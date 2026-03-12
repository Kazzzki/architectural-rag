import time
import schedule
import argparse
import sys
from datetime import datetime
import config
import fetcher
import summarizer
import emailer

def job():
    print(f"\n--- Starting Job at {datetime.now()} ---")
    
    # 1. Fetch News
    news = fetcher.fetch_news(config.RSS_FEEDS)
    
    if not news:
        print("No news found today.")
        # Optional: Send an email saying "No news" or just skip
        # emailer.send_email("AI News Digest: Nothing New Today", "<p>Quiet day in AI.</p>")
        return

    # 2. Summarize (Format)
    html_body = summarizer.summarize_news(news)
    
    # 3. Send Email
    subject = f"【日刊】AIニュースダイジェスト - {datetime.now().strftime('%Y-%m-%d')}"
    emailer.send_email(subject, html_body)
    
    print("--- Job Finished ---\n")

def run_scheduler():
    print(f"Scheduler started. Task set for {config.SCHEDULE_TIME} daily.")
    schedule.every().day.at(config.SCHEDULE_TIME).do(job)
    
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI News Aggregator & Emailer")
    parser.add_argument("--run-now", action="store_true", help="Run the job immediately and exit")
    args = parser.parse_args()
    
    if args.run_now:
        job()
    else:
        run_scheduler()
