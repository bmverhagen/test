#!/usr/bin/env python3
"""Genereer een HTML-overzichtspagina van gescrapete NOS-artikelen."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


def format_date(value: str | None) -> str:
    if not value:
        return ""
    return value.replace("T", " ").split("+")[0]


def section_label(article: dict) -> str:
    secties = article.get("sectie") or []
    if secties:
        return ", ".join(secties)
    return article.get("bron_feed", "NOS")


def generate_page(data: dict) -> str:
    articles = data.get("artikelen", [])
    scraped_at = format_date(data.get("gescrapet_op", ""))

    cards = []
    for article in articles:
        titel = html.escape(article.get("titel", ""))
        url = html.escape(article.get("url") or article.get("link", ""))
        sectie = html.escape(section_label(article))
        datum = html.escape(
            format_date(article.get("gepubliceerd") or article.get("gepubliceerd_rss"))
        )
        samenvatting = html.escape(
            article.get("samenvatting") or article.get("samenvatting_rss", "")
        )
        inhoud = html.escape(article.get("inhoud", ""))
        afbeelding = article.get("afbeelding")
        trefwoorden = article.get("trefwoorden") or []

        image_html = ""
        if afbeelding:
            image_html = (
                f'<img class="card-image" src="{html.escape(afbeelding)}" '
                f'alt="{titel}" loading="lazy">'
            )

        tags_html = "".join(
            f'<span class="tag">{html.escape(tag)}</span>' for tag in trefwoorden
        )

        body_html = ""
        if inhoud and inhoud != samenvatting:
            body_html = f'<p class="card-body">{inhoud}</p>'

        cards.append(
            f"""
            <article class="card" data-section="{sectie.lower()}">
              {image_html}
              <div class="card-content">
                <div class="card-meta">
                  <span class="section">{sectie}</span>
                  <time datetime="{datum}">{datum}</time>
                </div>
                <h2><a href="{url}" target="_blank" rel="noopener">{titel}</a></h2>
                <p class="card-summary">{samenvatting}</p>
                {body_html}
                <div class="tags">{tags_html}</div>
              </div>
            </article>
            """
        )

    sections = sorted(
        {section_label(a) for a in articles},
        key=str.lower,
    )
    filter_buttons = '<button class="filter active" data-filter="all">Alles</button>'
    for sectie in sections:
        safe = html.escape(sectie)
        filter_buttons += (
            f'<button class="filter" data-filter="{safe.lower()}">{safe}</button>'
        )

    return f"""<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>NOS Artikelen — {len(articles)} stuks</title>
  <style>
    :root {{
      --nos-red: #e61e14;
      --bg: #f4f4f4;
      --card: #ffffff;
      --text: #1a1a1a;
      --muted: #666666;
      --border: #e5e5e5;
    }}

    * {{ box-sizing: border-box; }}

    body {{
      margin: 0;
      font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.55;
    }}

    header {{
      background: var(--nos-red);
      color: white;
      padding: 1.5rem 1rem 2rem;
    }}

    .container {{
      max-width: 960px;
      margin: 0 auto;
      padding: 0 1rem;
    }}

    header h1 {{
      margin: 0 0 0.35rem;
      font-size: 1.8rem;
      font-weight: 700;
    }}

    header p {{
      margin: 0;
      opacity: 0.95;
    }}

    .filters {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      margin: 1.25rem 0 0;
    }}

    .filter {{
      border: 1px solid rgba(255,255,255,0.45);
      background: rgba(255,255,255,0.12);
      color: white;
      border-radius: 999px;
      padding: 0.35rem 0.85rem;
      cursor: pointer;
      font-size: 0.9rem;
    }}

    .filter:hover,
    .filter.active {{
      background: white;
      color: var(--nos-red);
      border-color: white;
    }}

    main {{
      padding: 1.5rem 0 3rem;
    }}

    .stats {{
      color: var(--muted);
      margin-bottom: 1rem;
      font-size: 0.95rem;
    }}

    .grid {{
      display: grid;
      gap: 1rem;
    }}

    .card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }}

    .card.hidden {{
      display: none;
    }}

    .card-image {{
      width: 100%;
      height: 220px;
      object-fit: cover;
      display: block;
      background: #ddd;
    }}

    .card-content {{
      padding: 1rem 1.1rem 1.15rem;
    }}

    .card-meta {{
      display: flex;
      justify-content: space-between;
      gap: 1rem;
      font-size: 0.85rem;
      color: var(--muted);
      margin-bottom: 0.5rem;
    }}

    .section {{
      color: var(--nos-red);
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.03em;
      font-size: 0.78rem;
    }}

    h2 {{
      margin: 0 0 0.6rem;
      font-size: 1.25rem;
      line-height: 1.3;
    }}

    h2 a {{
      color: inherit;
      text-decoration: none;
    }}

    h2 a:hover {{
      color: var(--nos-red);
    }}

    .card-summary {{
      margin: 0 0 0.75rem;
      color: #333;
    }}

    .card-body {{
      margin: 0 0 0.75rem;
      color: var(--muted);
      font-size: 0.95rem;
      display: -webkit-box;
      -webkit-line-clamp: 4;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}

    .tags {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.4rem;
    }}

    .tag {{
      background: #f0f0f0;
      color: #444;
      border-radius: 999px;
      padding: 0.2rem 0.55rem;
      font-size: 0.78rem;
    }}

    @media (min-width: 720px) {{
      .card {{
        display: grid;
        grid-template-columns: 280px 1fr;
      }}

      .card-image {{
        height: 100%;
        min-height: 180px;
      }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="container">
      <h1>NOS Artikelen</h1>
      <p>Gescrapet op {html.escape(scraped_at)} — {len(articles)} artikelen</p>
      <div class="filters" id="filters">
        {filter_buttons}
      </div>
    </div>
  </header>

  <main class="container">
    <p class="stats" id="stats">{len(articles)} artikelen zichtbaar</p>
    <div class="grid" id="articles">
      {"".join(cards)}
    </div>
  </main>

  <script>
    const filters = document.getElementById("filters");
    const articles = document.querySelectorAll(".card");
    const stats = document.getElementById("stats");

    filters.addEventListener("click", (event) => {{
      const button = event.target.closest(".filter");
      if (!button) return;

      filters.querySelectorAll(".filter").forEach((el) => el.classList.remove("active"));
      button.classList.add("active");

      const value = button.dataset.filter;
      let visible = 0;

      articles.forEach((card) => {{
        const section = card.dataset.section || "";
        const show = value === "all" || section.includes(value);
        card.classList.toggle("hidden", !show);
        if (show) visible += 1;
      }});

      stats.textContent = `${{visible}} artikelen zichtbaar`;
    }});
  </script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Genereer HTML-overzicht van NOS-artikelen")
    parser.add_argument(
        "-i",
        "--input",
        default="data/nos_artikelen.json",
        help="Invoer JSON-bestand",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="nos_artikelen.html",
        help="Uitvoer HTML-bestand",
    )
    args = parser.parse_args()

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    output_path = Path(args.output)
    output_path.write_text(generate_page(data), encoding="utf-8")
    print(f"HTML gegenereerd: {output_path}")


if __name__ == "__main__":
    main()
