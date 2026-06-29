"""
database.py -- SQLite repository with connection pooling and migration support.
"""

import sqlite3
import os
from typing import List, Tuple, Optional, Any
from pathlib import Path
from utils.logger import get_logger

log = get_logger("database")

import contextlib

class Database:
    """Manages SQLite connections, schema creation, and migrations."""
    
    def __init__(self, db_path: str = "trading_state.db") -> None:
        self.db_path = db_path
        self._pragmas_logged = False
        # Initialize DB and run migrations/pragmas
        with contextlib.closing(self.get_connection()) as conn:
            pass
            
    def get_connection(self) -> sqlite3.Connection:
        """Get a new SQLite connection with dict rows."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
        conn.row_factory = sqlite3.Row
        
        # Enforce durability pragmas on every connection
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA wal_autocheckpoint=1000;")
        conn.execute("PRAGMA foreign_keys=ON;")
        
        if not getattr(self, '_pragmas_logged', True):
            log.info("SQLite connection established with WAL, synchronous=NORMAL, autocheckpoint=1000")
            self._pragmas_logged = True
            
        return conn
        
    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a single statement and commit."""
        with contextlib.closing(self.get_connection()) as conn:
            with conn: # handles transaction
                cursor = conn.execute(sql, params)
                # Keep lastrowid and rowcount accessible by copying them if needed, 
                # but cursor properties remain accessible after conn closes.
                return cursor
            
    def executemany(self, sql: str, data: list) -> None:
        """Execute multiple statements and commit."""
        with contextlib.closing(self.get_connection()) as conn:
            with conn:
                conn.executemany(sql, data)
            
    def fetchall(self, sql: str, params: tuple = ()) -> List[sqlite3.Row]:
        """Fetch all rows from a query."""
        with contextlib.closing(self.get_connection()) as conn:
            cursor = conn.execute(sql, params)
            return cursor.fetchall()
            
    def fetchone(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """Fetch a single row from a query."""
        with contextlib.closing(self.get_connection()) as conn:
            cursor = conn.execute(sql, params)
            return cursor.fetchone()

    def migrate(self) -> None:
        """Run schema upgrades idempotently."""
        migrations_dir = Path(__file__).parent.parent / "migrations"
        if not migrations_dir.exists():
            log.warning(f"Migrations directory not found at {migrations_dir}")
            return
            
        with self.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
            """)
            
            # Simple migration runner (assumes alphabetical order is correct)
            for file_path in sorted(migrations_dir.glob("*.sql")):
                version = file_path.stem
                cursor = conn.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (version,))
                if not cursor.fetchone():
                    log.info(f"Applying migration: {version}")
                    sql = file_path.read_text(encoding="utf-8")
                    conn.executescript(sql)
                    import datetime
                    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    conn.execute("INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)", (version, now))
            
            conn.commit()
