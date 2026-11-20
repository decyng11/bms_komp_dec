#!/usr/bin/env python3
"""Zbiorczy status instalacji EMS komp-dec — Twojej i znajomych — na jednej stronie.

Narzędzie jest poza integracją (nie instaluje się go w Home Assistancie). Uruchamiasz je u siebie (komputer, serwer, Raspberry),
a ono odpytuje po sieci (np. Tailscale) kolejne instalacje o dwa czujniki EMS i pokazuje: co u kogo „dziś nie działa”,
ile jest alarmów i jak wypadła ostatnia ocena planu. Tylko odczyt (zapytania GET), nic nie zmienia u znajomych.

Użycie:
    python3 fleet_status.py fleet.json                 # tabela w terminalu
    python3 fleet_status.py fleet.json --html out.html # strona HTML do otwarcia w przeglądarce
    python3 fleet_status.py fleet.json --json          # surowy wynik (do własnych skryptów)

fleet.json:
    {"installations": [
        {"name": "Dom",       "url": "http://100.64.0.10:8123", "token": "DŁUGOTERMINOWY-TOKEN"},
        {"name": "Kuba",      "url": "http://100.64.0.22:8123", "token": "…"}
    ]}
(opcjonalnie na instalację: "monitor_entity", "accuracy_entity" — gdy czujniki mają inne nazwy niż sensor.bms_monitor_status
i sensor.bms_forecast_accuracy; "timeout" w sekundach.)

Ważne o tokenie: długoterminowy token Home Assistanta NIE jest tokenem „tylko do odczytu” — ma uprawnienia konta, na którym go
utworzono. To narzędzie wysyła wyłącznie GET, ale token trzeba chronić: dla znajomego załóż osobne konto bez uprawnień
administratora, trzymaj fleet.json z prawami tylko dla siebie (chmod 600) i łącz się wyłącznie przez Tailscale / sieć prywatną.
Narzędzie nie zapisuje tokenów nigdzie poza wczytanym plikiem i nie wypisuje ich w komunikatach."""
from __future__ import annotations

import argparse
import concurrent.futures
import html
import json
import os
import stat
import sys
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any

MONITOR = "sensor.bms_monitor_status"
ACCURACY = "sensor.bms_forecast_accuracy"
TIMEOUT = 8.0
MAX_BYTES = 2_000_000           # odpowiedź większa niż to jest podejrzana — nie wczytujemy
MAX_INSTALLATIONS = 50
MAX_ISSUES_SHOWN = 12
LEVEL_RANK = {"error": 0, "warn": 1, "info": 2}
LEVEL_ICON = {"error": "🔴", "warn": "🟠", "info": "🔵"}
STATUS_ICON = {"ok": "🟢", "info": "🔵", "warn": "🟠", "error": "🔴", "offline": "⚫"}
STATUS_RANK = {"error": 0, "offline": 1, "warn": 2, "info": 3, "ok": 4}
VERDICTS = ("trafny", "częściowo trafny", "chybiony")


# ------------------------------------------------------------------ konfiguracja
def load_config(path: str) -> list[dict[str, Any]]:
    """Lista instalacji z pliku JSON; błędne wpisy odrzucone z opisem (nie przerywamy całości)."""
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    items = raw.get("installations") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        raise ValueError("plik musi zawierać listę „installations”")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, it in enumerate(items[:MAX_INSTALLATIONS], 1):
        if not isinstance(it, dict):
            continue
        name = str(it.get("name") or f"Instalacja {i}").strip()[:60] or f"Instalacja {i}"
        url = str(it.get("url") or "").strip().rstrip("/")
        token = str(it.get("token") or "").strip()
        if not url.startswith(("http://", "https://")) or not token:
            out.append({"name": name, "url": url, "token": "", "bad": "brak poprawnego adresu (http://…) lub tokenu"})
            continue
        if name in seen:
            name = f"{name} ({i})"
        seen.add(name)
        try:
            to = float(it.get("timeout", TIMEOUT))
        except (TypeError, ValueError):
            to = TIMEOUT
        out.append({"name": name, "url": url, "token": token, "timeout": min(30.0, max(1.0, to)),
                    "monitor": str(it.get("monitor_entity") or MONITOR), "accuracy": str(it.get("accuracy_entity") or ACCURACY)})
    return out


def permissions_warning(path: str) -> str | None:
    """Ostrzeżenie, gdy plik z tokenami mogą czytać inni użytkownicy komputera."""
    try:
        mode = os.stat(path).st_mode
    except OSError:
        return None
    if mode & (stat.S_IRGRP | stat.S_IROTH):
        return f"Plik {os.path.basename(path)} z tokenami jest czytelny dla innych użytkowników — ustaw prawa: chmod 600 {path}"
    return None


# ------------------------------------------------------------------ odczyt
class FetchError(Exception):
    pass


