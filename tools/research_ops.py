import json
import re
from pathlib import Path
from typing import Dict, List
from urllib.parse import urlparse

from tools.base import YOLO_RESEARCH_FILE, audit_log

RESEARCH_STATE_FILE = YOLO_RESEARCH_FILE

LOW_SIGNAL_PATH_TOKENS = {
    "login",
    "signin",
    "signup",
    "register",
    "account",
    "privacy",
    "terms",
    "cookies",
    "cookie-policy",
    "about",
    "contact",
}

BINARY_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".webp",
    ".mp4",
    ".mp3",
    ".zip",
    ".tar",
    ".gz",
    ".exe",
    ".dmg",
}

STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "about",
    "into",
    "your",
    "their",
    "latest",
}


def _extract_topic_tokens(topic_hint: str) -> List[str]:
    if not topic_hint:
        return []
    tokens = re.findall(r"[a-zA-Z0-9]{3,}", topic_hint.lower())
    dedup = []
    seen = set()
    for token in tokens:
        if token in STOPWORDS or token in seen:
            continue
        seen.add(token)
        dedup.append(token)
    return dedup


def _is_high_signal_link(url: str, text: str, topic_tokens: List[str]) -> tuple[bool, str]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False, "unsupported_scheme"

    path = parsed.path.lower()
    if any(path.endswith(ext) for ext in BINARY_EXTENSIONS):
        return False, "binary_asset"

    path_parts = {part for part in path.split("/") if part}
    if path_parts.intersection(LOW_SIGNAL_PATH_TOKENS):
        return False, "low_signal_page"

    if topic_tokens:
        haystack = f"{url} {text}".lower()
        if not any(token in haystack for token in topic_tokens):
            return False, "topic_mismatch"

    return True, "ok"


def research_enqueue_from_crawl_step(
    crawl_step_output: str,
    topic_hint: str = "",
    max_urls: int = 25,
) -> str:
    """Parse crawl-step JSON, filter low-signal links, and enqueue high-quality URLs."""
    if max_urls <= 0:
        return "Error: `max_urls` must be greater than 0."

    try:
        payload = json.loads(crawl_step_output)
    except json.JSONDecodeError as e:
        audit_log("research_enqueue_from_crawl_step", {}, "error", f"Invalid JSON: {e}")
        return "Error: `crawl_step_output` must be valid JSON from `browser_crawl_step`."

    links_section = payload.get("links") if isinstance(payload, dict) else None
    if isinstance(links_section, dict):
        raw_links = links_section.get("links", [])
    elif isinstance(links_section, list):
        raw_links = links_section
    else:
        raw_links = []

    if not isinstance(raw_links, list) or not raw_links:
        return "No links found in crawl-step output to enqueue."

    topic_tokens = _extract_topic_tokens(topic_hint)

    selected = []
    seen_urls = set()
    filtered_counts: Dict[str, int] = {
        "invalid": 0,
        "duplicate": 0,
        "unsupported_scheme": 0,
        "binary_asset": 0,
        "low_signal_page": 0,
        "topic_mismatch": 0,
    }

    for item in raw_links:
        if len(selected) >= max_urls:
            break

        if isinstance(item, str):
            url = item.strip()
            text = ""
        elif isinstance(item, dict):
            url = str(item.get("url") or item.get("href") or "").strip()
            text = " ".join(str(item.get("text", "")).split())
        else:
            filtered_counts["invalid"] += 1
            continue

        if not url:
            filtered_counts["invalid"] += 1
            continue

        normalized_url = url.split("#", 1)[0]
        if normalized_url in seen_urls:
            filtered_counts["duplicate"] += 1
            continue

        is_valid, reason = _is_high_signal_link(normalized_url, text, topic_tokens)
        if not is_valid:
            filtered_counts[reason] = filtered_counts.get(reason, 0) + 1
            continue

        seen_urls.add(normalized_url)
        selected.append(normalized_url)

    if not selected:
        audit_log(
            "research_enqueue_from_crawl_step",
            {"topic_hint": topic_hint, "max_urls": max_urls, "filtered": filtered_counts},
            "warning",
            "No links passed filters",
        )
        return (
            "No links passed filters from crawl-step output. "
            f"Filtered counts: {json.dumps(filtered_counts)}"
        )

    queue_result = research_queue_urls(selected)
    audit_log(
        "research_enqueue_from_crawl_step",
        {
            "topic_hint": topic_hint,
            "max_urls": max_urls,
            "selected": len(selected),
            "filtered": filtered_counts,
        },
        "success",
    )

    preview = "\n".join(f"- {u}" for u in selected[:8])
    return (
        f"Selected {len(selected)} high-signal links from crawl output.\n"
        f"{queue_result}\n"
        "Preview:\n"
        f"{preview}"
    )

def research_queue_urls(urls: List[str]) -> str:
    """Add a list of discovered URLs to the research queue."""
    try:
        path = Path(RESEARCH_STATE_FILE)
        if path.exists():
            state = json.loads(path.read_text(encoding="utf-8"))
        else:
            state = {"queue": [], "visited": [], "summaries": []}
        
        added = 0
        for url in urls:
            if url not in state["visited"] and url not in state["queue"]:
                state["queue"].append(url)
                added += 1
        
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        audit_log("research_queue_urls", {"count": added}, "success")
        return f"Added {added} new URLs to the queue. Total in queue: {len(state['queue'])}."
    except Exception as e:
        return f"Error queuing URLs: {e}"

def research_get_next() -> str:
    """Get the next unvisited URL from the queue."""
    try:
        path = Path(RESEARCH_STATE_FILE)
        if not path.exists():
            return "Error: Research queue is empty. Discover URLs first."
        
        state = json.loads(path.read_text(encoding="utf-8"))
        if not state["queue"]:
            return "RESEARCH_COMPLETE: No more URLs in queue."
        
        url = state["queue"].pop(0)
        state["visited"].append(url)
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return url
    except Exception as e:
        return f"Error getting next URL: {e}"

def research_store_summary(url: str, summary: str) -> str:
    """Store a concise summary of a visited site to the persistent state."""
    try:
        path = Path(RESEARCH_STATE_FILE)
        state = json.loads(path.read_text(encoding="utf-8"))
        state["summaries"].append({"url": url, "summary": summary})
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return f"Summary for `{url}` stored. Total sites analyzed: {len(state['summaries'])}."
    except Exception as e:
        return f"Error storing summary: {e}"

def research_get_all_summaries() -> str:
    """Retrieve the combined summaries of all sources analyzed so far."""
    try:
        path = Path(RESEARCH_STATE_FILE)
        if not path.exists():
            return "No research data found."
        state = json.loads(path.read_text(encoding="utf-8"))

        output = ""
        for i, entry in enumerate(state["summaries"], 1):
            output += f"--- Source {i}: {entry['url']} ---\n{entry['summary']}\n\n"
        return (
            output
            if output
            else "Queue is active but no summaries have been stored yet."
        )
    except Exception as e:
        return f"Error retrieving data: {e}"


def research_clear() -> str:
    """Clear the persistent research state and queue."""
    try:
        path = Path(RESEARCH_STATE_FILE)
        if path.exists():
            path.unlink()
            audit_log("research_clear", {}, "success")
            return "Research state cleared successfully."
        return "No active research state to clear."
    except Exception as e:
        audit_log("research_clear", {}, "error", str(e))
        return f"Error clearing research state: {e}"
