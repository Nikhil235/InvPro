"""
news_classifier.py -- Rule-based NLP classifier for financial news impact.
Classifies incoming headlines and articles for market relevance, sentiment impact,
target asset targets, and timeframe horizons.
"""

from typing import Dict, Any

# Keyword groups to search for in headlines/text (case-insensitive)
KEYWORDS_GOLD = {"gold", "xau", "safe-haven", "bullion", "precious metal"}
KEYWORDS_USD = {"usd", "dollar", "fed", "fomc", "powell", "treasury", "greenback"}
KEYWORDS_INR = {"india", "rbi", "rupee", "inr", "nifty", "mumbai"}
KEYWORDS_OIL = {"oil", "crude", "brent", "wti", "opec", "energy", "gasoline"}
KEYWORDS_RATES = {"rates", "interest rate", "yield", "hike", "cut", "tightening", "easing"}
KEYWORDS_GEOPOLITICS = {
    "war", "sanction", "tariffs", "strike", "conflict", "escalation", "military",
    "missile", "tensions", "nato", "russia", "china", "iran", "israel", "middle east",
    "geopolitical", "threat", "blockade", "nuclear"
}
KEYWORDS_INFLATION = {"inflation", "cpi", "ppi", "pce", "price index"}

def classify_event(article: Dict[str, Any]) -> Dict[str, Any]:
    """
    Classify the market impact of an article.
    
    Returns:
        Dict containing:
            sentiment: BULLISH / BEARISH / VOLATILITY_SPIKE / RISK_OFF / NEUTRAL
            impact_score: HIGH / MEDIUM / LOW
            confidence: float (0.0 to 1.0)
            target_market: str (e.g., Gold, USD, Oil, USD/INR, Macro)
            horizon_hours: int
            summary: str
    """
    headline = article.get("headline", "").lower()
    summary_text = article.get("summary", "").lower()
    text = f"{headline} {summary_text}"
    
    # Calculate word presence
    has_gold = any(w in text for w in KEYWORDS_GOLD)
    has_usd = any(w in text for w in KEYWORDS_USD)
    has_inr = any(w in text for w in KEYWORDS_INR)
    has_oil = any(w in text for w in KEYWORDS_OIL)
    has_rates = any(w in text for w in KEYWORDS_RATES)
    has_geo = any(w in text for w in KEYWORDS_GEOPOLITICS)
    has_inf = any(w in text for w in KEYWORDS_INFLATION)

    sentiment = "NEUTRAL"
    impact_score = "LOW"
    target_market = "Macro"
    confidence = 0.50
    horizon_hours = 12
    summary = "No high-impact financial keywords detected."

    # Classification Rules (Heuristic Priority)
    if has_geo:
        sentiment = "RISK_OFF"
        impact_score = "HIGH"
        target_market = "Gold" if has_gold else "Gold / Oil" if has_oil else "Gold"
        confidence = 0.85
        horizon_hours = 48
        summary = "Geopolitical escalation or risk-off event detected. Safe-haven assets may see bullish inflows."
    elif has_rates and has_usd:
        sentiment = "VOLATILITY_SPIKE"
        impact_score = "HIGH"
        target_market = "USD"
        confidence = 0.80
        horizon_hours = 24
        summary = "Federal Reserve rate policy update or yield event. Expect volatility spikes in USD pairs."
    elif has_inf:
        sentiment = "VOLATILITY_SPIKE"
        impact_score = "HIGH"
        target_market = "Gold / USD"
        confidence = 0.75
        horizon_hours = 24
        summary = "Inflation print (CPI/PPI) or policy decision. Safe-havens and USD pairs exposed to volatility."
    elif has_oil:
        sentiment = "BULLISH" if any(w in text for w in ["tighten", "cut", "sanction", "blockade", "disruption"]) else "VOLATILITY_SPIKE"
        impact_score = "MEDIUM"
        target_market = "Oil"
        confidence = 0.70
        horizon_hours = 48
        summary = "Crude oil market event. Watch commodity volatility and energy indexes."
    elif has_inr:
        sentiment = "VOLATILITY_SPIKE"
        impact_score = "MEDIUM"
        target_market = "USD/INR"
        confidence = 0.75
        horizon_hours = 12
        summary = "India macro update or RBI policy action. Local currency pairs exposed."
    elif has_gold:
        sentiment = "BULLISH" if any(w in text for w in ["soar", "rally", "rise", "support"]) else "NEUTRAL"
        impact_score = "MEDIUM"
        target_market = "Gold"
        confidence = 0.70
        horizon_hours = 24
        summary = "Direct Gold bullion news or spot price movements."

    return {
        "sentiment": sentiment,
        "impact_score": impact_score,
        "target_market": target_market,
        "confidence": confidence,
        "horizon_hours": horizon_hours,
        "summary": summary
    }
