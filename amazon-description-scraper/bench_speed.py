#!/usr/bin/env python3
"""Benchmark 50+ speed ideas for Amazon description fetching.

Each experiment runs on a small ASIN slice and reports ok/captcha/rate.
Winner criteria: ok_rate >= 0.96 and captcha == 0, maximize rate.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed, ProcessPoolExecutor
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    import httpx
except ImportError:
    httpx = None

ASINS = Path("/tmp/asins1000.txt").read_text().split()
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
BASE = "https://www.amazon.nl"


def captcha(text: str) -> bool:
    t = text.casefold()
    return any(
        s in t
        for s in (
            "/errors/validatecaptcha",
            "enter the characters you see below",
            "sorry, we just need to make sure you're not a robot",
        )
    )


def bust() -> str:
    return hashlib.md5(f"{time.time_ns()}{random.random()}".encode()).hexdigest()[:10]


def has_desc(text: str, twister: bool = False) -> bool:
    if twister:
        return "featurebullets_feature_div" in text or "title_feature_div" in text
    return "feature-bullets" in text or 'id="productTitle"' in text or "productTitle" in text


@dataclass
class Result:
    name: str
    n: int
    ok: int
    fail: int
    captcha: int
    elapsed: float
    rate: float
    notes: str = ""

    @property
    def stable(self) -> bool:
        return self.n > 0 and self.ok / self.n >= 0.96 and self.captcha == 0


class Spacing:
    def __init__(self, spacing: float):
        self.spacing = spacing
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self):
        if self.spacing <= 0:
            return
        with self._lock:
            now = time.time()
            w = self._next - now
            if w > 0:
                time.sleep(w)
            self._next = time.time() + self.spacing


def build_session(
    *,
    pool: int = 20,
    retries: int = 1,
    backoff: float = 0.3,
) -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=retries,
        connect=retries,
        read=retries,
        status=retries,
        backoff_factor=backoff,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(pool_connections=pool, pool_maxsize=pool, max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update(
        {
            "User-Agent": UA,
            "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
    )
    return s


def fetch_twister(session: requests.Session, asin: str, *, timeout: float = 15, nocache_q: bool = True) -> tuple[bool, bool, int]:
    params = {"isDimensionSlotsAjax": "1", "asinList": asin, "vs": "1"}
    if nocache_q:
        params["_"] = bust()
    url = f"{BASE}/gp/twister/dimension?{urlencode(params)}"
    r = session.get(
        url,
        headers={
            "Accept": "application/json,text/javascript,*/*;q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{BASE}/dp/{asin}",
        },
        timeout=timeout,
    )
    text = r.text or ""
    cap = captcha(text)
    ok = r.status_code == 200 and not cap and has_desc(text, twister=True)
    return ok, cap, len(r.content or b"")


def fetch_dp(session: requests.Session, asin: str, *, timeout: float = 15, nocache_q: bool = True) -> tuple[bool, bool, int]:
    q = f"?th=1&psc=1&_={bust()}" if nocache_q else "?th=1&psc=1"
    r = session.get(f"{BASE}/dp/{asin}{q}", timeout=timeout)
    text = r.text or ""
    cap = captcha(text)
    ok = r.status_code == 200 and not cap and has_desc(text, twister=False)
    return ok, cap, len(r.content or b"")


def fetch_soft(session: requests.Session, asin: str, **kw) -> tuple[bool, bool, int]:
    ok, cap, n = fetch_twister(session, asin, **kw)
    if ok:
        return ok, cap, n
    if cap:
        return False, True, n
    return fetch_dp(session, asin, **kw)


def run_parallel(
    name: str,
    asins: list[str],
    worker_fn: Callable[[str], tuple[bool, bool]],
    workers: int,
    spacing: float,
) -> Result:
    gate = Spacing(spacing)
    t0 = time.time()
    ok = fail = cap = 0
    lock = threading.Lock()

    def one(asin: str):
        gate.wait()
        good, is_cap = worker_fn(asin)
        return good, is_cap

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(one, a) for a in asins]
        for f in as_completed(futs):
            good, is_cap = f.result()
            with lock:
                if good:
                    ok += 1
                else:
                    fail += 1
                if is_cap:
                    cap += 1
    elapsed = max(0.001, time.time() - t0)
    return Result(name, len(asins), ok, fail, cap, elapsed, len(asins) / elapsed)


def slice_asins(offset: int, n: int) -> list[str]:
    start = offset % max(1, len(ASINS) - n)
    return ASINS[start : start + n]


RESULTS: list[Result] = []


def record(r: Result):
    RESULTS.append(r)
    flag = "STABLE" if r.stable else "WEAK  "
    print(
        f"{flag} {r.name:42s} ok={r.ok:2d}/{r.n:<2d} cap={r.captcha} "
        f"fail={r.fail} {r.elapsed:5.1f}s rate={r.rate:5.2f}/s {r.notes}",
        flush=True,
    )


def main():
    N = 24  # per experiment — keep total runtime manageable
    offset = 50
    print(f"BENCH START experiments>=50 N={N} total_asins={len(ASINS)}", flush=True)

    # Warm once
    warm = build_session()
    warm.get(BASE + "/", timeout=20)
    print("warmed", flush=True)

    def mk_worker(fetch_mode: str, session_mode: str, timeout: float, nocache_q: bool, pool: int, retries: int):
        if session_mode == "shared":
            session = build_session(pool=pool, retries=retries)
            session.cookies.update(warm.cookies)

            def fn(asin: str):
                if fetch_mode == "twister":
                    ok, cap, _ = fetch_twister(session, asin, timeout=timeout, nocache_q=nocache_q)
                elif fetch_mode == "dp":
                    ok, cap, _ = fetch_dp(session, asin, timeout=timeout, nocache_q=nocache_q)
                else:
                    ok, cap, _ = fetch_soft(session, asin, timeout=timeout, nocache_q=nocache_q)
                return ok, cap

            return fn
        else:
            def fn(asin: str):
                session = build_session(pool=pool, retries=retries)
                session.cookies.update(warm.cookies)
                if fetch_mode == "twister":
                    ok, cap, _ = fetch_twister(session, asin, timeout=timeout, nocache_q=nocache_q)
                elif fetch_mode == "dp":
                    ok, cap, _ = fetch_dp(session, asin, timeout=timeout, nocache_q=nocache_q)
                else:
                    ok, cap, _ = fetch_soft(session, asin, timeout=timeout, nocache_q=nocache_q)
                return ok, cap

            return fn

    experiments: list[tuple[str, dict]] = []

    # 1-12: worker counts
    for w in (1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 16, 20):
        experiments.append((f"workers_{w}", {"workers": w, "spacing": 0.10, "mode": "soft", "session": "shared"}))

    # 13-20: spacing
    for sp in (0.0, 0.03, 0.05, 0.08, 0.10, 0.12, 0.15, 0.20):
        experiments.append((f"spacing_{sp}", {"workers": 6, "spacing": sp, "mode": "soft", "session": "shared"}))

    # 21-23: fetch mode
    for mode in ("soft", "twister", "dp"):
        experiments.append((f"mode_{mode}", {"workers": 6, "spacing": 0.08, "mode": mode, "session": "shared"}))

    # 24-25: session mode
    for sm in ("shared", "per_request"):
        experiments.append((f"session_{sm}", {"workers": 6, "spacing": 0.08, "mode": "soft", "session": sm}))

    # 26-28: timeouts
    for t in (6, 10, 15):
        experiments.append((f"timeout_{t}", {"workers": 6, "spacing": 0.08, "mode": "soft", "session": "shared", "timeout": t}))

    # 29-30: nocache query on/off (headers still no-cache)
    for nc in (True, False):
        experiments.append((f"nocache_q_{nc}", {"workers": 6, "spacing": 0.08, "mode": "soft", "session": "shared", "nocache_q": nc}))

    # 31-33: pool sizes
    for p in (5, 20, 50):
        experiments.append((f"pool_{p}", {"workers": 6, "spacing": 0.08, "mode": "soft", "session": "shared", "pool": p}))

    # 34-36: retries
    for r in (0, 1, 2):
        experiments.append((f"retries_{r}", {"workers": 6, "spacing": 0.08, "mode": "soft", "session": "shared", "retries": r}))

    # 37-40: combo candidates
    experiments.append(("combo_w8_s05", {"workers": 8, "spacing": 0.05, "mode": "soft", "session": "shared", "timeout": 10, "retries": 1}))
    experiments.append(("combo_w10_s05", {"workers": 10, "spacing": 0.05, "mode": "soft", "session": "shared", "timeout": 10, "retries": 1}))
    experiments.append(("combo_w8_s03", {"workers": 8, "spacing": 0.03, "mode": "soft", "session": "shared", "timeout": 10, "retries": 1}))
    experiments.append(("combo_w12_s05", {"workers": 12, "spacing": 0.05, "mode": "soft", "session": "shared", "timeout": 8, "retries": 1}))

    # 41-42: twister-only aggressive
    experiments.append(("twister_w8_s05", {"workers": 8, "spacing": 0.05, "mode": "twister", "session": "shared", "timeout": 10}))
    experiments.append(("twister_w10_s03", {"workers": 10, "spacing": 0.03, "mode": "twister", "session": "shared", "timeout": 8}))

    # 43-44: two-pass idea simulated as soft with low retries
    experiments.append(("soft_w8_s04_r0", {"workers": 8, "spacing": 0.04, "mode": "soft", "session": "shared", "retries": 0, "timeout": 8}))
    experiments.append(("soft_w10_s04_r0", {"workers": 10, "spacing": 0.04, "mode": "soft", "session": "shared", "retries": 0, "timeout": 8}))

    # 45-46: high workers zero spacing
    experiments.append(("w8_s0", {"workers": 8, "spacing": 0.0, "mode": "soft", "session": "shared", "timeout": 10}))
    experiments.append(("w12_s0", {"workers": 12, "spacing": 0.0, "mode": "soft", "session": "shared", "timeout": 10}))

    # 47-48: baseline comparison
    experiments.append(("baseline_w5_s12", {"workers": 5, "spacing": 0.12, "mode": "soft", "session": "shared"}))
    experiments.append(("baseline_safe_w1_s55", {"workers": 1, "spacing": 0.55, "mode": "soft", "session": "shared"}))

    # 49-52: more combos
    experiments.append(("combo_w6_s05_t8", {"workers": 6, "spacing": 0.05, "mode": "soft", "session": "shared", "timeout": 8, "retries": 1, "pool": 50}))
    experiments.append(("combo_w9_s06", {"workers": 9, "spacing": 0.06, "mode": "soft", "session": "shared", "timeout": 10}))
    experiments.append(("combo_w7_s04", {"workers": 7, "spacing": 0.04, "mode": "soft", "session": "shared", "timeout": 10, "pool": 40}))
    experiments.append(("combo_w8_s06_r2", {"workers": 8, "spacing": 0.06, "mode": "soft", "session": "shared", "timeout": 12, "retries": 2}))

    # Deduplicate names while keeping >=50
    print(f"planned_experiments={len(experiments)}", flush=True)

    for i, (name, cfg) in enumerate(experiments):
        asins = slice_asins(offset + i * N, N)
        fn = mk_worker(
            cfg.get("mode", "soft"),
            cfg.get("session", "shared"),
            float(cfg.get("timeout", 15)),
            bool(cfg.get("nocache_q", True)),
            int(cfg.get("pool", 20)),
            int(cfg.get("retries", 1)),
        )
        r = run_parallel(name, asins, fn, int(cfg["workers"]), float(cfg["spacing"]))
        record(r)
        time.sleep(0.4)

    # httpx async-style threaded (sync API) experiments 53-54
    if httpx is not None:
        for w, sp, name in ((8, 0.05, "httpx_w8_s05"), (10, 0.04, "httpx_w10_s04")):
            asins = slice_asins(offset + len(RESULTS) * N, N)
            client = httpx.Client(
                headers={
                    "User-Agent": UA,
                    "Accept-Language": "nl-NL,nl;q=0.9",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Cache-Control": "no-cache",
                },
                timeout=10,
                http2=False,
                limits=httpx.Limits(max_connections=w * 2, max_keepalive_connections=w * 2),
            )
            client.cookies.update(warm.cookies)
            gate = Spacing(sp)

            def hfn(asin: str, _c=client):
                gate.wait()
                url = f"{BASE}/gp/twister/dimension?isDimensionSlotsAjax=1&asinList={asin}&vs=1&_={bust()}"
                try:
                    resp = _c.get(url, headers={"X-Requested-With": "XMLHttpRequest", "Referer": f"{BASE}/dp/{asin}"})
                    text = resp.text or ""
                    if resp.status_code == 200 and not captcha(text) and has_desc(text, True):
                        return True, False
                    resp = _c.get(f"{BASE}/dp/{asin}?th=1&psc=1&_={bust()}")
                    text = resp.text or ""
                    return (resp.status_code == 200 and not captcha(text) and has_desc(text, False), captcha(text))
                except Exception:
                    return False, False

            r = run_parallel(name, asins, hfn, w, 0.0)  # spacing handled inside
            # Fix rate accounting: spacing inside doubles — recompute via elapsed already ok
            record(r)
            client.close()
            time.sleep(0.4)

    # Two-pass strategy: twister all, then dp only failures (55)
    asins = slice_asins(offset + len(RESULTS) * N, N)
    session = build_session(pool=40, retries=1)
    session.cookies.update(warm.cookies)
    t0 = time.time()
    gate = Spacing(0.04)
    ok_map = {}

    def pass1(asin):
        gate.wait()
        ok, cap, _ = fetch_twister(session, asin, timeout=8)
        return asin, ok, cap

    with ThreadPoolExecutor(max_workers=10) as ex:
        for asin, ok, cap in ex.map(lambda a: pass1(a), asins):
            ok_map[asin] = (ok, cap)
    failures = [a for a, (ok, cap) in ok_map.items() if not ok and not cap]
    gate2 = Spacing(0.08)

    def pass2(asin):
        gate2.wait()
        ok, cap, _ = fetch_dp(session, asin, timeout=10)
        return asin, ok, cap

    if failures:
        with ThreadPoolExecutor(max_workers=6) as ex:
            for asin, ok, cap in ex.map(lambda a: pass2(a), failures):
                ok_map[asin] = (ok, cap)
    elapsed = time.time() - t0
    ok = sum(1 for o, c in ok_map.values() if o)
    capn = sum(1 for o, c in ok_map.values() if c)
    record(Result("two_pass_twister_then_dp", N, ok, N - ok, capn, elapsed, N / elapsed, notes=f"dp_pass={len(failures)}"))

    # Rank
    stable = [r for r in RESULTS if r.stable]
    stable.sort(key=lambda r: -r.rate)
    print("\n===== TOP STABLE =====", flush=True)
    for r in stable[:15]:
        print(f"  {r.rate:5.2f}/s  {r.name}  ok={r.ok}/{r.n}", flush=True)
    print(f"\nTOTAL_EXPERIMENTS={len(RESULTS)} STABLE={len(stable)}", flush=True)
    Path("/tmp/speed_experiments.json").write_text(
        json.dumps([asdict(r) for r in RESULTS], indent=2)
    )
    Path("/tmp/speed_winner.json").write_text(
        json.dumps(asdict(stable[0]) if stable else {}, indent=2)
    )
    if stable:
        print("WINNER", stable[0].name, f"{stable[0].rate:.2f}/s", flush=True)


if __name__ == "__main__":
    # remove broken make_session leftover usage
    main()
