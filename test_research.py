import json
import logging
import requests
import os
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load credentials
load_dotenv()
password = os.getenv("APP_PASSWORD")

# Use localhost endpoint with Basic Auth
URL = "http://127.0.0.1:8000"
auth = ("admin", password)

def test_research_planner():
    # 1. Fetch nodes
    logger.info("Fetching /api/research/nodes...")
    res = requests.get(f"{URL}/api/research/nodes", auth=auth)
    res.raise_for_status()
    nodes = res.json()
    logger.info(f"Nodes retrieved: {len(nodes)}")
    
    # Take first node (Ingestion)
    node = nodes[0]
    
    # 2. Call generation
    logger.info(f"Generating research plan for node: {node['id']}")
    payload = {
        "node_id": node["id"],
        "node_label": node["label"],
        "node_desc": node["description"],
        "node_components": node["components"],
        "node_domains": node["domains"],
        "search_category": "rag_ingestion",
        "doc_type": "spec",
        "selected_tools": ["Gemini Deep Research", "Perplexity Pro"],
        "focus": "Automating prompt testing",
        "extra_context": ""
    }
    
    # Stream the response
    res = requests.post(f"{URL}/api/research/generate", json=payload, auth=auth, stream=True)
    res.raise_for_status()
    
    full_text = ""
    for line in res.iter_lines():
        if line:
            decoded_line = line.decode('utf-8')
            if decoded_line.startswith('data: ') and decoded_line != 'data: [DONE]':
                try:
                    data = json.loads(decoded_line[6:])
                    if data["type"] == "chunk":
                        full_text += data["data"]
                    elif data["type"] == "parsed":
                        logger.info("Received final parsed output chunk.")
                except Exception as e:
                    pass

    logger.info("--- Generated Text Start ---")
    logger.info(full_text[:500] + "...\n(truncated)")
    logger.info("--- Generated Text End ---")
    
    # Extremely simple regex validation
    import re
    if "---GAP_ANALYSIS---" in full_text and "---TOOL_INSTRUCTIONS---" in full_text:
        logger.info("[SUCCESS] Output formatting matched expected structure.")
        
test_research_planner()
