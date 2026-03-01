import asyncio
import json
from routers.research import generate_research_plan, ResearchGenerateRequest

async def main():
    request = ResearchGenerateRequest(
        node_id="test_node_1",
        node_label="基本設計フェーズの法規チェック",
        node_phase="基本設計",
        node_category="law",
        node_description="延床面積2000平米の事務所ビルの基本設計における建築基準法の適合性確認",
        node_checklist=["防火区画の確認", "避難階段の設置基準の確認"],
        node_deliverables=["法規チェックシート"],
        selected_tools=["Gemini Deep Research", "Claude web_fetch"],
        focus="避難規定と防火区画に特化して調査したい"
    )
    
    # generate_research_plan returns a StreamingResponse
    # The actual async generator is its body_iterator (in starlette StreamingResponse)
    response = generate_research_plan(request)
    
    print("=== Starting Stream ===")
    async for chunk in response.body_iterator:
        print(chunk.strip())
    print("=== Stream Ended ===")

if __name__ == "__main__":
    asyncio.run(main())
