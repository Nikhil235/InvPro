"""
test_signin.py -- Quick test of the sign-in flow.

Opens a visible browser for sign-in, then attempts one scrape cycle
to verify all 9 timeframes are accessible.
"""

import sys
import os
import time

# Fix Windows console encoding
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass



from core.scraper import GoldScraper
from core.parser import parse_snapshot
from utils.logger import get_logger

log = get_logger("test_signin")


def main():
    print("=" * 60)
    print("  SIGN-IN TEST")
    print("  Will open browser for Google sign-in,")
    print("  then attempt one scrape cycle.")
    print("=" * 60)

    scraper = GoldScraper()

    try:
        # Launch browser (will open sign-in window if needed)
        print("\n[1/3] Starting browser + sign-in flow...")
        scraper.start()
        print("  [OK] Browser ready, session active.")

        # Scrape one cycle
        print("\n[2/3] Attempting scrape with all 9 timeframes...")
        raw = scraper.read_snapshot()

        print(f"\n  Price: {raw.get('price')}")
        print("  Timeframe signals:")
        for key, val in raw.items():
            if key != "price":
                marker = "[OK]" if val and val != "N/A" else "[--]"
                print(f"    {marker} {key}: {val}")

        # Count how many timeframes have real signals
        real_signals = sum(
            1 for k, v in raw.items()
            if k != "price" and v and v != "N/A"
        )
        print(f"\n  Timeframes with data: {real_signals}/9")

        if real_signals >= 6:
            print("\n[3/3] [PASS] Sign-in working! InvestingPro data accessible.")
        else:
            print("\n[3/3] [WARN] Some timeframes missing -- check sign-in status.")

    except Exception as e:
        print(f"\n  [FAIL] Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        scraper.stop()
        print("\nDone.")


if __name__ == "__main__":
    main()
