# XAU/USD Gold Trading Data Pipeline + Strategy Engine

Real-time scraper for Investing.com XAU/USD technical analysis data with a
rule-based trading strategy engine. Scraped signals are stored in daily Excel
files alongside advisory LONG/SHORT/FLAT trade decisions.

## Architecture

```
Scheduler (5s) → Playwright Scraper → Parser → Validator ──┐
       │                │                │           │      │
       │                └── Logger ◄─────┴───────────┘      │
       │                                                    ▼
       │           ┌──────────────────────────────────────────────┐
       │           │  Strategy Engine                             │
       │           │  ┌─────────────┐  ┌───────────────────────┐  │
       │           │  │ Bias Detect │  │ ATR Approximator      │  │
       │           │  │ (D+W→dir)   │  │ (rolling price range) │  │
       │           │  └──────┬──────┘  └──────────┬────────────┘  │
       │           │         ▼                    ▼               │
       │           │  ┌──────────────┐  ┌────────────────┐       │
       │           │  │ Entry Confirm│  │ Risk Manager   │       │
       │           │  │ (H1+H4→ok?) │  │ (SL/TP/sizing) │       │
       │           │  └──────┬───────┘  └───────┬────────┘       │
       │           │         └──────┬───────────┘                │
       │           │                ▼                             │
       │           │  StrategySignal (LONG/SHORT/FLAT)           │
       │           └─────────────────────────┬───────────────────┘
       │                                     ▼
       └──────────────────────────────► Excel Storage
```

## Quick Start

### 1. Install Dependencies

