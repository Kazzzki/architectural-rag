import os
from dotenv import load_dotenv

load_dotenv()

# Email Configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL", SENDER_EMAIL)

# Application Settings
SCHEDULE_TIME = "08:00"

# RSS Feeds List (Categorized)
RSS_FEEDS = {
    "AI (LLM/Model)": [
        {"name": "OpenAI Blog", "url": "https://openai.com/blog/rss.xml"},
        {"name": "Google AI Blog", "url": "http://feeds.feedburner.com/blogspot/gJZg"},
        {"name": "Microsoft AI", "url": "https://blogs.microsoft.com/ai/feed/"},
        {"name": "Hugging Face Blog", "url": "https://huggingface.co/blog/feed.xml"},
        {"name": "DeepMind Blog", "url": "https://deepmind.google/discover/blog/rss.xml"},
        {"name": "NVIDIA AI Blog", "url": "https://blogs.nvidia.com/feed/"},
        {"name": "BAIR Blog (Berkeley)", "url": "https://bair.berkeley.edu/blog/feed.xml"},
        {"name": "Unite.AI", "url": "https://www.unite.ai/feed/"},
        # Japanese
        {"name": "Zenn (AI Topic)", "url": "https://zenn.dev/topics/ai/feed"},
        {"name": "Qiita (AI Tag)", "url": "https://qiita.com/tags/AI/feed.atom"},
        {"name": "Fukabori.fm", "url": "https://rss.fukabori.fm/feed"}, 
    ],
    "AI (Business)": [
        {"name": "VentureBeat AI", "url": "https://venturebeat.com/category/ai/feed/"},
        {"name": "TechCrunch AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
        {"name": "MIT Tech Review", "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed"},
        {"name": "Reuters Technology", "url": "https://www.reutersagency.com/feed/?best-topics=tech&post_type=best"}, 
        {"name": "Bloomberg Technology", "url": "https://feeds.bloomberg.com/technology/news.xml"},
        {"name": "AI News", "url": "https://www.artificialintelligence-news.com/feed/rss/"},
        # Japanese
        {"name": "Ledge.ai", "url": "https://ledge.ai/feed"},
        {"name": "ITmedia AI+", "url": "https://rss.itmedia.co.jp/rss/2.0/aiplus.xml"},
        {"name": "AINOW", "url": "https://ainow.ai/feed/"},
        {"name": "Nikkei XTECH (AI)", "url": "https://xtech.nikkei.com/rss/xtech-it.rdf"},
    ],
    "AI (Drug Discovery)": [
        {"name": "Fierce Biotech", "url": "https://www.fiercebiotech.com/rss/xml"},
        {"name": "Drug Discovery World", "url": "https://www.ddw-online.com/feed/"},
        {"name": "Nature Biotechnology", "url": "http://feeds.nature.com/nbt/rss/current"},
        {"name": "ScienceDaily (Drug Discovery)", "url": "https://www.sciencedaily.com/rss/health_medicine/drug_discovery.xml"},
        # Japanese (General Bio/Tech)
        {"name": "Nikkei Biotech", "url": "https://bio.nikkeibp.co.jp/rss/index.rdf"},
    ],
    "AI (Construction)": [
        {"name": "Construction Dive", "url": "https://www.constructiondive.com/feeds/news/"},
        {"name": "BIM+", "url": "https://www.bimplus.co.uk/feed/"},
        {"name": "Global Construction Review", "url": "https://www.globalconstructionreview.com/feed/"},
        {"name": "Construction Tech Review", "url": "https://www.constructiontechreview.com/rss/"},
        # Japanese
        {"name": "BUILT (ITmedia)", "url": "https://rss.itmedia.co.jp/rss/2.0/built.xml"},
    ],
    "AI (Logistics)": [
        {"name": "Supply Chain Dive", "url": "https://www.supplychaindive.com/feeds/news/"},
        {"name": "Logistics Manager", "url": "https://www.logisticsmanager.com/feed/"},
        {"name": "FreightWaves", "url": "https://www.freightwaves.com/feed"},
        {"name": "SupplyChainBrain", "url": "https://www.supplychainbrain.com/rss/topic/202-artificial-intelligence-ai"},
        # Japanese
        {"name": "LNEWS", "url": "https://lnews.jp/feed/"},
    ],
    "Nuclear Fusion": [
        {"name": "World Nuclear News", "url": "https://www.world-nuclear-news.org/RSS/WNN-News.xml"},
        {"name": "ITER News", "url": "https://www.iter.org/rss/newsline"},
        {"name": "Fusion Energy Base", "url": "https://www.fusionenergybase.com/feed"},
        {"name": "Fusion Industry Assn", "url": "https://anchor.fm/s/2d6f2d50/podcast/rss"},
        # Japanese
        {"name": "QST (Quantum Science)", "url": "https://www.qst.go.jp/feed/press"},
    ],
    "Space": [
        {"name": "SpaceNews", "url": "https://spacenews.com/feed/"},
        {"name": "NASA Breaking News", "url": "https://www.nasa.gov/rss/dyn/breaking_news.rss"},
        {"name": "Space.com", "url": "https://www.space.com/feeds/all"},
        {"name": "ESA (European Space Agency)", "url": "https://www.esa.int/rssfeed/Our_Activities/Space_Engineering_Technology"},
        {"name": "Universe Today", "url": "https://www.universetoday.com/feed/"},
        # Japanese
        {"name": "JAXA Press", "url": "https://www.jaxa.jp/rss/press_j.rdf"},
        {"name": "Sorae", "url": "https://sorae.info/feed"},
    ]
}
