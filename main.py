"""
main.py -- Entry point for the InvPro Trading Simulator API.

Starts the FastAPI server which manages live and replay sessions.
"""

import os
import sys
import uvicorn
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from paper_trading.config.settings import print_banner

def main():
    print_banner()
    print("Starting InvPro Simulator API on http://localhost:8000")
    print("Dashboard available at http://localhost:5173 (if running npm run dev)")
    uvicorn.run("api.app:app", host="0.0.0.0", port=8000, reload=True, reload_dirs=["api", "core", "paper_trading"], log_level="info")

if __name__ == "__main__":
    main()
