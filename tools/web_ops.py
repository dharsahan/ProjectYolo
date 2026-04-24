import httpx
from bs4 import BeautifulSoup  # type: ignore
from duckduckgo_search import DDGS
from tools.base import audit_log

MAX_BROWSE_TEXT_CHARS = 8000


def web_search(query: str) -> str:
    """Search the internet for real-time information."""
    try:
        results = []
        # Increase timeout and handle potential DDG rate limiting
        with DDGS(timeout=20) as ddgs:
            # We use text search which is generally more stable
            ddgs_gen = ddgs.text(query, max_results=8)
            for r in ddgs_gen:
                results.append(
                    f"Title: {r['title']}\nURL: {r['href']}\nSnippet: {r['body']}\n"
                )

        if not results:
            # If DDG fails or is empty, suggest using the browser directly
            audit_log("web_search", {"query": query}, "warning", "No results found")
            return "No search results found via API. Please use `browser_navigate` to search on Google or Bing directly."

        output = "\n".join(results)
        audit_log("web_search", {"query": query}, "success")
        return output
    except Exception as e:
        audit_log("web_search", {"query": query}, "error", str(e))
        return f"Error performing web search via API: {e}. Suggestion: Use `browser_navigate` to perform a manual search."


def browse_url(url: str) -> str:
    """Fetch and extract text content from a specific URL."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        with httpx.Client(follow_redirects=True, timeout=20.0) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        for script_or_style in soup(["script", "style", "header", "footer", "nav"]):
            script_or_style.extract()

        text = soup.get_text(separator="\n")
        lines = (line.strip() for line in text.splitlines())
        clean_text = "\n".join(line for line in lines if line)

        result = clean_text[:MAX_BROWSE_TEXT_CHARS]
        audit_log("browse_url", {"url": url}, "success")
        return result
    except Exception as e:
        audit_log("browse_url", {"url": url}, "error", str(e))
        return f"Error browsing URL: {e}. Suggestion: Use `browser_navigate` for a visual session if this fetch failed."
