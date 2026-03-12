from flask import Flask, render_template, jsonify, request
import config
import fetcher
import translator
import summarizer
import emailer
from datetime import datetime

import threading
import time
import schedule
from datetime import datetime
import json

app = Flask(__name__)
PORT = 5001

# Global Cache
news_cache = {
    "articles": [],
    "last_updated": None,
    "is_updating": False
}

def update_news_cache():
    """Background task to fetch and translate news."""
    global news_cache
    if news_cache["is_updating"]:
        print("Update already in progress, skipping...")
        return

    print("--- Starting Background News Update ---")
    news_cache["is_updating"] = True
    try:
        # Fetch raw news
        news = fetcher.fetch_news(config.RSS_FEEDS)
        
        # Sort by date
        news.sort(key=lambda x: x['_pub_date_obj'], reverse=True)
        
        # Limit to 30
        news = news[:30]
        
        # Translate
        translated_news = []
        for item in news:
            translated_item = item.copy()
            if '_pub_date_obj' in translated_item:
                del translated_item['_pub_date_obj']
            
            # Translation could be slow, that's why we are here
            translated_item['title'] = translator.translate_text(item['title'])
            translated_item['summary'] = translator.translate_text(item['summary'])
            translated_news.append(translated_item)
            
        # Update Cache
        news_cache["articles"] = translated_news
        news_cache["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"--- Cache Updated at {news_cache['last_updated']} ({len(translated_news)} articles) ---")
        
    except Exception as e:
        print(f"Error updating cache: {e}")
    finally:
        news_cache["is_updating"] = False

def run_schedule():
    """Runs the schedule loop."""
    print("Scheduler thread started...")
    # Initial fetch on startup
    update_news_cache()
    
    # Schedule every 60 minutes
    schedule.every(60).minutes.do(update_news_cache)
    
    while True:
        schedule.run_pending()
        time.sleep(1)

# Start background thread
scheduler_thread = threading.Thread(target=run_schedule, daemon=True)
scheduler_thread.start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/fetch', methods=['POST'])
def fetch_news_api():
    """
    Returns cached news immediately.
    Optional query param ?force=true to trigger immediate update.
    """
    force = request.args.get('force') == 'true'
    
    if force:
        # Trigger update in background if not running, but for UI feedback we might want to wait?
        # Alternatively, we can run it synchronously for "Force Refresh"
        if not news_cache["is_updating"]:
            # Run synchronously for force refresh so user sees result
            update_news_cache()
    
    return jsonify({
        "status": "success",
        "articles": news_cache["articles"],
        "last_updated": news_cache["last_updated"],
        "is_updating": news_cache["is_updating"]
    })

@app.route('/api/send-email', methods=['POST'])
def send_email_api():
    try:
        data = request.json
        articles = data.get('articles', [])
        
        if not articles:
            return jsonify({"status": "error", "message": "No articles to send"}), 400
            
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
