from __future__ import annotations

import json

from bs4 import BeautifulSoup

BODY_SELECTORS = (
    "article .block-content",
    "article [data-testid='article-body']",
    "article .textblock",
    ".article-body",
    "article",
)
def extract_article_body(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")

    for selector in BODY_SELECTORS:
        node = soup.select_one(selector)
        if node is None:
            continue
        paragraphs = [
            paragraph.get_text(" ", strip=True)
            for paragraph in node.find_all(["p", "h2", "h3", "li"])
            if paragraph.get_text(strip=True)
        ]
        if paragraphs:
            return "\n\n".join(paragraphs)

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            payload = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if not isinstance(item, dict):
                continue
            body = item.get("articleBody")
            if isinstance(body, str) and body.strip():
                return body.strip()

    return None
