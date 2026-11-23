"""Oś decyzji planu (o 6:00, 12:00, 18:00) i miara stabilności planu; zużycie baterii w zł. Czyste funkcje, bez HA."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

SLOTS = (6, 12, 18)
KEEP_DAYS = 14


def _sig(props: dict, k1: str, k2: str) -> str | None:
    a, b = props.get(k1), props.get(k2)
    if not isinstance(a, dict):
        return None
    if a.get("skip") or not a.get("proposed"):
        return "pomijam"
    return f"{a.get('proposed')}–{(b or {}).get('proposed')}"


def take(snaps: dict, today: date, hour: int, props: dict, groups: tuple) -> bool:
    """Zapisuje decyzje planu, gdy minęła pełna godzina slotu (6/12/18) i dla niej jeszcze nie ma zapisu. True = coś zapisano."""
    slot = max((s for s in SLOTS if hour >= s), default=None)
    if slot is None or not isinstance(props, dict):
        return False
    day = snaps.setdefault(today.isoformat(), {})
    if str(slot) in day:
        return False
    day[str(slot)] = {name: s for name, k1, k2 in groups if (s := _sig(props, k1, k2)) is not None}
    for k in sorted(snaps)[:-KEEP_DAYS]:
        snaps.pop(k, None)
    return True


def view(snaps: dict, today: date, days: int = 7) -> dict[str, Any]:
    rows = []
    changes = 0
    pairs = 0
    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        rec = snaps.get(d) if isinstance(snaps, dict) else None
        if not isinstance(rec, dict) or not rec:
            continue
        slots = {s: rec.get(str(s)) for s in SLOTS}
        prev = None
        for s in SLOTS:
            cur = slots[s]
            if cur is None:
                continue
            if prev is not None:
                for name in set(prev) | set(cur):
                    pairs += 1
                    if prev.get(name) != cur.get(name):
                        changes += 1
            prev = cur
        rows.append({"date": d, "slots": {str(s): slots[s] for s in SLOTS}})
    share = round(100.0 * changes / pairs) if pairs else None
    if share is None:
        text = "Za mało zapisów — oś decyzji zbiera dane od dziś (zapis o 6:00, 12:00 i 18:00)."
    elif share <= 15:
        text = f"Plan jest stabilny: w ciągu doby zmieniał {share}% decyzji."
    else:
        text = f"Plan zmienia decyzje dość często: w ciągu doby {share}% okien miało inne godziny albo zostało dodane/pominięte."
    return {"rows": rows, "changes": changes, "compared": pairs, "changed_pct": share, "text": text}


def wear_days(ledger_days: dict, stats_days: dict, today: date, wear: float, n: int = 7) -> dict[str, Any]:
    """Zużycie baterii w zł: rozładowana energia × koszt zużycia 1 kWh; bilans dnia przed i po uwzględnieniu zużycia."""
    out = []
    for i in range(n):
        d = (today - timedelta(days=i)).isoformat()
        sd, ld = stats_days.get(d), ledger_days.get(d)
        dis = sd.get("dis") if isinstance(sd, dict) else None
        if not isinstance(dis, (int, float)):
            continue
        net = None
        if isinstance(ld, dict):
            try:
                net = round(float(ld.get("revenue", 0)) - float(ld.get("cost", 0)), 2)
            except (TypeError, ValueError):
                net = None
        w = round(float(dis) * wear, 2)
        out.append({"date": d, "dis_kwh": round(float(dis), 1), "wear_pln": w, "net": net, "net_after": None if net is None else round(net - w, 2)})
    tot = round(sum(r["wear_pln"] for r in out), 2)
    return {"wear_per_kwh": round(wear, 4), "days": out, "total_wear": tot}
