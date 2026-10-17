#!/usr/bin/env python3
"""Zelfstandig script: aangeboden diensten ophalen en mailen.

Haalt status 16 en 26 op voor Leiderdorp, van deze maand t/m december 2027,
laat nachten weg, print het overzicht en mailt het.

Een geldige token staat in .waarneemapp_token.json naast dit script.
Het script logt alleen opnieuw in als die token ontbreekt of door de API wordt geweigerd.

Start:
  python3 waarneemapp_shifts.py

Vul hieronder de twee wachtwoorden in. Het SMTP-wachtwoord is een
Gmail-appwachtwoord van het account dat de mail verstuurt
(https://myaccount.google.com/apppasswords), niet het WaarneemApp-wachtwoord.
Outlook weigert het gewone Hotmail-wachtwoord voor SMTP.
"""

from __future__ import annotations

import json
import smtplib
import ssl
import urllib.error
import urllib.request
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

# --- instellingen -----------------------------------------------------------

WA_EMAIL = "annejet.warmenhoven@hotmail.com"
WA_PASSWORD = ""  # WaarneemApp-wachtwoord

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "bas.m.verhagen@gmail.com"
SMTP_PASSWORD = ""  # Gmail-appwachtwoord van SMTP_USER
MAIL_FROM = SMTP_USER
MAIL_TO = "bas.m.verhagen@gmail.com"

# ---------------------------------------------------------------------------

API = "https://waarneemapp.nl/api"
COMPANY_ID = 8127
DEPARTMENT_ID = 8355
STATUSES = (16, 26)
TOKEN_PATH = Path(__file__).with_name(".waarneemapp_token.json")
AMSTERDAM = ZoneInfo("Europe/Amsterdam")
MONTHS_NL = (
    "jan", "feb", "mrt", "apr", "mei", "jun",
    "jul", "aug", "sep", "okt", "nov", "dec",
)
WEEKDAYS_NL = ("ma", "di", "wo", "do", "vr", "za", "zo")


class AuthError(Exception):
    pass


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
        if error.code == 401 and token:
            raise AuthError(detail)
        raise SystemExit(f"HTTP {error.code} voor {url}\n{detail}") from error


def load_saved_token() -> str | None:
    try:
        payload = json.loads(TOKEN_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    token = payload.get("access_token") if isinstance(payload, dict) else None
    return token or None


def save_token(token: str) -> None:
    TOKEN_PATH.write_text(json.dumps({"access_token": token}))
    TOKEN_PATH.chmod(0o600)


def login(email: str, password: str) -> str:
    if not password:
        raise SystemExit(
            "De opgeslagen token werkt niet meer en WA_PASSWORD is leeg. "
            "Vul het WaarneemApp-wachtwoord bovenaan het script in."
        )
    payload = request(
        f"{API}/login",
        body={"email": email, "password": password},
        method="POST",
    )
    token = payload.get("access_token")
    if not token:
        raise SystemExit("Login gelukt, maar er kwam geen access_token terug.")
    save_token(token)
    return token


class Client:
    def __init__(self) -> None:
        self.token = load_saved_token()
        self.logged_in = False

    def relogin(self) -> None:
        self.token = login(WA_EMAIL, WA_PASSWORD)
        self.logged_in = True
        print("Opnieuw ingelogd, token opgeslagen.")

    def get(self, url: str):
        if not self.token:
            self.relogin()
        try:
            return request(url, token=self.token)
        except AuthError:
            self.relogin()
            return request(url, token=self.token)


def month_range(today: datetime):
    year, month = today.year, today.month
    while (year, month) <= (2027, 12):
        yield year, month
        month += 1
        if month == 13:
            year, month = year + 1, 1


def fetch_month(client: Client, year: int, month: int, status: int) -> list[dict]:
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
        batch = client.get(url).get("data") or []
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


def offer_info(client: Client, shift_id: int) -> tuple[str, str, int]:
    detail = client.get(f"{API}/wa/companies/{COMPANY_ID}/schedules/shifts/{shift_id}")
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


def send_report(report: str) -> None:
    if not SMTP_PASSWORD:
        raise SystemExit(
            "SMTP_PASSWORD is leeg. Vul bovenaan een Gmail-appwachtwoord in van "
            f"{SMTP_USER}. Het WaarneemApp-wachtwoord kan deze mail niet versturen: "
            "Outlook weigert dat wachtwoord voor SMTP."
        )
    message = EmailMessage()
    message["Subject"] = "Aangeboden diensten Leiderdorp, zonder nachten"
    message["From"] = MAIL_FROM
    message["To"] = MAIL_TO
    message.set_content(report)
    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls(context=context)
        smtp.ehlo()
        smtp.login(SMTP_USER, SMTP_PASSWORD)
        smtp.send_message(message)


def main() -> None:
    client = Client()
    if client.token:
        print("Opgeslagen token gevonden, eerst die gebruiken.")
    shifts = []
    for year, month in month_range(datetime.now(AMSTERDAM)):
        for status in STATUSES:
            shifts.extend(fetch_month(client, year, month, status))
    if client.token and not client.logged_in:
        print("Bestaande token is geldig, niet opnieuw ingelogd.")

    kept = [shift for shift in shifts if not is_night(shift)]
    kept.sort(key=lambda shift: shift.get("start_time") or "")

    rows = []
    for shift in kept:
        code = code_of(shift)
        offered_by, offered_on, responses = offer_info(client, shift["id"])
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
    send_report(report)
    print(f"Gemaild naar {MAIL_TO}.")


if __name__ == "__main__":
    main()
