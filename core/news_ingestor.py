"""
news_ingestor.py -- Asynchronous polling ingestor that monitors external news sources
(World Monitor feed) and processes them through classification, deduplication, and DB logging.
"""

import asyncio
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List
import requests

from core.database import Database
from core.event_bus import EventBus
from core.news_classifier import classify_event
from utils.logger import get_logger

log = get_logger("news_ingestor")

class NewsIngestor:
    def __init__(self, db: Database, event_bus: EventBus, interval_seconds: int = 30, settings_getter=None):
        self.db = db
        self.event_bus = event_bus
        self.interval_seconds = interval_seconds
        self.settings_getter = settings_getter
        self.seen_hashes = set()
        self.is_running = False
        self._task = None
        
        self._warm_dedup_cache()

    def _warm_dedup_cache(self):
        """Pre-populate seen hashes cache from existing database logs."""
        try:
            rows = self.db.fetchall("SELECT headline FROM news_events ORDER BY id DESC LIMIT 500")
            for row in rows:
                headline = row["headline"].strip()
                h_hash = hashlib.md5(headline.encode('utf-8')).hexdigest()
                self.seen_hashes.add(h_hash)
            log.info(f"News deduplication cache warmed up with {len(self.seen_hashes)} entries.")
        except Exception as e:
            log.warning(f"Could not warm deduplication cache (table might not exist yet): {e}")

    async def start(self) -> None:
        """Launch the background polling task."""
        if self.is_running:
            return
        self.is_running = True
        self._task = asyncio.create_task(self._poll_loop())
        log.info("News Ingestor service started successfully.")

    async def stop(self) -> None:
        """Gracefully stop the background polling task."""
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("News Ingestor service stopped.")

    async def _poll_loop(self) -> None:
        while self.is_running:
            try:
                articles = await self._fetch_world_monitor_feed()
                for article in articles:
                    if not self.is_running:
                        break
                    await self.process_article(article)
            except Exception as e:
                log.error(f"Error in news poll tick: {e}", exc_info=True)
                
            await asyncio.sleep(self.interval_seconds)

    async def _fetch_world_monitor_feed(self) -> List[Dict[str, Any]]:
        """
        Pulls recent news items from Yahoo Finance RSS feeds if live feed is enabled.
        Otherwise, returns simulated financial updates.
        """
        import random
        
        # Check settings
        use_simulation = True
        if self.settings_getter:
            try:
                settings = self.settings_getter()
                use_simulation = getattr(settings, "use_news_simulation", True)
            except Exception as e:
                log.warning(f"Failed to check settings_getter: {e}")
                
        # Generate dynamic mock pool
        mock_templates = [
            {
                "headline": "Geopolitical tensions rise as primary Middle East oil supply route experiences naval blockade",
                "summary": "Tensions intensified today following naval blockades along primary container and shipping routes, exposing crude oil markets.",
                "url": "https://example.com/geo-oil-route"
            },
            {
                "headline": "US Core CPI Print matches estimates, Fed policy decision rates expected to hold next week",
                "summary": "Core Consumer Price Index inflation rates remain flat. Markets project FOMC will keep current rates unchanged.",
                "url": "https://example.com/cpi-rates-usd"
            },
            {
                "headline": "RBI Governor hints at monetary policy rates hikes if Nifty inflation breaches target limits",
                "summary": "Reserve Bank of India warns of local liquidity tightening depending on inflation growth prints.",
                "url": "https://example.com/rbi-inflation-rates"
            },
            {
                "headline": "OPEC+ members agree to additional voluntary crude oil production cuts",
                "summary": "OPEC+ members agree to cut oil supply by 1.5 million barrels per day starting next month to support market stability.",
                "url": "https://example.com/opec-cuts"
            },
            {
                "headline": "Dovish Fed comments suggest rate easing cycle may begin earlier than expected",
                "summary": "Federal Reserve officials hint at potential interest rate cuts later this year if inflation continues its downward trajectory.",
                "url": "https://example.com/fed-dovish-easing"
            },
            {
                "headline": "Escalating tensions in the Middle East drive heavy safe-haven demand for Gold bullion",
                "summary": "A sudden escalation of geopolitical conflict has sparked a global flight to safety, sending spot gold prices to new intraday highs.",
                "url": "https://example.com/gold-safe-haven"
            },
            {
                "headline": "10-Year US Treasury yields surge to new yearly highs",
                "summary": "Treasury yields spike following stronger-than-expected economic growth data, applying pressure to non-yielding gold assets.",
                "url": "https://example.com/treasury-yields-spike"
            },
            {
                "headline": "India trade deficit widens as gold imports surge ahead of major festive season",
                "summary": "The Ministry of Commerce reported a substantial increase in gold imports, putting negative pressure on the USD/INR currency pair.",
                "url": "https://example.com/india-trade-deficit"
            },
            {
                "headline": "Severe port congestion and logistical blockades raise global inflation concerns",
                "summary": "Global supply chain disruptions intensify as major shipping ports experience severe delays, boosting commodity pricing pressure.",
                "url": "https://example.com/supply-chain-blockade"
            },
            {
                "headline": "European Central Bank announces surprise 25 bps rate cut to bolster Eurozone growth",
                "summary": "The ECB lowering its benchmark interest rates surprised economists, signaling concerns over slowing regional macroeconomic momentum.",
                "url": "https://example.com/ecb-rate-cut"
            },
            {
                "headline": "US Non-Farm Payrolls exceed forecasts by a wide margin, reinforcing USD strength",
                "summary": "The US labor market added 275,000 jobs last month, far exceeding expectations and locking in hawkish rate expectations for the greenback.",
                "url": "https://example.com/nfp-strong-usd"
            },
            {
                "headline": "Major gold mine strikes in South Africa tighten global physical bullion supply",
                "summary": "Industry representatives warn of prolonged shutdowns at major operations, creating immediate price support for physical gold.",
                "url": "https://example.com/gold-mine-strikes"
            }
        ]

        def get_randomized_mock():
            evt = random.choice(mock_templates).copy()
            if "cpi-rates-usd" in evt["url"]:
                cpi_val = round(random.uniform(2.8, 4.2), 1)
                evt["headline"] = f"US Core CPI Print registers at {cpi_val}%, Fed policy rates expected to hold"
                evt["summary"] = f"Core Consumer Price Index inflation rates printed at {cpi_val}% annually. Markets project FOMC will keep rates unchanged."
            elif "opec-cuts" in evt["url"]:
                cut_val = round(random.uniform(0.5, 2.0), 1)
                evt["headline"] = f"OPEC+ members agree to voluntary crude oil cuts of {cut_val}M bpd"
                evt["summary"] = f"OPEC+ members agree to cut oil supply by {cut_val} million barrels per day starting next month to support market stability."
            elif "treasury-yields-spike" in evt["url"]:
                yield_val = round(random.uniform(4.2, 5.1), 2)
                evt["headline"] = f"10-Year US Treasury yields surge to {yield_val}% yearly highs"
                evt["summary"] = f"Treasury yields spike to {yield_val}% following stronger-than-expected economic growth data, applying pressure to gold assets."
            return evt

        if not use_simulation:
            articles = []
            urls = [
                "https://finance.yahoo.com/rss/headlines?s=GC=F",
                "https://finance.yahoo.com/rss/headlines?s=DX-Y.NYB"
            ]
            loop = asyncio.get_event_loop()
            for url in urls:
                try:
                    response = await loop.run_in_executor(
                        None,
                        lambda u=url: requests.get(u, timeout=5.0)
                    )
                    if response.status_code == 200:
                        import xml.etree.ElementTree as ET
                        root = ET.fromstring(response.content)
                        for item in root.findall(".//item"):
                            title_el = item.find("title")
                            desc_el = item.find("description")
                            link_el = item.find("link")
                            
                            headline = title_el.text.strip() if title_el is not None and title_el.text else ""
                            summary = desc_el.text.strip() if desc_el is not None and desc_el.text else ""
                            link = link_el.text.strip() if link_el is not None and link_el.text else ""
                            
                            if headline:
                                articles.append({
                                    "headline": headline,
                                    "summary": summary,
                                    "url": link
                                })
                except Exception as e:
                    log.debug(f"Failed to fetch or parse RSS from {url}: {e}")
            
            if articles:
                return articles
            else:
                log.debug("No live articles fetched from RSS. Falling back to simulated news feed.")

        # In simulation mode or as a fallback when RSS is empty, generate simulated feed items
        if random.random() < 0.20:
            return [get_randomized_mock()]
            
        return []

    async def process_article(self, article: Dict[str, Any]) -> None:
        headline = article.get("headline", "").strip()
        if not headline:
            return

        # Deduplicate using MD5 hashing
        h_hash = hashlib.md5(headline.encode('utf-8')).hexdigest()
        if h_hash in self.seen_hashes:
            return
        self.seen_hashes.add(h_hash)

        # Classify the article impact
        classification = classify_event(article)
        sentiment = classification["sentiment"]
        impact = classification["impact_score"]
        target = classification["target_market"]
        horizon = classification["horizon_hours"]
        confidence = classification["confidence"]
        summary = classification["summary"]

        # Store logged alert in SQLite DB
        try:
            self.db.execute("""
                INSERT INTO news_events (
                    timestamp, headline, summary, source_url, sentiment, 
                    impact_score, confidence, target_market, horizon_hours
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now(timezone.utc).isoformat(),
                headline,
                summary,
                article.get("url"),
                sentiment,
                impact,
                confidence,
                target,
                horizon
            ))
        except Exception as e:
            log.error(f"Failed to record news event to DB: {e}")

        # Broadcast update to the EventBus (WebSockets broadcaster will pick this up)
        try:
            self.event_bus.publish("NEWS_ALERT", {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "headline": headline,
                "summary": summary,
                "source_url": article.get("url"),
                "sentiment": sentiment,
                "impact_score": impact,
                "target_market": target,
                "confidence": confidence,
                "horizon_hours": horizon
            })
        except Exception as e:
            log.error(f"Failed to publish news event to EventBus: {e}")
