#!/usr/bin/env python3
"""Zelfstandig script: aangeboden diensten bewaken en nieuwe diensten mailen.

Haalt elke minuut status 16 en 26 op voor Leiderdorp, van deze maand t/m
december 2027, en laat nachten weg. De eerste 5 runs na het starten mailen
het volledige overzicht, als test. Daarna gaat er alleen een mail de deur
uit als er diensten bij zijn gekomen sinds de vorige run, en die mail bevat
alleen die nieuwe diensten.

Een geldige token staat in .waarneemapp_token.json naast dit script.
Het script logt alleen opnieuw in als die token ontbreekt of door de API wordt geweigerd.
De vorige stand staat in .waarneemapp_seen.json.

Start:
  python3 waarneemapp_shifts.py

Vul hieronder de twee wachtwoorden in. Het SMTP-wachtwoord is een
Gmail-appwachtwoord van het account dat de mail verstuurt
(https://myaccount.google.com/apppasswords), niet het WaarneemApp-wachtwoord.
Outlook weigert het gewone Hotmail-wachtwoord voor SMTP.
"""

from __future__ import annotations

import html
import json
import smtplib
import ssl
import time
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
SEEN_PATH = Path(__file__).with_name(".waarneemapp_seen.json")
INTERVAL_SECONDS = 60
TEST_RUNS = 5
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
        self.token_ok_reported = False

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


def load_seen() -> set[int] | None:
    try:
        payload = json.loads(SEEN_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("ids"), list):
        return None
    return {int(shift_id) for shift_id in payload["ids"]}


def save_seen(shift_ids: set[int]) -> None:
    SEEN_PATH.write_text(json.dumps({"ids": sorted(shift_ids)}))
    SEEN_PATH.chmod(0o600)


def describe(client: Client, shift: dict) -> dict[str, str]:
    code = code_of(shift)
    department = (code.get("department") or {}).get("name") or "Leiderdorp"
    assigned = ((shift.get("vacancy") or {}).get("assigned_user") or {}).get("name") or "—"
    offered_by, offered_on, responses = offer_info(client, shift["id"])
    return {
        "when": format_when(shift),
        "code": code.get("code") or "—",
        "name": code.get("name") or "—",
        "department": department,
        "status": str(shift.get("_status") or "—"),
        "assigned": assigned,
        "offered_by": offered_by,
        "offered_on": offered_on,
        "responses": str(responses),
        "hours": str(shift.get("wa_shift_diff_in_hours") or "—"),
        "id": str(shift.get("id") or "—"),
    }


def detail_pairs(row: dict[str, str]) -> list[tuple[str, str]]:
    return [
        ("Wanneer", row["when"]),
        ("Code", row["code"]),
        ("Dienst", row["name"]),
        ("Afdeling", row["department"]),
        ("Status", row["status"]),
        ("Ingevuld door", row["assigned"]),
        ("Aangeboden door", row["offered_by"]),
        ("Aangeboden op", row["offered_on"]),
        ("Duur", row["hours"]),
        ("Reacties", row["responses"]),
        ("Dienstnummer", row["id"]),
    ]


def render_report(rows: list[dict[str, str]], footer: str) -> str:
    if not rows:
        return f"Geen diensten buiten de nachten.\n\n{footer}"
    blocks = []
    for row in rows:
        blocks.append(f"{row['code']}  {row['name']}")
        blocks.extend(f"  {label}: {value}" for label, value in detail_pairs(row))
        blocks.append("")
    blocks.append(footer)
    return "\n".join(blocks)


def render_html(rows: list[dict[str, str]], footer: str) -> str:
    cards = []
    for row in rows:
        title = html.escape(f"{row['code']}  {row['name']}")
        body = []
        for label, value in detail_pairs(row):
            body.append(
                "<tr>"
                f"<td style=\"padding:8px 14px;color:#52606d;width:38%;border-top:1px solid #e6ebf0;\">{html.escape(label)}</td>"
                f"<td style=\"padding:8px 14px;border-top:1px solid #e6ebf0;\">{html.escape(value)}</td>"
                "</tr>"
            )
        cards.append(
            "<table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" "
            "style=\"background:#ffffff;border:1px solid #d9e2ec;border-radius:10px;"
            "margin:0 0 16px;border-collapse:separate;overflow:hidden;\">"
            f"<tr><td colspan=\"2\" style=\"background:#163a5f;color:#ffffff;padding:14px 16px;"
            f"font-size:16px;font-weight:bold;\">{title}</td></tr>"
            f"{''.join(body)}</table>"
        )
    if not cards:
        cards.append("<p style=\"margin:0;\">Geen diensten buiten de nachten.</p>")
    return (
        "<!DOCTYPE html><html><body style=\"margin:0;background:#f4f7fb;"
        "font-family:Arial,Helvetica,sans-serif;color:#1c2430;\">"
        "<div style=\"max-width:640px;margin:0 auto;padding:28px 16px;\">"
        "<p style=\"margin:0 0 6px;font-size:13px;letter-spacing:.04em;color:#52606d;\">"
        "WAARNEEMAPP · LEIDERDORP</p>"
        "<h1 style=\"margin:0 0 8px;font-size:22px;\">Aangeboden diensten</h1>"
        f"<p style=\"margin:0 0 20px;color:#52606d;\">{html.escape(footer)}</p>"
        f"{''.join(cards)}"
        "</div></body></html>"
    )


