"""
scraper.py -- Playwright-based scraper for the Investing.com XAU/USD technical page.

Uses a persistent Chromium context (saves cookies/localStorage to disk).
On first run (or when session expires), opens a VISIBLE browser window
for interactive Google OAuth sign-in, then switches to headless for scraping.

Sign-in detection uses the most reliable method: checking whether the
short-timeframe tabs (1Min, 5Min, 15Min) show "Unlock" vs real signals.
An "Unlock" label means the session is NOT authenticated with InvestingPro.

Usage:
    scraper = GoldScraper()
    scraper.start()                # Launch + sign in + navigate
    raw = scraper.read_snapshot()  # Read current DOM values
    scraper.stop()                 # Clean shutdown (session saved)
"""

from __future__ import annotations

import shutil
import time
from typing import Dict, Optional

from playwright.sync_api import (
    sync_playwright,
    Playwright,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeout,
)

from config.settings import (
    TARGET_URL,
    SIGNIN_URL,
    SIGNIN_TIMEOUT_SECONDS,
    HEADLESS,
    BROWSER_ARGS,
    USER_AGENT,
    VIEWPORT,
    PAGE_LOAD_TIMEOUT_MS,
    ELEMENT_TIMEOUT_MS,
    TIMEFRAME_MAP,
    LOCKED_TIMEFRAMES,
    BROWSER_REFRESH_EVERY_N_CYCLES,
    SESSION_DIR,
)
from utils.logger import get_logger

log = get_logger("scraper")

# Stealth JS injected into every page to defeat bot-detection
_STEALTH_SCRIPT = """
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){}, app: {} };
    const _origQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (p) =>
        p.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : _origQuery(p);
    Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US','en'] });
"""

# Ad/tracker patterns to block during scraping (speeds up page, fewer fingerprints)
_BLOCKED_ROUTES = [
    "**/securepubads*",
    "**/amazon-adsystem*",
    "**/doubleclick*",
    "**/facebook.net*",
    "**/hotjar*",
    "**/googletag*",
    "**/pbxai*",
]


def _abort_handler(route):
    route.abort()


