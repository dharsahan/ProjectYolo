import asyncio
from tools.browser_ops import browser_navigate, browser_extract_text, browser_close

async def main():
    try:
        print("Navigating to Mem0 GitHub...")
        res = await browser_navigate("https://github.com/mem0ai/mem0")
        print(res)
        
        text = await browser_extract_text()
        print("\n--- CONTENT ---\n")
        print(text)
        print("\n--- END CONTENT ---\n")
        
    finally:
        await browser_close()

if __name__ == "__main__":
    asyncio.run(main())