def subject_for(rows: list[dict[str, str]], *, new: bool, run_number: int | None = None) -> str:
    if not rows:
        listed = "geen diensten"
    elif new and len(rows) == 1:
        row = rows[0]
        return f"Nieuwe dienst: {row['code']} {row['name']}, {row['when']}"
    else:
        listed = "; ".join(f"{row['code']} {row['when']}" for row in rows)
    if new:
        return f"Nieuwe diensten: {listed}"
    return f"Testoverzicht {run_number}/{TEST_RUNS}: {listed}"


def send_report(rows: list[dict[str, str]], footer: str, subject: str) -> bool:
    if not SMTP_PASSWORD:
        print(
            "SMTP_PASSWORD is leeg, mail niet verstuurd. Vul bovenaan een "
            f"Gmail-appwachtwoord in van {SMTP_USER}."
        )
        return False
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = MAIL_FROM
    message["To"] = MAIL_TO
    message.set_content(render_report(rows, footer))
    message.add_alternative(render_html(rows, footer), subtype="html")
    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls(context=context)
        smtp.ehlo()
        smtp.login(SMTP_USER, SMTP_PASSWORD)
        smtp.send_message(message)
    return True


def collect_shifts(client: Client) -> list[dict]:
    shifts = []
    for year, month in month_range(datetime.now(AMSTERDAM)):
        for status in STATUSES:
            shifts.extend(fetch_month(client, year, month, status))
    kept = [shift for shift in shifts if not is_night(shift)]
    kept.sort(key=lambda shift: shift.get("start_time") or "")
    return kept


def log(message: str) -> None:
    stamp = datetime.now(AMSTERDAM).strftime("%Y-%m-%d %H:%M:%S")
    print(f"{stamp} {message}", flush=True)


def run_once(client: Client, run_number: int) -> None:
    log(f"Run {run_number}: controle gestart.")
    kept = collect_shifts(client)
    if client.token and not client.logged_in and not client.token_ok_reported:
        log("Bestaande token is geldig, niet opnieuw ingelogd.")
        client.token_ok_reported = True
    current_ids = {shift["id"] for shift in kept}
    if run_number == TEST_RUNS + 1:
        log("Testfase klaar. Het script blijft elke minuut draaien en mailt alleen nieuwe diensten.")

    if run_number <= TEST_RUNS:
        rows = [describe(client, shift) for shift in kept]
        footer = (
            f"Testmail {run_number} van {TEST_RUNS}. "
            f"Volledig overzicht: {len(rows)} dienst(en), nachten weggelaten."
        )
        print(render_report(rows, footer), flush=True)
        subject = subject_for(rows, new=False, run_number=run_number)
        mailed = send_report(rows, footer, subject)
        if mailed:
            log(f"Run {run_number}: klaar, testmail verstuurd naar {MAIL_TO}, {len(rows)} diensten.")
        else:
            log(f"Run {run_number}: klaar, testmail niet verstuurd, {len(rows)} diensten.")
        save_seen(current_ids)
        return

    previous = load_seen()
    if previous is None:
        save_seen(current_ids)
        log(f"Run {run_number}: klaar, geen eerdere stand, {len(current_ids)} diensten vastgelegd, geen mail.")
        return

    new_shifts = [shift for shift in kept if shift["id"] not in previous]
    if not new_shifts:
        save_seen(current_ids)
        log(f"Run {run_number}: klaar, geen nieuwe diensten, {len(current_ids)} bekend.")
        return

    rows = [describe(client, shift) for shift in new_shifts]
    count = len(rows)
    footer = f"{count} nieuwe dienst(en) sinds de vorige controle. Nachten blijven buiten beeld."
    print(render_report(rows, footer), flush=True)
    subject = subject_for(rows, new=True)
    if send_report(rows, footer, subject):
        save_seen(current_ids)
        log(f"Run {run_number}: klaar, mail verstuurd naar {MAIL_TO}, {count} nieuwe dienst(en).")
        return
    log(f"Run {run_number}: klaar, {count} nieuwe dienst(en), mail niet verstuurd.")


def main() -> None:
    client = Client()
    if client.token:
        print("Opgeslagen token gevonden, eerst die gebruiken.")
    run_number = 1
    while True:
        started = time.monotonic()
        try:
            run_once(client, run_number)
            run_number += 1
        except SystemExit:
            raise
        except Exception as error:
            log(f"Run {run_number}: fout tijdens controle: {error}")
        remaining = INTERVAL_SECONDS - (time.monotonic() - started)
        if remaining > 0:
            time.sleep(remaining)


if __name__ == "__main__":
    main()
