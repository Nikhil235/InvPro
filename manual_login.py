"""
manual_login.py -- Natively launches Google Chrome to allow manual sign-in.

This script completely bypasses Playwright/automation detection by launching
your actual Chrome browser natively, but forcing it to save all cookies to
our custom `session/` folder.

Once you sign in and close Chrome, the automated pipeline will inherit
your authenticated session!
"""

import os
import sys
import subprocess
from pathlib import Path

# Setup paths
PROJECT_ROOT = Path(__file__).resolve().parent
SESSION_DIR = PROJECT_ROOT / "session"
SESSION_DIR.mkdir(parents=True, exist_ok=True)

def main():
    print("=" * 70)
    print("  MANUAL SIGN-IN LAUNCHER")
    print("=" * 70)
    
    # Common Chrome installation paths on Windows
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        # MS Edge fallback
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    
    exe_path = next((p for p in chrome_paths if os.path.exists(p)), None)
    
    if not exe_path:
        print("[!] Could not find Google Chrome or MS Edge on your system.")
        sys.exit(1)
        
    print(f"\n  Found browser: {exe_path}")
    print("  Launching native browser (100% undetected by anti-bot)...")
    print("\n  PLEASE FOLLOW THESE STEPS:")
    print("  1. In the browser that opens, click 'Sign In' (top right)")
    print("  2. Complete the 'Continue with Google' flow.")
    print("  3. Once you see your profile/dashboard on Investing.com,")
    print("     CLOSE THE ENTIRE BROWSER WINDOW.")
    print("\n  Waiting for browser to close...")
    
    try:
        # Launch Chrome as a completely native process pointing to our session dir
        subprocess.run([
            exe_path,
            f"--user-data-dir={SESSION_DIR}",
            "--no-first-run",
            "--no-default-browser-check",
            "https://www.investing.com/currencies/xau-usd-technical"
        ])
    except KeyboardInterrupt:
        pass
        
    print("\n  [OK] Browser closed. Session saved to:", SESSION_DIR)
    print("  You can now run 'python main.py' to start scraping!\n")

if __name__ == "__main__":
    main()
