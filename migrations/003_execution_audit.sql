ALTER TABLE orders ADD COLUMN execution_mode TEXT;
ALTER TABLE orders ADD COLUMN slippage_model TEXT;

ALTER TABLE positions ADD COLUMN execution_mode TEXT;
ALTER TABLE positions ADD COLUMN slippage_model TEXT;
ALTER TABLE positions ADD COLUMN slippage_points_applied REAL;

ALTER TABLE trades ADD COLUMN execution_mode TEXT;
ALTER TABLE trades ADD COLUMN slippage_model TEXT;
ALTER TABLE trades ADD COLUMN slippage_points_applied REAL;
