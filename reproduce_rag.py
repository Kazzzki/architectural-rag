
import sys
import os
import asyncio
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

# Mock settings
class MockSettings:
    def get_api_key(self):
        return os.environ.get("GEMINI_API_KEY")
    
    def get_analysis_model(self):
        return "gemini-3-flash-preview"

sys.modules["mindmap.api_settings"] = MockSettings()

# Import the function to test
from mindmap.router import ai_action_endpoint, AIActionRequest

async def test_rag():
    print("Testing RAG action...")
    req = AIActionRequest(
        action="rag",
        nodeId="test_node",
        content="鉄骨工事の安全基準",
        context={}
    )
    
    try:
        result = await ai_action_endpoint(req)
        with open("rag_result.txt", "w") as f:
            f.write(str(result))
        print("Result written to rag_result.txt")
    except Exception as e:
        with open("rag_result.txt", "w") as f:
            f.write(f"Error: {e}")
        print("Error:", e)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(test_rag())
