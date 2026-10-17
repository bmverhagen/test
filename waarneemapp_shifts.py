#!/usr/bin/env python3
"""Haal aangeboden diensten op (status 16 en 26) en laat nachten weg.

Van de huidige maand tot en met december 2027, voor Leiderdorp.
Het overzicht wordt ook gemaild.

Gebruik:
  WA_EMAIL=... WA_PASSWORD=... \\
  WA_SMTP_USER=... WA_SMTP_PASSWORD=... \\
  python3 waarneemapp_shifts.py

WA_SMTP_HOST staat standaard op smtp.gmail.com, poort 587.
Het ontvangeradres is bas.m.verhagen@gmail.com, tenzij WA_MAIL_TO anders is.
"""

from __future__ import annotations

import json
import os
import smtplib
import urllib.error
import urllib.request
from datetime import datetime
from email.message import EmailMessage
from zoneinfo import ZoneInfo

API = "https://waarneemapp.nl/api"
COMPANY_ID = 8127
DEPARTMENT_ID = 8355
STATUSES = (16, 26)
MAIL_TO = "bas.m.verhagen@gmail.com"
AMSTERDAM = ZoneInfo("Europe/Amsterdam")
MONTHS_NL = (
    "jan",
    "feb",
    "mrt",
    "apr",
    "mei",
    "jun",
    "jul",
    "aug",
    "sep",
    "okt",
    "nov",
    "dec",
)
WEEKDAYS_NL = ("ma", "di", "wo", "do", "vr", "za", "zo")


def request(url: str, token: str | None = None, body: dict | None = None, method: str | None = None):
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=40) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")[:300]
        raise SystemExit(f"HTTP {error.code} voor {url}\n{detail}") from error


def login(email: str, password: str) -> str:
    payload = request(
        f"{API}/login",
        body={"email": email, "password": password},
        method="POST",
    )
    token = payload.get("access_token")
    if not token:
        raise SystemExit("Login gelukt, maar er kwam geen access_token terug.")
    return token


def month_range(today: datetime):
    year, month = today.year, today.month
    while (year, month) <= (2027, 12):
        yield year, month
        month += 1
        if month == 13:
            year, month = year + 1, 1


def fetch_month(token: str, year: int, month: int, status: int) -> list[dict]:
    rows: list[dict] = []
    page = 1
    while page <= 10:
        url = (
            f"{API}/wa/companies/{COMPANY_ID}/schedules/shifts?"
            f"sort&view=calendar&per_page=100&page={page}&year={year}&month={month}"
            f"&period=month&is_active=1&weekday&status&_status={status}"
            "&code&code_schedule&date_range&single&created_at&updated_at"
            "&code_deviation&holidays&schedule"
            f"&departments={DEPARTMENT_ID}&companies&company_period_id&is_hidden"
            "&user_labels&shift_labels&virtual_assigned_group_ids&company_rate_label_ids"
        )
        batch = request(url, token=token).get("data") or []
        for shift in batch:
            shift["_status"] = status
        rows.extend(batch)
        if len(batch) < 100:
            return rows
        page += 1
    return rows


def local(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(AMSTERDAM)


def code_of(shift: dict) -> dict:
    return (shift.get("code_schedule") or {}).get("code") or {}


def is_night(shift: dict) -> bool:
    code = code_of(shift)
    label = f"{code.get('code') or ''} {code.get('name') or ''}".casefold()
    if "nacht" in label:
        return True
    start = local(shift.get("start_time"))
    end = local(shift.get("end_time"))
    return bool(start and end and end.date() > start.date())


def offer_info(token: str, shift_id: int) -> tuple[str, str, int]:
    detail = request(f"{API}/wa/companies/{COMPANY_ID}/schedules/shifts/{shift_id}", token=token)
    vacancies = (detail.get("vacancy") or {}).get("corporate_schedule_vacancies") or []
    names = []
    dates = []
    responses = 0
    for vacancy in vacancies:
        names.append((vacancy.get("user") or {}).get("name") or "onbekend")
        created = local(vacancy.get("created_at"))
        if created:
            dates.append(f"{created.day} {MONTHS_NL[created.month - 1]} {created.year}")
        responses += len(vacancy.get("responses") or [])
    return (", ".join(names) or "—", ", ".join(dates) or "—", responses)


def format_when(shift: dict) -> str:
    start = local(shift.get("start_time"))
    end = local(shift.get("end_time"))
    if not start or not end:
        return "?"
    return (
        f"{WEEKDAYS_NL[start.weekday()]} {start.strftime('%d-%m-%Y')} "
        f"{start.strftime('%H:%M')}–{end.strftime('%H:%M')}"
    )


def render_report(rows: list[tuple[str, ...]]) -> str:
    headers = ("Wanneer", "Dienst", "Aangeboden door", "Aangeboden op", "Status", "Reacties")
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def line(cells: tuple[str, ...]) -> str:
        return "  ".join(cell.ljust(widths[index]) for index, cell in enumerate(cells)).rstrip()

    lines = [line(headers), line(tuple("-" * width for width in widths))]
    if not rows:
        lines.append("Geen diensten buiten de nachten.")
    lines.extend(line(row) for row in rows)
    lines.append("")
    lines.append(f"{len(rows)} diensten, nachten weggelaten. Periode: deze maand t/m december 2027.")
    return "\n".join(lines)


def send_report(report: str) -> str:
    recipient = os.environ.get("WA_MAIL_TO", MAIL_TO).strip() or MAIL_TO
    host = os.environ.get("WA_SMTP_HOST", "smtp.gmail.com").strip()
    port = int(os.environ.get("WA_SMTP_PORT", "587"))
    user = os.environ.get("WA_SMTP_USER", "").strip()
    password = os.environ.get("WA_SMTP_PASSWORD", "")
    sender = os.environ.get("WA_SMTP_FROM", user).strip()
    if not user or not password or not sender:
        raise SystemExit(
            "De mail is niet verstuurd. Zet WA_SMTP_USER en WA_SMTP_PASSWORD "
            "(een Gmail-appwachtwoord) en draai het script opnieuw."
        )

    message = EmailMessage()
    message["Subject"] = "Aangeboden diensten Leiderdorp, zonder nachten"
    message["From"] = sender
    message["To"] = recipient
    message.set_content(report)

    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(user, password)
        smtp.send_message(message)
    return recipient


def main() -> None:
    email = os.environ.get("WA_EMAIL", "").strip()
    password = os.environ.get("WA_PASSWORD", "")
    if not email or not password:
        raise SystemExit("Zet WA_EMAIL en WA_PASSWORD in de omgeving en draai het script opnieuw.")

    token = login(email, password)
    shifts = []
    for year, month in month_range(datetime.now(AMSTERDAM)):
        for status in STATUSES:
            shifts.extend(fetch_month(token, year, month, status))

    kept = [shift for shift in shifts if not is_night(shift)]
    kept.sort(key=lambda shift: shift.get("start_time") or "")

    rows = []
    for shift in kept:
        code = code_of(shift)
        offered_by, offered_on, responses = offer_info(token, shift["id"])
        rows.append(
            (
                format_when(shift),
                f"{code.get('code') or ''} {code.get('name') or ''}".strip(),
                offered_by,
                offered_on,
                str(shift.get("_status")),
                str(responses),
            )
        )

    report = render_report(rows)
    print(report)
    recipient = send_report(report)
    print(f"Gemaild naar {recipient}.")


if __name__ == "__main__":
    main()
