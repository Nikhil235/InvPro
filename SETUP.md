# InvPro System Setup Guide

This document outlines the step-by-step requirements and instructions to build, configure, and run the **InvPro** paper-trading system on a new machine.

---

## 1. System Requirements

Ensure the target system has the following software installed:
- **Python**: Version `3.9` or higher.
- **Node.js**: Version `16` or higher (includes `npm`).
- **Google Chrome / Chromium**: Or let Playwright install its own local binaries.
- **SQLite3**: Python includes the native `sqlite3` library; no separate server installation is required.

---

## 2. Step-by-Step Installation

### Step A: Clone the Repository
Clone the codebase to your target system:
```bash
git clone <repository-url>
cd InvPro
```

### Step B: Configure Environment Variables
Copy the template configuration file to `.env`:
```bash
cp .env.example .env
```
Open `.env` and verify key parameters (such as database location, port numbers, or default margins):
- `ACCOUNT_BALANCE`: Starting simulated capital (default: `10000.0`).
- `RISK_PER_TRADE_PCT`: Sizing risk ratio (e.g. `0.01` for 1%).
- `API_PORT`: API listener port (default: `8000`).

### Step C: Setup Python Backend Environment
1. Create a Python virtual environment to keep packages isolated:
   ```bash
   python -m venv venv
   ```
2. Activate the virtual environment:
   - **Windows (Command Prompt)**: `venv\Scripts\activate.bat`
   - **Windows (PowerShell)**: `venv\Scripts\Activate.ps1`
   - **Linux / macOS**: `source venv/bin/activate`
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Install the package in editable developer mode with test runner dependencies:
   ```bash
   pip install -e .[dev]
   ```
5. **Install Playwright Scraper Browsers** (Critical for gold price scraping):
   ```bash
   playwright install chromium
   ```

### Step D: Setup React Frontend Environment
1. Navigate to the `dashboard` directory:
   ```bash
   cd dashboard
   ```
2. Install npm dependencies:
   ```bash
   npm install
   ```
3. Return to the root folder:
   ```bash
   cd ..
   ```

---

## 3. Database & Migration Schema

InvPro uses a serverless SQLite database (`trading_state.db`) stored locally. 
- **Auto-Initialization**: The database file is created automatically on startup.
- **Auto-Migrations**: The system scans the `migrations/` directory and executes all SQL migration files alphabetically during initial database connection. You do **not** need to run manual schema creation scripts.

---

## 4. Running the Project

You must start the **FastAPI Backend**, the **Trading Engine**, and the **React Frontend** concurrently.

### Quick Start (Windows)
Run the automated script to launch all three services in separate command windows:
```cmd
run.bat
```
To shut down all services safely, run:
```cmd
stop.bat
```

### Manual Start (Cross-Platform)

#### 1. FastAPI API Backend
Starts the HTTP/Websocket server to receive trading data:
```bash
python main.py
```

#### 2. Trading Engine
Runs the core strategy scanner and paper broker loop. Choose one of the following modes:
- **Live Mode** (scrapes technical indicators in real-time):
  ```bash
  python -m paper_trading.main --mode live
  ```
- **Replay Mode** (replays trading ticks from historical data files):
  ```bash
  python -m paper_trading.main --mode replay
  ```

#### 3. React Frontend Dashboard
Launches the real-time UI dashboard at `http://localhost:5173`:
```bash
cd dashboard
npm run dev
```

---

## 5. Verification & Testing

Verify that everything is set up correctly by running the unit test suite:
```bash
python -m pytest
```
This runs the complete test suite (96 tests) verifying technical analysis bias, ATR positioning, take-profit legs, and risk calculations.