def _get_state(base: str, entity: str, token: str, timeout: float, opener=None) -> dict[str, Any]:
    """Jeden GET /api/states/<encja>. Wyjątek FetchError z czytelnym opisem (bez tokenu)."""
    if not entity.startswith("sensor.") or any(c in entity for c in " /?#&"):
        raise FetchError(f"zła nazwa encji „{entity[:40]}”")
    req = urllib.request.Request(f"{base}/api/states/{entity}", headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=timeout) as resp:
            data = resp.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as err:
        if err.code in (401, 403):
            raise FetchError("token odrzucony (401/403) — sprawdź, czy token jest aktualny") from None
        if err.code == 404:
            raise FetchError(f"brak encji {entity} (nie ma EMS komp-dec albo inna nazwa czujnika)") from None
        raise FetchError(f"HTTP {err.code}") from None
    except urllib.error.URLError as err:
        raise FetchError(f"brak połączenia ({type(err.reason).__name__ if not isinstance(err.reason, str) else err.reason})") from None
    except (TimeoutError, OSError) as err:
        raise FetchError(f"brak połączenia ({type(err).__name__})") from None
    if len(data) > MAX_BYTES:
        raise FetchError("odpowiedź zbyt duża")
    try:
        obj = json.loads(data.decode("utf-8", "replace"))
    except ValueError:
        raise FetchError("odpowiedź nie jest JSON-em (zły adres?)") from None
    if not isinstance(obj, dict):
        raise FetchError("nieoczekiwany kształt odpowiedzi")
    return obj


def _attrs(st: Any) -> dict[str, Any]:
    a = st.get("attributes") if isinstance(st, dict) else None
    return a if isinstance(a, dict) else {}


def summarize(monitor: Any, accuracy: Any) -> dict[str, Any]:
    """Z dwóch stanów czujników EMS: lista problemów, liczba alarmów, ostatnia ocena planu i ogólny status."""
    ma = _attrs(monitor)
    issues = []
    for it in ma.get("issues") if isinstance(ma.get("issues"), list) else []:
        if isinstance(it, dict) and it.get("title"):
            lvl = it.get("level") if it.get("level") in LEVEL_RANK else "info"
            issues.append({"level": lvl, "title": str(it["title"])[:200], "fix": str(it.get("fix") or "")[:300]})
    issues.sort(key=lambda x: LEVEL_RANK[x["level"]])
    alarms = ma.get("alarms") if isinstance(ma.get("alarms"), list) else []
    last = None
    revs = [r for r in (_attrs(accuracy).get("reviews") if isinstance(_attrs(accuracy).get("reviews"), list) else [])
            if isinstance(r, dict) and r.get("verdict") in VERDICTS and isinstance(r.get("date"), str)]
    if revs:
        r = max(revs, key=lambda x: x["date"])
        cul = r.get("culprit") if isinstance(r.get("culprit"), dict) else {}
        last = {"date": r["date"][:10], "verdict": r["verdict"], "culprit": str(cul.get("label") or "")[:80] or None}
    level = "ok"
    if issues:
        level = issues[0]["level"]
    if alarms:
        level = "error"                     # aktywny alarm falownika to zawsze sprawa do sprawdzenia
    if level == "ok" and last and last["verdict"] == "chybiony":
        level = "info"
    return {"status": level, "issues": issues[:MAX_ISSUES_SHOWN], "issues_total": len(issues), "alarms": len(alarms), "review": last}


def check_one(inst: dict[str, Any], opener=None) -> dict[str, Any]:
    """Odpytuje jedną instalację. Zawsze zwraca słownik (nigdy wyjątek): status offline z powodem, gdy się nie udało."""
    base = {"name": inst.get("name") or "?", "checked_at": datetime.now().strftime("%H:%M:%S")}
    if inst.get("bad"):
        return {**base, "status": "offline", "error": inst["bad"], "issues": [], "issues_total": 0, "alarms": 0, "review": None}
    try:
        mon = _get_state(inst["url"], inst["monitor"], inst["token"], inst["timeout"], opener)
        try:
            acc = _get_state(inst["url"], inst["accuracy"], inst["token"], inst["timeout"], opener)
        except FetchError:
            acc = None                      # ocena planu to dodatek — jej brak nie oznacza awarii instalacji
        return {**base, **summarize(mon, acc), "error": None}
    except FetchError as err:
        return {**base, "status": "offline", "error": str(err), "issues": [], "issues_total": 0, "alarms": 0, "review": None}
    except Exception as err:  # noqa: BLE001
        return {**base, "status": "offline", "error": f"nieoczekiwany błąd ({type(err).__name__})", "issues": [], "issues_total": 0, "alarms": 0, "review": None}


def check_all(insts: list[dict[str, Any]], opener=None) -> list[dict[str, Any]]:
    """Wszystkie instalacje równolegle; kolejność wyniku jak w pliku."""
    if not insts:
        return []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(insts))) as ex:
        return list(ex.map(lambda i: check_one(i, opener), insts))


