-- ═══════════════════════════════════════════════════════════════
-- NEWS EVENTS: Geopolitical and macro-impact alerts without WhatsApp tracking
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS news_events (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp         TEXT NOT NULL,
    headline          TEXT NOT NULL,
    summary           TEXT,
    source_url        TEXT,
    sentiment         TEXT CHECK(sentiment IN ('BULLISH', 'BEARISH', 'VOLATILITY_SPIKE', 'RISK_OFF', 'NEUTRAL')),
    impact_score      TEXT CHECK(impact_score IN ('HIGH', 'MEDIUM', 'LOW')),
    confidence        REAL,
    target_market     TEXT,
    horizon_hours     INTEGER
);

CREATE INDEX IF NOT EXISTS idx_news_events_time ON news_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_news_events_impact ON news_events(impact_score);
