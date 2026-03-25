import os
import hashlib
import json
import time
import google.generativeai as genai
from typing import List, Dict, Any, Optional

# Configure Gemini
# Assumes GEMINI_API_KEY is set in environment (e.g. via .env loaded in main.py)
# If not, we might need to load it here or assume caller handles it.
# For robustness, we'll try to configure it if key is present.
API_KEY = os.environ.get("GEMINI_API_KEY")
if API_KEY:
    genai.configure(api_key=API_KEY)

def generate_node_id(filename: str, label: str) -> str:
    raw = f"{filename}:{label}"
    return hashlib.md5(raw.encode('utf-8')).hexdigest()

class LLMAgent:
    def __init__(self):
        self.model = genai.GenerativeModel(
            model_name='gemini-3-flash-preview',
            generation_config={"response_mime_type": "application/json"}
        )

    def analyze_file(self, filepath: str) -> List[Dict[str, Any]]:
        filename = os.path.basename(filepath)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(f"Error reading {filepath}: {e}")
            return []
        
        if not API_KEY:
            print("WARNING: GEMINI_API_KEY not set. Using mock data.")
            return self._mock_analyze(filename)

        prompt = f"""
        You are a project manager assistant. Analyze the following note content.
        Extract key "Facts" and "Issues". 
        For each item, assign a priority score (0.0 to 1.0) based on importance/risk.
        
        Output strictly valid JSON in this format:
        [
            {{ "label": "description", "category": "Fact" or "Issue", "priority": 0.1 to 1.0 }}
        ]

        Note Content:
        {content}
        """

        try:
            response = self.model.generate_content(prompt)
            items = json.loads(response.text.strip())
            
            nodes = []
            for item in items:
                label = item.get("label", "Unknown")
                category = item.get("category", "General")
                priority = float(item.get("priority", 0.5))
                
                node_id = generate_node_id(filename, label)
                
                nodes.append({
                    "id": node_id,
                    "type": "issueNode",
                    "position": {"x": 0, "y": 0}, # Layout handled by frontend
                    "data": {
                        "label": label,
                        "priority": priority,
                        "source_file": filename,
                        "category": category,
                        "user_decision": "",
                        "is_user_edited": False
                    }
                })
            return nodes

        except Exception as e:
            print(f"Gemini API Error: {e}")
            # Fallback to mock if API fails? Or return empty.
            return []

    def analyze_text(self, text: str, source_label: str) -> List[Dict[str, Any]]:
        """Bug3 fix: analyze raw text (e.g. from voice input) instead of a file."""
        if not API_KEY:
            return self._mock_analyze(source_label)

        prompt = f"""
        You are a project manager assistant. Analyze the following text.
        Extract key "Facts" and "Issues".
        For each item, assign a priority score (0.0 to 1.0) based on importance/risk.

        Output strictly valid JSON in this format:
        [
            {{ "label": "description", "category": "Fact" or "Issue", "priority": 0.1 to 1.0 }}
        ]

        Text:
        {text}
        """

        try:
            response = self.model.generate_content(prompt)
            items = json.loads(response.text.strip())
            nodes = []
            for item in items:
                label = item.get("label", "Unknown")
                category = item.get("category", "General")
                priority = float(item.get("priority", 0.5))
                node_id = generate_node_id(source_label, label)
                nodes.append({
                    "id": node_id,
                    "type": "issueNode",
                    "position": {"x": 0, "y": 0},
                    "data": {
                        "label": label,
                        "priority": priority,
                        "source_file": source_label,
                        "category": category,
                        "user_decision": "",
                        "is_user_edited": False,
                    },
                })
            return nodes
        except Exception as e:
            print(f"Gemini API Error (analyze_text): {e}")
            return []

    def chat(self, message: str, node_id: Optional[str], graph: Dict) -> str:
        """Bug3 fix: chat with Gemini, optionally in context of a specific node."""
        if not API_KEY:
            return f"[Mock] Received: {message}"

        # Build context from graph node if provided
        context = ""
        if node_id:
            for node in graph.get("nodes", []):
                if node["id"] == node_id:
                    d = node["data"]
                    context = (
                        f"Context node — Label: {d.get('label')}, "
                        f"Category: {d.get('category')}, "
                        f"Priority: {d.get('priority')}, "
                        f"Decision: {d.get('user_decision') or 'none yet'}."
                    )
                    break

        # Use a plain text model (no JSON response_mime_type for chat)
        chat_model = genai.GenerativeModel(model_name='gemini-3-flash-preview')
        prompt = f"{context}\n\nUser: {message}" if context else message
        try:
            response = chat_model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            print(f"Gemini API Error (chat): {e}")
            return f"Error: {e}"

    def _mock_analyze(self, filename):
        # Fallback for testing without keys
        return [
            {
                "id": generate_node_id(filename, f"Mock Fact from {filename}"),
                "type": "issueNode",
                "position": {"x": 0, "y": 0},
                "data": {
                    "label": f"Mock Fact from {filename}",
                    "priority": 0.5,
                    "source_file": filename,
                    "category": "Fact",
                    "user_decision": "",
                    "is_user_edited": False
                }
            }
        ]