# ------------------------------------------------------------------ widoki
def render_text(results: list[dict[str, Any]]) -> str:
    rows = sorted(results, key=lambda r: STATUS_RANK.get(r["status"], 9))
    lines = [f"Status instalacji EMS komp-dec — {datetime.now().strftime('%Y-%m-%d %H:%M')}", ""]
    for r in rows:
        head = f"{STATUS_ICON.get(r['status'], '?')} {r['name']}"
        if r["status"] == "offline":
            lines.append(f"{head} — brak odczytu: {r['error']}")
            continue
        extra = []
        if r["alarms"]:
            extra.append(f"alarmy: {r['alarms']}")
        if r["review"]:
            extra.append(f"plan z {r['review']['date']}: {r['review']['verdict']}" + (f" (zawiodło: {r['review']['culprit'].lower()})" if r["review"]["culprit"] else ""))
        lines.append(head + (" — " + "; ".join(extra) if extra else ""))
        for it in r["issues"]:
            lines.append(f"    {LEVEL_ICON.get(it['level'], '•')} {it['title']}")
        if r["issues_total"] > len(r["issues"]):
            lines.append(f"    … i {r['issues_total'] - len(r['issues'])} więcej")
        if not r["issues"] and r["status"] == "ok":
            lines.append("    wszystko działa")
    return "\n".join(lines)


def render_html(results: list[dict[str, Any]]) -> str:
    """Samodzielna strona. Wszystko z cudzych instalacji przechodzi przez html.escape (to dane niezaufane)."""
    esc = lambda x: html.escape(str(x), quote=True)  # noqa: E731
    rows = sorted(results, key=lambda r: STATUS_RANK.get(r["status"], 9))
    cards = []
    for r in rows:
        st = r["status"] if r["status"] in STATUS_ICON else "offline"
        body = []
        if st == "offline":
            body.append(f'<p class="muted">Brak odczytu: {esc(r["error"])}</p>')
        else:
            meta = []                       # kawałki HTML, każdy już po escape
            if r["alarms"]:
                meta.append(f'alarmy: {int(r["alarms"])}')
            if r["review"]:
                rv = r["review"]
                meta.append(f'plan z {esc(rv["date"])}: <b>{esc(rv["verdict"])}</b>' + (f' (zawiodło: {esc(rv["culprit"].lower())})' if rv["culprit"] else ""))
            if meta:
                body.append(f'<p class="muted">{"; ".join(meta)}</p>')
            if r["issues"]:
                body.append("<ul>" + "".join(f'<li class="{esc(it["level"])}">{LEVEL_ICON.get(it["level"], "•")} {esc(it["title"])}</li>' for it in r["issues"]) + "</ul>")
                if r["issues_total"] > len(r["issues"]):
                    body.append(f'<p class="muted">… i {int(r["issues_total"]) - len(r["issues"])} więcej</p>')
            elif st == "ok":
                body.append('<p class="muted">Wszystko działa.</p>')
        cards.append(f'<section class="card {st}"><h2>{STATUS_ICON[st]} {esc(r["name"])}</h2>{"".join(body)}'
                     f'<p class="time">odczyt {esc(r["checked_at"])}</p></section>')
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return ("<!doctype html><html lang=\"pl\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>Status instalacji EMS</title><style>"
            ":root{color-scheme:light dark;--bg:#fff;--fg:#1c1c1e;--card:#f2f2f7;--mut:#6b6b70}"
            "@media(prefers-color-scheme:dark){:root{--bg:#111;--fg:#f2f2f7;--card:#1c1c1e;--mut:#9a9aa0}}"
            "body{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,sans-serif}"
            "h1{font-size:20px;margin:0 0 12px}.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(280px,1fr))}"
            ".card{background:var(--card);border-radius:12px;padding:12px 14px;border-left:4px solid #8e8e93}"
            ".card.ok{border-left-color:#30d158}.card.warn{border-left-color:#ff9f0a}.card.error{border-left-color:#ff453a}.card.info{border-left-color:#0a84ff}"
            ".card h2{font-size:16px;margin:0 0 6px}.card ul{margin:6px 0;padding-left:18px}.muted,.time{color:var(--mut);font-size:13px;margin:4px 0}"
            "</style></head><body>"
            f"<h1>Status instalacji EMS komp-dec <span class=\"muted\">· {esc(now)}</span></h1>"
            f"<div class=\"grid\">{''.join(cards)}</div></body></html>")


# ------------------------------------------------------------------ wejście
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Zbiorczy status instalacji EMS komp-dec (tylko odczyt).")
    ap.add_argument("config", help="plik JSON z listą instalacji (nazwa, adres, token)")
    ap.add_argument("--html", metavar="PLIK", help="zapisz stronę HTML zamiast tabeli w terminalu")
    ap.add_argument("--json", action="store_true", help="wypisz wynik jako JSON")
    args = ap.parse_args(argv)
    warn = permissions_warning(args.config)
    if warn:
        print("UWAGA: " + warn, file=sys.stderr)
    try:
        insts = load_config(args.config)
    except (OSError, ValueError) as err:
        print(f"Nie mogę wczytać {args.config}: {err}", file=sys.stderr)
        return 2
    results = check_all(insts)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    elif args.html:
        with open(args.html, "w", encoding="utf-8") as fh:
            fh.write(render_html(results))
        print(f"Zapisano {args.html} ({len(results)} instalacji)")
    else:
        print(render_text(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
