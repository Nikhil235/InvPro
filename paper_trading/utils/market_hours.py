from datetime import datetime, timezone

def is_market_open(dt: datetime = None) -> bool:
    """
    Checks if the XAU/USD market is open at the given UTC time.
    XAU/USD trading hours:
    - Opens: Sunday 22:00 UTC
    - Closes: Friday 21:00 UTC
    - Daily break: Monday-Thursday 21:00 UTC to 22:00 UTC
    """
    if dt is None:
        dt = datetime.now(timezone.utc)
    
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
        
    weekday = dt.weekday() # Monday = 0, Sunday = 6
    hour = dt.hour
    
    # Weekend fully closed: Friday 21:00 to Sunday 22:00
    if weekday == 4 and hour >= 21: # Friday after 21:00
        return False
    if weekday == 5: # Saturday
        return False
    if weekday == 6 and hour < 22: # Sunday before 22:00
        return False
        
    # Daily break: 21:00 to 22:00
    if hour == 21:
        return False
        
    return True