class GoldScraper:
    """Persistent browser session with Google/InvestingPro sign-in support."""

    def __init__(self) -> None:
        self._pw: Optional[Playwright] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._cycle_count: int = 0
        self._is_running: bool = False

    # ------------------------------------------------------------------
    # Public lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """
        Start the pipeline:
        1. Try to resume saved session headlessly
        2. Navigate to technical page
        3. Verify InvestingPro access by checking 1Min tab
        4. If locked -> run interactive sign-in, then re-navigate
        """
        log.info("Starting browser with persistent session...")
        self._pw = sync_playwright().start()

        # Try headless resume first
        self._open_context(headless=HEADLESS)
        self._navigate_to_technical_page()

        # Definitive check: does the 1Min tab show real data or "Unlock"?
        if self._is_pro_locked():
            log.warning(
                "InvestingPro content is locked (1Min tab shows 'Unlock'). "
                "Starting interactive sign-in..."
            )
            self._close_context()
            self._run_interactive_signin()
            # Re-open headless and navigate after sign-in
            self._open_context(headless=HEADLESS)
            self._navigate_to_technical_page()

            if self._is_pro_locked():
                log.warning(
                    "Still locked after sign-in. "
                    "Short timeframes will show 'Unlock'. "
                    "Please verify your InvestingPro subscription is active."
                )
            else:
                log.info("InvestingPro access confirmed -- all 9 timeframes unlocked.")
        else:
            log.info("InvestingPro session active -- all 9 timeframes unlocked.")

        self._is_running = True
        log.info("Browser session ready -- page loaded successfully.")

    def stop(self) -> None:
        """Gracefully close browser (session cookies remain on disk)."""
        self._is_running = False
        self._close_context()
        if self._pw:
            try:
                self._pw.stop()
            except Exception:
                pass
        log.info("Browser session closed (session state saved to disk).")

    @property
    def is_running(self) -> bool:
        return self._is_running

    # ------------------------------------------------------------------
    # Context management
    # ------------------------------------------------------------------

    def _open_context(self, headless: bool) -> None:
        """Launch a persistent browser context (reads/writes SESSION_DIR)."""
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        
        launch_kwargs = {
            "user_data_dir": str(SESSION_DIR),
            "headless": headless,
            "args": BROWSER_ARGS,
            "user_agent": USER_AGENT,
            "viewport": VIEWPORT,
            "locale": "en-US",
            "timezone_id": "Asia/Kolkata",
            "java_script_enabled": True,
            "ignore_https_errors": True,
        }

        # We must use the default bundled Chromium for the automated scraping phase.
        # Native Chrome (channel="chrome") in headless mode frequently gets blocked
        # by Cloudflare. The bundled Chromium + stealth scripts bypass it perfectly.
        self._context = self._pw.chromium.launch_persistent_context(**launch_kwargs)
        self._context.add_init_script(_STEALTH_SCRIPT)
        log.debug(f"Browser context opened using bundled Chromium (headless={headless})")

    def _close_context(self) -> None:
        """Close page and context, saving session state."""
        if self._page and not self._page.is_closed():
            try:
                self._page.close()
            except Exception:
                pass
            self._page = None
        if self._context:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _navigate_to_technical_page(self) -> None:
        """Open a new page in the current context and load the target URL."""
        self._page = self._context.new_page()

        # Block heavy/ad resources (keep Google OAuth routes open)
        self._page.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2,ttf,eot}", _abort_handler)
        for pattern in _BLOCKED_ROUTES:
            self._page.route(pattern, _abort_handler)

        log.info(f"Navigating to {TARGET_URL} ...")
        self._page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)

        # Wait for price element to confirm the page rendered
        try:
            self._page.wait_for_selector(
                '[data-test="instrument-price-last"]',
                timeout=ELEMENT_TIMEOUT_MS,
            )
        except PlaywrightTimeout:
            log.warning("Price element not found in expected time -- continuing anyway.")

        # Let dynamic JS finish rendering signal tabs
        self._page.wait_for_timeout(4000)

    def _refresh_page(self) -> None:
        """Close current page and reopen (context/session stays intact)."""
        if self._page and not self._page.is_closed():
            try:
                self._page.close()
            except Exception:
                pass
            self._page = None
        self._navigate_to_technical_page()

    def _maybe_refresh(self) -> None:
        """Periodic page reload to prevent memory leaks or stale DOM."""
        self._cycle_count += 1
        if self._cycle_count >= BROWSER_REFRESH_EVERY_N_CYCLES:
            log.info(f"Periodic refresh after {BROWSER_REFRESH_EVERY_N_CYCLES} cycles...")
            self._cycle_count = 0
            self._refresh_page()

    # ------------------------------------------------------------------
    # InvestingPro access check (the reliable method)
    # ------------------------------------------------------------------

    def _is_pro_locked(self) -> bool:
        """
        Definitive InvestingPro access check.

        Reads the text of the 1Min tab. If it contains "Unlock" the user
        is NOT signed in with a Pro account.  Any real signal word means
        access is granted.

        This is far more reliable than checking header elements because
        Investing.com shows "My Watchlist" even for logged-out users.
        """
        try:
            tabs = self._page.query_selector_all('button[role="tab"]')
            for tab in tabs:
                text = tab.inner_text().strip()
                if "1 Min" in text or "1Min" in text:
                    log.debug(f"1Min tab text: {repr(text)}")
                    if "Unlock" in text or "unlock" in text:
                        return True   # Locked
                    # Has a real signal or at least no "Unlock"
                    return False
        except Exception as e:
            log.debug(f"Pro lock check failed: {e}")

        # If we can't find the tab at all (e.g., Cloudflare block in headless mode),
        # return True to force the visible browser window to open.
        log.debug("1Min tab not found -- assuming locked or page blocked by Cloudflare.")
        return True

    # ------------------------------------------------------------------
    # Interactive sign-in
    # ------------------------------------------------------------------

    def _run_interactive_signin(self) -> None:
        """
        Bypass Playwright entirely for sign-in.
        Launches the system's actual Chrome browser as a native OS process,
        pointing it to our session directory. Google sees a 100% legitimate
        browser, allowing the popup to work flawlessly.
        """
        print("\n" + "=" * 70)
        print("  INVESTINGPRO SIGN-IN REQUIRED")
        print("  " + "-" * 66)
        print("  To bypass Google's strict anti-bot detection, we are launching")
        print("  your native browser.")
        print("  \n  PLEASE FOLLOW THESE STEPS:")
        print("  1. In the browser that opens, click 'Sign In' (top right)")
        print("  2. Complete the 'Continue with Google' flow.")
        print("  3. Wait until you see your profile/dashboard loaded on the page.")
        print("  4. CLOSE THE ENTIRE BROWSER WINDOW to continue.")
        print("=" * 70 + "\n")

        import os
        import sys
        import subprocess
        
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        ]
        
        exe_path = next((p for p in chrome_paths if os.path.exists(p)), None)
        
        if not exe_path:
            log.error("Could not find Google Chrome or MS Edge on your system.")
            log.error("Please sign in manually by running: python manual_login.py")
            sys.exit(1)

        log.info("Waiting for you to sign in and close the browser...")
        
        try:
            # Launch Chrome as a completely native OS process
            subprocess.run([
                exe_path,
                f"--user-data-dir={SESSION_DIR}",
                "--no-first-run",
                "--no-default-browser-check",
                TARGET_URL
            ])
        except KeyboardInterrupt:
            pass
            
        print("\n  [OK] Browser closed. Attempting to resume automated session...\n")

    def force_reload(self) -> None:
        """Force a full page reload (called by watchdog on staleness)."""
        log.warning("Forcing full page reload...")
        try:
            self._refresh_page()
            self._cycle_count = 0
        except Exception as e:
            log.error(f"Force reload failed: {e}")
            raise

    # ------------------------------------------------------------------
    # Data reading
    # ------------------------------------------------------------------

    def read_snapshot(self) -> Dict[str, Optional[str]]:
        """
        Read current price + summary signals from the live DOM.

        Returns a dict like:
            {
                "price":   "4133.35",
                "1 min":   "Strong Sell",
                "5 min":   "Buy",
                ...
                "Monthly": "Strong Buy",
            }
        """
        if not self._is_running or not self._page or self._page.is_closed():
            raise RuntimeError("Browser session not active. Call start() first.")

        self._maybe_refresh()

        raw: Dict[str, Optional[str]] = {}
        raw["price"] = self._read_price()

        for tab_label, col_name in TIMEFRAME_MAP:
            if tab_label in LOCKED_TIMEFRAMES:
                raw[col_name] = "N/A"
            else:
                raw[col_name] = self._read_timeframe_signal(tab_label)

        return raw

    def _read_price(self) -> Optional[str]:
        """Extract the current XAU/USD price from the instrument header."""
        selectors = [
            '[data-test="instrument-price-last"]',
            'span.text-5xl',
            '.instrument-price_last__KQzyA',
            'div[class*="instrument-price"] span',
        ]
        for sel in selectors:
            try:
                el = self._page.query_selector(sel)
                if el:
                    text = el.inner_text().strip()
                    if text and any(c.isdigit() for c in text):
                        log.debug(f"Price via '{sel}': {text}")
                        return text
            except Exception as e:
                log.debug(f"Price selector '{sel}' failed: {e}")
        log.warning("Could not read price from any selector.")
        return None

    def _read_timeframe_signal(self, tab_label: str) -> Optional[str]:
        """
        Read the summary signal for a timeframe tab.
        Tab text is e.g. "Hourly\\nStrong Sell" -- we take the last line.
        """
        try:
            tabs = self._page.query_selector_all('button[role="tab"]')
            for tab in tabs:
                text = tab.inner_text().strip()
                if tab_label in text:
                    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
                    if len(lines) >= 2:
                        signal = lines[-1]
                        log.debug(f"'{tab_label}' -> '{signal}'")
                        return signal
                    elif len(lines) == 1:
                        log.debug(f"'{tab_label}' tab has no signal yet.")
                        return None

            # Fallback: get_by_role
            try:
                tab = self._page.get_by_role("tab", name=tab_label)
                if tab.count() > 0:
                    full_text = tab.first.inner_text().strip()
                    lines = [ln.strip() for ln in full_text.split("\n") if ln.strip()]
                    if len(lines) >= 2:
                        return lines[-1]
            except Exception:
                pass

            log.warning(f"Tab '{tab_label}' not found.")
            return None

        except Exception as e:
            log.error(f"Error reading '{tab_label}': {e}")
            return None
