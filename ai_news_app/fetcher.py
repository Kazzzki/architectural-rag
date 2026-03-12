import feedparser
from datetime import datetime, timedelta, timezone
from dateutil import parser
import time

def get_publish_date(entry):
    """
    Attempts to parse the published date of an RSS entry.
    Returns a timezone-aware datetime object or current time if parsing fails.
    """
    if hasattr(entry, 'published'):
        try:
            dt = parser.parse(entry.published)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            pass
            
    if hasattr(entry, 'updated'):
        try:
            dt = parser.parse(entry.updated)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            pass
            
    # Fallback to current time if no date found (so we don't miss it if it's fresh but badly formatted, 
    # though filtering logic might exclude it if we were strict. 
    # For now, let's treat current time as a fallback but maybe print a warning)
    return datetime.now(timezone.utc)

def fetch_news(feeds_config):
    """
    Fetches news from the provided configuration.
    Handles 'feeds_config' as a dictionary of categories -> list of feeds.
    
    Returns:
        list: A flat list of all news items, each with a 'category' field.
    """
    all_news_items = []
    # Capture news from the last 3 days (72 hours) to ensure niche topics are covered
    cutoff_time = datetime.now(timezone.utc) - timedelta(days=3)
    
    # Check if feeds_config is a dict (Categorized) or list (Old format)
    if isinstance(feeds_config, list):
        # Fallback for old compatibility or simple list
        categories = {"General": feeds_config}
    else:
        categories = feeds_config

    print(f"Fetching news from {len(categories)} categories (Last 3 days)...")
    
    # User-Agent to mimic a browser and avoid being blocked by some RSS servers
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    for category, feeds in categories.items():
        print(f"--- Category: {category} ---")
        for feed in feeds:
            try:
                print(f"Checking {feed['name']}...")
                # feedparser can take a dictionary of request_headers
                # Note: 'agent' param is deprecated in some versions, requests is safer if feedparser supports it,
                # but standard feedparser.parse(url, request_headers=...) works for URL handling.
                parsed_feed = feedparser.parse(feed['url'], request_headers=headers)
                
                if parsed_feed.bozo:
                    print(f"  Warning: Potential issue with feed {feed['name']} (Bozo: {parsed_feed.bozo_exception})")
                
                # Check for empty entries (often means blocking/parsing failure)
                if not parsed_feed.entries:
                    print(f"  No entries found in {feed['name']}. Might be blocked or empty.")
                
                for entry in parsed_feed.entries:
                    pub_date = get_publish_date(entry)
                    
                    if pub_date > cutoff_time:
                        item = {
                            "category": category,
                            "source": feed['name'],
                            "title": entry.title,
                            "link": entry.link,
                            "summary": getattr(entry, 'summary', 'No summary available.'),
                            "published": pub_date.strftime("%Y-%m-%d %H:%M"),
                            # Store raw date for sorting
                            "_pub_date_obj": pub_date
                        }
                        all_news_items.append(item)
                        
            except Exception as e:
                print(f"  Error fetching {feed['name']}: {e}")
            
    print(f"Found {len(all_news_items)} total recent articles.")
    return all_news_items
