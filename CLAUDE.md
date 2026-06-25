# XAU/USD Gold Trading Pipeline - CLAUDE.md

## Project Overview
This project is an XAU/USD Gold Trading Data Pipeline and Strategy Engine. It scrapes real-time technical analysis data from Investing.com, processes it through a rule-based strategy engine, and stores the signals and advisory decisions in daily Excel files. Additionally, a React-based paper trading dashboard is provided for monitoring.

## Tech Stack
- **Backend/Scraper**: Python 3, Playwright (for browser automation), openpyxl (for Excel storage), pandas (optional).
- **Frontend/Dashboard**: React 19, Vite, Tailwind CSS v4, Recharts, Lucide React.
- **Environment**: Managed via `.env` files.

## Project Structure Skeleton
```text
InvPro/
├── CLAUDE.md                 # Project conventions and system prompts for Claude Code
├── README.md                 # Primary project documentation, architecture, and quick start guide
├── main.py                   # Main entry point and scheduler loop for the backend scraper
├── test_signin.py            # Unit/integration test for the Investing.com sign-in flow
├── manual_login.py           # Helper script for manually saving a browser auth session
├── dry_run_test.py           # Script to run the pipeline without writing to Excel (for testing)
├── requirements.txt          # Python pip dependencies
├── .env.example              # Template for environment variables and secrets
├── backtest_notes.md         # Documentation and scaffolding guide for strategy backtesting
├── health.json               # Auto-generated JSON file indicating current scraper health status
│
├── config/
│   └── settings.py           # Global configuration settings, env loading, and strategy params
│
├── core/
│   ├── scraper.py            # Playwright automation script for fetching data from Investing.com
│   ├── parser.py             # Parses the raw HTML/DOM into structured trading data
│   ├── validator.py          # Validates parsed data quality and constraints
│   ├── strategy.py           # The rule-based trading strategy engine (bias, entry, risk)
│   └── storage.py            # Handles reading/writing the daily Excel output files
│
├── paper_trading/
│   ├── main.py               # Entry point specifically for the paper trading simulation engine
│   ├── core/                 # Core engine for executing and journaling simulated trades
│   ├── config/               # Settings specifically for the paper trading environment
│   └── utils/                # Utilities and helper functions for paper trading
│
├── utils/
│   └── logger.py             # Custom rotating file logger and console output formatter
│
└── dashboard/                # Vite + React frontend application (Paper Trading Dashboard)
    ├── src/
    │   ├── App.jsx           # Main React application component assembling the dashboard layout
    │   ├── index.css         # Global Tailwind v4 CSS variables and base styles
    │   ├── lib/              # Utility functions for the frontend (e.g., Tailwind class merging)
    │   └── components/       # React UI, Layout, and Dashboard components
    ├── package.json          # Node dependencies for the dashboard
    └── vite.config.js        # Vite bundler configuration including Tailwind plugins
```

## Build and Run Commands
- **Backend**:
  - Install dependencies: `pip install -r requirements.txt` and `playwright install chromium`
  - Run the pipeline: `python main.py`
- **Frontend Dashboard**:
  - Navigate to directory: `cd dashboard`
  - Install dependencies: `npm install`
  - Run dev server: `npm run dev`

## Coding Conventions
### Python
- Maintain strong type hinting across all Python files.
- Ensure proper logging using the custom `logger.py` module.
- **CRITICAL**: Do not add auto-execution capabilities to the strategy engine; signals are strictly advisory.
- When modifying `storage.py`, be careful with the `openpyxl` implementation as the Excel layout (colours, filters, frozen headers) is strictly defined.

### React (Dashboard)
- Use standard React functional components with hooks.
- Use Tailwind CSS v4 for all styling. Rely on the predefined CSS variables in `src/index.css` (e.g., `--color-bullish`, `--color-bearish`, `--color-card`).
- Follow a modular component structure (`components/ui/`, `components/layout/`, `components/dashboard/`).

## Strategy Rules Context
- **Bias**: Determined by Daily and Weekly signals (+2 = Long, -2 = Short).
- **Entry**: Confirmed by Hourly and 5-Hour signals.
- **Stop Loss**: ATR-based, approximated from rolling price windows.
- **Risk**: 0.5% to 1% of the account balance per trade.

## Claude-Mem Integration
This file works alongside `claude-mem` to preserve context across sessions. When new features are added to the strategy or dashboard, this file should be updated to maintain an accurate source of truth for all future Claude Code sessions.
