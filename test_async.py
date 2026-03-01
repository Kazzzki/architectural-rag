import asyncio
from gemini_client import get_client
from config import GEMINI_MODEL_RAG

async def main():
    try:
        client = get_client()
        response = await client.aio.models.generate_content(
            model=GEMINI_MODEL_RAG,
            contents="hello",
        )
        print("Success:", response.text)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(main())
