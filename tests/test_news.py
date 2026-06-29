"""
test_news.py -- Unit tests for classification, deduplication, and caching of news intelligence events.
"""

from __future__ import annotations

import pytest
import os
from datetime import datetime, timezone

from core.news_classifier import classify_event
from core.news_ingestor import NewsIngestor
from core.database import Database
from core.event_bus import EventBus

def test_classify_geopolitical_risk():
    article = {
        "headline": "BREAKING: Sanctions imposed on crude oil routes due to geopolitical threats",
        "summary": "Geopolitical blockades rising amid conflict in the Middle East."
    }
    result = classify_event(article)
    assert result["sentiment"] == "RISK_OFF"
    assert result["impact_score"] == "HIGH"
    assert "Gold" in result["target_market"]
    assert result["horizon_hours"] == 48

def test_classify_fed_rates():
    article = {
        "headline": "Fed updates interest rate stance following CPI prints",
        "summary": "FOMC members discuss potential rate hike options."
    }
    result = classify_event(article)
    assert result["sentiment"] == "VOLATILITY_SPIKE"
    assert result["impact_score"] == "HIGH"
    assert result["target_market"] == "USD"

def test_classify_low_impact():
    article = {
        "headline": "Minor tech updates reported by broker platform",
        "summary": "Staging server performs routine cache updates."
    }
    result = classify_event(article)
    assert result["sentiment"] == "NEUTRAL"
    assert result["impact_score"] == "LOW"

class TestNewsIngestor:
    def setup_method(self):
        self.db_path = "test_news_ingest.db"
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass
                
        self.db = Database(db_path=self.db_path)
        self.db.migrate()
        self.event_bus = EventBus()
        self.ingestor = NewsIngestor(self.db, self.event_bus, interval_seconds=10)

    def teardown_method(self):
        if hasattr(self, 'db'):
            self.db = None
            
        import time
        time.sleep(0.1)
        
        if hasattr(self, 'db_path') and os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    @pytest.mark.anyio
    async def test_duplicate_events_ignored(self):
        article = {
            "headline": "Interest rate updates expected to trigger market move",
            "summary": "Inflation metrics print CPI estimates.",
            "url": "https://example.com/cpi-test"
        }
        
        # Process once
        await self.ingestor.process_article(article)
        initial_count = len(self.db.fetchall("SELECT * FROM news_events"))
        assert initial_count == 1
        
        # Process exact same article again
        await self.ingestor.process_article(article)
        new_count = len(self.db.fetchall("SELECT * FROM news_events"))
        assert new_count == 1 # Stays 1 due to deduplication

    @pytest.mark.anyio
    async def test_news_ingestion_modes(self):
        # 1. Test simulation mode (default)
        self.ingestor.settings_getter = lambda: type('Settings', (), {'use_news_simulation': True})()
        
        import unittest.mock as mock
        with mock.patch("random.random", return_value=0.0):
            articles = await self.ingestor._fetch_world_monitor_feed()
            assert len(articles) > 0
            assert "headline" in articles[0]
            assert "summary" in articles[0]

        # 2. Test live RSS mode
        self.ingestor.settings_getter = lambda: type('Settings', (), {'use_news_simulation': False})()
        articles = await self.ingestor._fetch_world_monitor_feed()
        assert isinstance(articles, list)
