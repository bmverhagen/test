"""Export Booking results as browser bookmarks (Netscape HTML)."""

from __future__ import annotations

import html
import time
from typing import TextIO

from .models import PropertyResult, SearchQuery, SearchReport
from .urls import build_stay_url


def stay_url(prop: PropertyResult, query: SearchQuery) -> str:
    """Hotel URL with check-in/out and party size for a bookable deep link."""
    return build_stay_url(prop.url, query)


def write_bookmarks(report: SearchReport, stream: TextIO) -> None:
    """Write a Netscape-bookmark file importable by Chrome/Firefox/Safari."""
    now = int(time.time())
    ages = ",".join(str(a) for a in report.query.children_ages) or "—"
    folder = (
        f"Zwarte Woud {report.query.checkin}–{report.query.checkout} "
        f"({report.query.adults} volw. + {report.query.children} kind "
        f"leeftijd {ages}; beschikbaar + gratis annuleren)"
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
    ages = ", ".join(str(a) for a in report.query.children_ages) or "—"
    stream.write(
        f"# Bookmarks — {report.query.destination} "
        f"{report.query.checkin} → {report.query.checkout}\n\n"
        f"**Gezelschap:** {report.query.adults} volwassenen + "
        f"{report.query.children} kind (leeftijd {ages}).\n\n"
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
