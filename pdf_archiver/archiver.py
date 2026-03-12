import asyncio
import os
from google import genai
from google.genai import types
from playwright.async_api import async_playwright
from slugify import slugify
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Configuration
INPUT_FILE = "urls.txt"

class Archiver:
    def __init__(self, download_dir="downloads", temp_dir="temp_pdfs", model_id="gemini-3-flash-preview"):
        self.download_dir = download_dir
        self.temp_dir = temp_dir
        self.model_id = model_id
        self.client = genai.Client(api_key=GEMINI_API_KEY)
        
        # Ensure directories exist
        if not os.path.exists(self.download_dir): os.makedirs(self.download_dir)
        if not os.path.exists(self.temp_dir): os.makedirs(self.temp_dir)

    async def generate_title_from_pdf(self, pdf_path):
        try:
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()
            
            prompt = """
            Analyze this document. Identify the title, the main topic, and the date if available.
            Generate a concise filename in the format: YYYY-MM-DD_Title.pdf
            If date is unknown, use TODAY's date (e.g. 2026-01-06).
            The Title's language should match the document's language.
            Return ONLY the filename. Nothing else.
            """
            
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=[prompt, types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")]
            )
            
            filename = response.text.strip().replace(".pdf", "")
            # Remove any markdown formatting if present
            filename = filename.replace("```", "").strip()
            return slugify(filename, allow_unicode=True) + ".pdf"
            
        except Exception as e:
            print(f"Error generating title for {pdf_path}: {e}")
            return f"Unknown_{os.path.basename(pdf_path)}"

    async def process_url(self, url, browser, callback=None):
        print(f"Processing: {url}")
        if callback: callback("processing", url=url)
        
        # Use a context with proper User-Agent to avoid being blocked
        context = await browser.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        page = await context.new_page()
        
        temp_filename = f"temp_{slugify(url)}.pdf"
        temp_path = os.path.join(self.temp_dir, temp_filename)
        
        try:
            # Navigate with longer timeout (60s)
            await page.goto(url, wait_until="networkidle", timeout=60000)
            
            if url.lower().endswith(".pdf"):
                 # Direct PDF download
                 import aiohttp
                 headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
                 async with aiohttp.ClientSession(headers=headers) as session:
                     async with session.get(url) as resp:
                         if resp.status == 200:
                             with open(temp_path, 'wb') as f:
                                 f.write(await resp.read())
                             print(f"Downloaded PDF to {temp_path}")
                         else:
                             raise Exception(f"Failed to download PDF: {resp.status}")
            else:
                # HTML to PDF
                await page.emulate_media(media="screen")
                await page.pdf(path=temp_path, format="A4", print_background=True)
                print(f"Saved PDF to {temp_path}")
            
            # Generate Title (Common for both)
            if callback: callback("analyzing", url=url)
            new_filename = await self.generate_title_from_pdf(temp_path)
            final_path = os.path.join(self.download_dir, new_filename)
            
            # Rename/Move
            os.rename(temp_path, final_path)
            print(f"✅ Saved as: {final_path}")
            
            if callback: callback("completed", url=url, filename=new_filename)
            return {"url": url, "filename": new_filename} # Ensure return dict for results

        except Exception as e:
            print(f"❌ Failed to process {url}: {e}")
            if callback: callback("failed", url=url, error=str(e))
            return {"url": url, "error": str(e)}
        finally:
            await context.close() # Close context instead of page
            # Cleanup temp if exists
            if os.path.exists(temp_path):
                try:
                   os.remove(temp_path)
                except:
                   pass

    async def run_urls_async(self, urls, callback=None):
        # Limit concurrency to 5 to avoid timeouts/blocking
        semaphore = asyncio.Semaphore(5)
        
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            
            async def bounded_process(url):
                async with semaphore:
                    return await self.process_url(url, browser, callback)

            tasks = [bounded_process(url) for url in urls]
            results = await asyncio.gather(*tasks)
            await browser.close()
            return results

    def run_batch(self, urls, callback=None):
        """Sync wrapper for async execution"""
        return asyncio.run(self.run_urls_async(urls, callback))

# CLI Entrypoint
if __name__ == "__main__":
    if not os.path.exists(INPUT_FILE):
        print(f"Please create {INPUT_FILE} with URLs.")
    else:
        with open(INPUT_FILE, "r") as f:
            urls = [line.strip() for line in f if line.strip()]
        
        archiver = Archiver()
        archiver.run_batch(urls)
