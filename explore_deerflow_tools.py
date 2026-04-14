import asyncio
from tools.browser_ops import browser_navigate, browser_extract_text, browser_close

async def main():
    try:
        # Navigate to the tools directory of DeerFlow
        print("Exploring DeerFlow Tools directory...")
        res = await browser_navigate("https://github.com/bytedance/deer-flow/tree/main/src/deerflow/tools")
        print(res)
        
        text = await browser_extract_text()
        print("\n--- TOOLS STRUCTURE ---\n")
        print(text)
        print("\n--- END STRUCTURE ---\n")
        
    finally:
        await browser_close()

if __name__ == "__main__":
    asyncio.run(main())
