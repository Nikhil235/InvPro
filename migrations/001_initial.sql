-- ═══════════════════════════════════════════════════════════════
-- ORDERS: Full order lifecycle
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS orders (
    order_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    side            TEXT NOT NULL CHECK(side IN ('LONG','SHORT')),
    order_type      TEXT NOT NULL CHECK(order_type IN ('MARKET','LIMIT','STOP', 'STOP_LIMIT')),
    status          TEXT NOT NULL CHECK(status IN ('PENDING','FILLED','REJECTED','CANCELLED')),
    requested_price REAL NOT NULL,
    fill_price      REAL,
    lots            REAL NOT NULL,
    stop_loss       REAL,
    take_profit     REAL,
    confidence      TEXT,
    bias            TEXT,
    risk_amount     REAL,
    reason          TEXT,
    spread_cost     REAL,
    slippage_cost   REAL,
    rejection_reason TEXT,
    signal_time     TEXT NOT NULL,  -- UTC ISO8601
    created_at      TEXT NOT NULL,  -- UTC ISO8601
    filled_at       TEXT,           -- UTC ISO8601
    cancelled_at    TEXT,           -- UTC ISO8601
    session_id      TEXT            -- links to sessions.session_id
);

-- ═══════════════════════════════════════════════════════════════
-- POSITIONS: Currently open positions
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS positions (
    position_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id        INTEGER NOT NULL REFERENCES orders(order_id),
    side            TEXT NOT NULL,
    entry_price     REAL NOT NULL,  -- advisory price from strategy
    fill_price      REAL NOT NULL,  -- actual fill
    stop_loss       REAL NOT NULL,
    take_profit     REAL NOT NULL,
    lots            REAL NOT NULL,
    confidence      TEXT,
    bias            TEXT,
    risk_amount     REAL,
    reason          TEXT,
    open_time       TEXT NOT NULL,   -- UTC ISO8601
    current_price   REAL DEFAULT 0,
    unrealised_pnl  REAL DEFAULT 0,
    session_id      TEXT
);

-- ═══════════════════════════════════════════════════════════════
-- TRADES: Closed trades (the journal)
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS trades (
    trade_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id        INTEGER NOT NULL,
    position_id     INTEGER NOT NULL,
    side            TEXT NOT NULL,
    entry_price     REAL NOT NULL,
    fill_price      REAL NOT NULL,
    exit_price      REAL NOT NULL,
    stop_loss       REAL NOT NULL,
    take_profit     REAL NOT NULL,
    lots            REAL NOT NULL,
    open_time       TEXT NOT NULL,
    close_time      TEXT NOT NULL,
    exit_reason     TEXT NOT NULL,   -- SL_HIT, TP_HIT, SIGNAL_REVERSAL, MANUAL_CLOSE, END_OF_SESSION, RISK_LIMIT
    gross_pnl       REAL NOT NULL,
    commission      REAL NOT NULL,
    net_pnl         REAL NOT NULL,
    risk_amount     REAL,
    rr_achieved     REAL,
    confidence      TEXT,
    bias            TEXT,
    balance_after   REAL NOT NULL,
    reason          TEXT,
    session_id      TEXT
);

-- ═══════════════════════════════════════════════════════════════
-- LEDGER: Account state snapshots (time-series)
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS ledger (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,   -- UTC ISO8601
    balance         REAL NOT NULL,
    equity          REAL NOT NULL,
    unrealised_pnl  REAL NOT NULL DEFAULT 0,
    margin_used     REAL NOT NULL DEFAULT 0,
    peak_equity     REAL NOT NULL,
    drawdown_abs    REAL NOT NULL DEFAULT 0,
    drawdown_pct    REAL NOT NULL DEFAULT 0,
    open_positions  INTEGER NOT NULL DEFAULT 0,
    session_id      TEXT
);

-- ═══════════════════════════════════════════════════════════════
-- SNAPSHOTS: Raw scraped data (replaces Excel as source of truth)
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    price           REAL NOT NULL,
    signal_1m       TEXT,
    signal_5m       TEXT,
    signal_15m      TEXT,
    signal_30m      TEXT,
    signal_1h       TEXT,
    signal_5h       TEXT,
    signal_daily    TEXT,
    signal_weekly   TEXT,
    signal_monthly  TEXT,
    strategy_dir    TEXT,            -- LONG/SHORT/FLAT at scrape time
    session_id      TEXT
);

-- ═══════════════════════════════════════════════════════════════
-- CANDLES: Aggregated 1-minute OHLC from tick data
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS candles (
    time            TEXT PRIMARY KEY, -- UTC ISO8601 truncated to minute
    open            REAL NOT NULL,
    high            REAL NOT NULL,
    low             REAL NOT NULL,
    close           REAL NOT NULL,
    tick_count      INTEGER DEFAULT 1
);

-- ═══════════════════════════════════════════════════════════════
-- EVENTS_LOG: Full audit trail of every system event
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS events_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    payload         TEXT NOT NULL,   -- JSON blob
    session_id      TEXT
);

-- ═══════════════════════════════════════════════════════════════
-- SESSIONS: Browser session tracking
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sessions (
    session_id      TEXT PRIMARY KEY,
    mode            TEXT NOT NULL,   -- 'live' or 'replay'
    started_at      TEXT NOT NULL,
    ended_at        TEXT,
    initial_capital REAL NOT NULL,
    final_equity    REAL,
    total_trades    INTEGER DEFAULT 0,
    net_pnl         REAL DEFAULT 0,
    status          TEXT DEFAULT 'active',  -- active, completed, error
    config_json     TEXT             -- serialised settings snapshot
);

-- ═══════════════════════════════════════════════════════════════
-- ALERT_RULES: Price alerts
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS alert_rules (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    condition       TEXT NOT NULL,
    value           REAL NOT NULL,
    is_active       INTEGER DEFAULT 1
);

-- ═══════════════════════════════════════════════════════════════
-- INDEXES
-- ═══════════════════════════════════════════════════════════════
CREATE INDEX IF NOT EXISTS idx_trades_session ON trades(session_id);
CREATE INDEX IF NOT EXISTS idx_trades_close_time ON trades(close_time);
CREATE INDEX IF NOT EXISTS idx_ledger_timestamp ON ledger(timestamp);
CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp ON snapshots(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_type ON events_log(event_type);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
