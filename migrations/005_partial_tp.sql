-- Migration 005: Add partial take-profit levels and tracking columns

-- Alter orders table
ALTER TABLE orders ADD COLUMN tp1 REAL;
ALTER TABLE orders ADD COLUMN tp2 REAL;
ALTER TABLE orders ADD COLUMN tp3 REAL;

-- Alter positions table
ALTER TABLE positions ADD COLUMN tp1 REAL;
ALTER TABLE positions ADD COLUMN tp2 REAL;
ALTER TABLE positions ADD COLUMN tp3 REAL;
ALTER TABLE positions ADD COLUMN tp1_hit INTEGER DEFAULT 0;
ALTER TABLE positions ADD COLUMN tp2_hit INTEGER DEFAULT 0;
ALTER TABLE positions ADD COLUMN tp3_hit INTEGER DEFAULT 0;
ALTER TABLE positions ADD COLUMN realised_pnl REAL DEFAULT 0.0;
ALTER TABLE positions ADD COLUMN initial_lots REAL;
ALTER TABLE positions ADD COLUMN initial_sl REAL;

-- Alter trades table
ALTER TABLE trades ADD COLUMN tp1 REAL;
ALTER TABLE trades ADD COLUMN tp2 REAL;
ALTER TABLE trades ADD COLUMN tp3 REAL;