```bash
cd d:\InvPro
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure (Optional)

```bash
copy .env.example .env
notepad .env
```

Key settings in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `ACCOUNT_BALANCE` | 10000 | Notional account balance (USD) |
| `RISK_PER_TRADE_PCT` | 0.01 | Risk per trade (1%) |
| `MIN_REWARD_RISK_RATIO` | 2.0 | Minimum reward:risk (1:2) |
| `ATR_PERIOD` | 14 | Rolling ATR window count |
| `ATR_STOP_MULTIPLIER` | 1.5 | Stop loss = ATR × multiplier |
| `REFRESH_INTERVAL_SECONDS` | 5 | Scrape frequency |
| `HEADLESS` | true | Show/hide browser window |
| `LOG_LEVEL` | INFO | DEBUG / INFO / WARNING / ERROR |

### 3. Run the Pipeline

```bash
python main.py
```

### 4. First Run: Sign In

On the first run, a **visible browser window** will open:
1. Click **"Sign In"** on the Investing.com page
2. Choose **"Continue with Google"**
3. Complete the Google OAuth flow in your browser
4. Wait until you see your profile/dashboard

Your session is **automatically saved** to the `session/` folder. On subsequent runs, the pipeline will reuse your saved session and go straight to scraping -- no sign-in needed.

> **Note:** If your session expires (usually after a few days), the pipeline will detect it and re-open the sign-in window automatically.

Press `Ctrl+C` to stop gracefully. All data is saved to `data/xau_usd_YYYY-MM-DD.xlsx`.

## Output

### Excel Schema

The daily Excel file has two sections:

#### Raw Data Columns

| Column | Type | Example |
|--------|------|---------|
| Date-Time | datetime | 2026-06-23 20:35:48 |
| Price | float | 4,127.33 |
| 1 min | string | Strong Sell |
| 5 min | string | Buy |
| 15 min | string | Neutral |
| 30 min | string | Buy |
| Hourly | string | Strong Sell |
| 5 Hours | string | Sell |
| Daily | string | Strong Sell |
| Weekly | string | Strong Sell |
| Monthly | string | Strong Buy |

#### Strategy Output Columns

| Column | Type | Example |
|--------|------|---------|
| Signal | string | LONG / SHORT / FLAT |
| Bias | string | Bullish (Daily=Buy, Weekly=Strong Buy) |
| Confidence | string | HIGH / MEDIUM / LOW |
| Entry | float | 4,127.33 |
| Stop Loss | float | 4,119.50 |
| Take Profit | float | 4,142.99 |
| Risk ($) | float | 100.00 |
| Position (lots) | float | 0.1282 |
| Reason | string | Aligned LONG: bias=+3 (D=Buy, W=Strong Buy)... |

### Signal Values

Each timeframe column contains one of: `Strong Buy`, `Buy`, `Neutral`, `Sell`, `Strong Sell`, or `N/A`.

### File Output

- **Location**: `data/` directory
- **Naming**: `xau_usd_2026-06-23.xlsx` (daily rotation at midnight)
- **Format**: Colour-coded signals, frozen header, auto-filters enabled
- **Strategy section**: Purple header, LONG=green, SHORT=red, FLAT=grey

## Strategy Rules

The strategy engine evaluates signals every 30 scrape cycles (~2.5 minutes) and follows these rules:

### 1. Bias Detection (Daily + Weekly)
- Both bullish (score sum ≥ +2) → **Long bias**
- Both bearish (score sum ≤ -2) → **Short bias**
- Mixed or neutral → **No trade**

### 2. Entry Confirmation (Hourly + 5 Hours)
- Confirmation timeframes must agree with the bias direction
- Long bias requires H1 + H4 score sum ≥ +1
- Short bias requires H1 + H4 score sum ≤ -1

### 3. ATR-Based Stop Loss
- ATR approximated from rolling price windows (~5 min each)
- Stop loss = entry price ± (ATR × 1.5)
- Requires ~14 completed windows (~70 min) to warm up

### 4. Risk Management
- Minimum reward:risk ratio = 1:2
- Take profit = entry ± (stop_distance × RR ratio)
- Risk per trade: 0.5% to 1% of account balance (configurable)
- Position size = risk_amount / (stop_distance × lot_size)

### 5. Confidence Scoring
- **HIGH**: Strong bias + strong confirmation + monthly alignment
- **MEDIUM**: Moderate bias or partial confirmation
- **LOW**: Marginal alignment (FLAT signals)

> **Important**: This strategy produces **advisory signals only** — it does not place trades.
> The ATR is approximated from scraped price ticks, not true OHLC candlestick data.

## Project Structure

```
InvPro/
├── config/
│   └── settings.py          # All configuration + .env loading + strategy params
├── core/
│   ├── scraper.py           # Playwright browser automation + sign-in
│   ├── parser.py            # DOM text -> structured data
│   ├── validator.py         # Data quality checks
│   ├── storage.py           # Excel read/write (raw + strategy columns)
│   └── strategy.py          # Rule-based trading strategy engine
├── utils/
│   └── logger.py            # Rotating file + console logging
├── data/                    # Excel output files (auto-created)
├── logs/                    # Log files (auto-created)
├── session/                 # Persistent browser session (auto-created)
├── main.py                  # Entry point & scheduler loop
├── .env.example             # Sample environment configuration
├── backtest_notes.md        # Backtesting extension guide
├── requirements.txt         # Python dependencies
└── README.md                # This file
```

## Monitoring

- **Console**: Live dashboard showing current price, strategy direction (▲ LONG / ▼ SHORT / — FLAT), and signals
- **Logs**: `logs/pipeline.log` (rotating, 10 MB × 5 files)
- **Health**: `health.json` — machine-readable status for external monitoring

## Backtesting

See [backtest_notes.md](backtest_notes.md) for a complete guide on:
- Replaying historical data through the strategy
- Ready-to-use `Backtester` class scaffolding
- Key metrics (win rate, Sharpe, max drawdown, profit factor)
- Recommended libraries (vectorbt, backtrader, QuantStats)

## Limitations

1. **1 Min / 5 Min / 15 Min** timeframes require InvestingPro subscription
2. 5-second polling ≠ true streaming (inherent latency)
3. Extended sessions may trigger Cloudflare anti-bot detection
4. ~17,280 rows/day at 5s interval (~1 MB/day)
5. No data during market closures (weekends/holidays)
6. ATR is approximated from tick data, not true OHLC candles
7. Strategy signals are advisory only — no auto-execution

## Future Improvements

- **Signal Generation**: Multi-timeframe confluence scoring
- **Alerts**: Telegram/email on signal changes
- **Database**: Migrate from Excel to SQLite/PostgreSQL
- **WebSocket**: Reverse-engineer real-time data stream
- **Dashboard**: Streamlit/Dash real-time visualization
- **Backtesting**: Full walk-forward optimisation framework
- **True ATR**: Integrate OANDA/MT5 API for real OHLC data

## Disclaimer

This tool is for **personal research and educational purposes only**. Automated scraping may violate Investing.com's Terms of Service. For production trading, use official APIs or licensed data feeds. The strategy signals are **not financial advice** — always do your own analysis.

#   I n v P r o  
 