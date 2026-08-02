"""Export Booking results as browser bookmarks (Netscape HTML)."""

from __future__ import annotations

import html
import time
from typing import TextIO
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from .models import PropertyResult, SearchQuery, SearchReport


def stay_url(prop: PropertyResult, query: SearchQuery) -> str:
    """Hotel URL with check-in/out and party size for a bookable deep link."""
    if not prop.url:
        return ""
    parts = urlparse(prop.url)
    params = parse_qs(parts.query, keep_blank_values=True)
    params["checkin"] = [query.checkin]
    params["checkout"] = [query.checkout]
    params["group_adults"] = [str(query.adults)]
    params["req_adults"] = [str(query.adults)]
    params["no_rooms"] = [str(query.rooms)]
    params["group_children"] = [str(query.children)]
    params["req_children"] = [str(query.children)]
    params["selected_currency"] = [query.currency]
    flat = [(k, v) for k, values in params.items() for v in values]
    return urlunparse(parts._replace(query=urlencode(flat)))


def write_bookmarks(report: SearchReport, stream: TextIO) -> None:
    """Write a Netscape-bookmark file importable by Chrome/Firefox/Safari."""
    now = int(time.time())
    folder = (
        f"Zwarte Woud {report.query.checkin}–{report.query.checkout} "
        f"(beschikbaar + gratis annuleren)"
    )
    stream.write(
        "<!DOCTYPE NETSCAPE-Bookmark-file-1>\n"
        "<!-- This is an automatically generated file.\n"
        "     It can be imported via browser bookmark manager. -->\n"
        '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">\n'
        "<TITLE>Bookmarks</TITLE>\n"
        "<H1>Bookmarks</H1>\n"
        "<DL><p>\n"
        f'    <DT><H3 ADD_DATE="{now}" LAST_MODIFIED="{now}">'
        f"{html.escape(folder)}</H3>\n"
        "    <DL><p>\n"
    )
    for prop in report.properties:
        url = stay_url(prop, report.query)
        if not url:
            continue
        price = (
            f"€{prop.price_total:.0f}"
            if prop.price_total is not None
            else "prijs ?"
        )
        score = (
            f"score {prop.review_score:.1f}"
            if prop.review_score is not None
            else "score ?"
        )
        place = prop.location or "?"
        title = f"{prop.name} — {place} — {price} — {score}"
        stream.write(
            f'        <DT><A HREF="{html.escape(url, quote=True)}" '
            f'ADD_DATE="{now}">{html.escape(title)}</A>\n'
        )
    stream.write("    </DL><p>\n</DL><p>\n")


def write_bookmarks_markdown(report: SearchReport, stream: TextIO) -> None:
    """Human-readable bookmark list (markdown links)."""
    stream.write(
        f"# Bookmarks — {report.query.destination} "
        f"{report.query.checkin} → {report.query.checkout}\n\n"
        "Alleen **beschikbaar** (`oos=1`) en **gratis annuleerbaar** (`fc=2`).\n\n"
    )
    if not report.properties:
        stream.write("Geen matches.\n")
        return
    for prop in report.properties:
        url = stay_url(prop, report.query)
        price = (
            f"€{prop.price_total:.0f}"
            if prop.price_total is not None
            else "—"
        )
        score = (
            f"{prop.review_score:.1f}"
            if prop.review_score is not None
            else "—"
        )
        until = prop.free_cancellation_until or "—"
        stream.write(
            f"- [{prop.name}]({url}) — {prop.location or '?'} — "
            f"{price} — score {score} — gratis annuleren tot {until}\n"
        )
