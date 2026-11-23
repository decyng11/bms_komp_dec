"""Własne źródło cen godzinowych: RCE z publicznego API PSE → cena zakupu dopasowana do Twojej taryfy dynamicznej (np. Pstryk).

Po co: ceny na jutro bez integracji operatora cen. RCE (PSE) jest publiczne i bez tokenu; cena zakupu = a × RCE + b(godzina),
gdzie `a` (np. VAT) i `b` (opłaty, narzut, strefy) są UCZONE z ostatnich dób na porównaniu z prawdziwą ceną zakupu, którą
EMS już zapisuje godzina po godzinie. Dopasowanie ma własną ocenę (błąd w zł/kWh) i pokazuje ją użytkownikowi: gdy RCE
nie odpowiada ceninkowi (np. operator liczy z innej giełdy), jakość wyjdzie „słaba” i nie należy na tym polegać.

Czysty moduł (bez HA i bez sieci): parsowanie odpowiedzi PSE, dopasowanie, przeliczenie."""
from __future__ import annotations

import math
import re
from datetime import date, timedelta
from statistics import median
from typing import Any
from urllib.parse import quote

PSE_URL = "https://api.raporty.pse.pl/api/rce-pln"
MIN_HOURS_DAY = 20          # doba RCE jest „pełna”, gdy ma ceny z tylu godzin
MIN_FIT_DAYS = 3            # tyle dób z parą (RCE, cena zakupu) trzeba, żeby uczyć
MIN_FIT_PAIRS = 48
A_MIN, A_MAX = 0.3, 3.0     # sensowny mnożnik (VAT 1,23 itp.)
KEEP_DAYS = 20
QUALITY = ((0.012, "idealne"), (0.05, "dobre"), (0.12, "średnie"))      # RMSE w zł/kWh; powyżej „słabe”
EXACT_TOL = 0.01                                    # „co do grosza”: różnica ≤ 1 gr
MIN_WEEKEND_PAIRS = 8


def day_url(d: date) -> str:
    """Adres zapytania o jedną dobę (OData: business_date eq 'RRRR-MM-DD')."""
    return f"{PSE_URL}?$filter={quote(f'business_date eq {chr(39)}{d.isoformat()}{chr(39)}')}"


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    return x if math.isfinite(x) else None


def _start_hour(row: dict) -> int | None:
    """Godzina początku okresu: `period` „00:15 - 00:30” (początek), inaczej `dtime` (KONIEC okresu) − 15 min."""
    per = row.get("period")
    if isinstance(per, str):
        m = re.match(r"\s*(\d{1,2}):(\d{2})", per)
        if m:
            h = int(m.group(1))
            return h if 0 <= h <= 23 else None
    dt = row.get("dtime")
    if isinstance(dt, str):
        m = re.search(r"(\d{1,2}):(\d{2})", dt[10:] if len(dt) > 10 else dt)
        if m:
            minutes = (int(m.group(1)) * 60 + int(m.group(2)) - 15) % (24 * 60)
            return minutes // 60
    return None


def parse_rce(payload: Any, day: date) -> list[float | None] | None:
    """24 średnie godzinowe ceny RCE (zł/kWh) dla `day` z odpowiedzi PSE (PLN/MWh, wpisy 15-minutowe lub godzinowe).
    None, gdy odpowiedź jest zła albo ma za mało godzin (doba jeszcze nieopublikowana)."""
    rows = payload.get("value") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return None
    sums, cnt = [0.0] * 24, [0] * 24
    want = day.isoformat()
    for r in rows:
        if not isinstance(r, dict):
            continue
        bd = str(r.get("business_date") or "")[:10]
        if bd and bd != want:
            continue
        p = _num(r.get("rce_pln"))
        h = _start_hour(r)
        if p is None or h is None:
            continue
        sums[h] += p / 1000.0
        cnt[h] += 1
    out = [round(sums[h] / cnt[h], 4) if cnt[h] else None for h in range(24)]
    return out if sum(1 for v in out if v is not None) >= MIN_HOURS_DAY else None


def _weekend(key: str) -> bool:
    try:
        return date.fromisoformat(str(key)[:10]).weekday() >= 5
    except ValueError:
        return False


def fit(rce: dict[str, list[float | None]], buy: dict[str, list[float | None]]) -> dict[str, Any] | None:
    """Uczy `cena = a × RCE + b[godzina]` z par (RCE, prawdziwa cena zakupu) z tych samych godzin.

    a — z odchyleń w obrębie godziny (stałe opłaty i strefy nie wpływają na nachylenie), b[h] — mediana reszt godziny
    (łapie strefy G12 i opłaty). Weekendy i dni robocze mają osobne b[h] (strefy bywają inne), gdy weekendów jest dość.
    Ocena: błąd RMSE oraz odsetek godzin trafionych co do grosza. None, gdy za mało danych."""
    pairs: list[tuple[int, float, float, bool]] = []
    days = set()
    for k, rr in rce.items():
        bb = buy.get(k)
        if not isinstance(rr, list) or not isinstance(bb, list):
            continue
        we = _weekend(k)
        for h in range(min(24, len(rr), len(bb))):
            x, y = _num(rr[h]), _num(bb[h])
            if x is not None and y is not None and y > 0:
                pairs.append((h, x, y, we))
                days.add(k)
    if len(days) < MIN_FIT_DAYS or len(pairs) < MIN_FIT_PAIRS:
        return None
    by_h: dict[int, list[tuple[float, float]]] = {}
    for h, x, y, _w in pairs:
        by_h.setdefault(h, []).append((x, y))
    num = den = 0.0
    for lst in by_h.values():
        if len(lst) < 2:
            continue
        mx, my = sum(p[0] for p in lst) / len(lst), sum(p[1] for p in lst) / len(lst)
        num += sum((x - mx) * (y - my) for x, y in lst)
        den += sum((x - mx) ** 2 for x, _ in lst)
    a = num / den if den > 1e-9 else 1.0
    a = min(A_MAX, max(A_MIN, a))

    def offsets(sel) -> list[float | None]:
        grp: dict[int, list[float]] = {}
        for h, x, y, w in pairs:
            if sel(w):
                grp.setdefault(h, []).append(y - a * x)
        return [median(grp[h]) if len(grp.get(h, [])) >= 2 else None for h in range(24)]

    b_all = offsets(lambda w: True)
    known = [v for v in b_all if v is not None]
    if not known:
        return None
    fill = median(known)
    b_all = [v if v is not None else fill for v in b_all]
    n_we = sum(1 for p in pairs if p[3])
    b_wd_raw, b_we_raw = offsets(lambda w: not w), offsets(lambda w: w)
    split = n_we >= MIN_WEEKEND_PAIRS and (len(pairs) - n_we) >= MIN_WEEKEND_PAIRS
    if split:
        b = [round(v if v is not None else b_all[h], 4) for h, v in enumerate(b_wd_raw)]
        bw: list[float] | None = [round(v if v is not None else b_all[h], 4) for h, v in enumerate(b_we_raw)]
    else:
        b, bw = [round(v, 4) for v in b_all], None
    res = []
    for h, x, y, w in pairs:
        res.append(y - (a * x + ((bw if (w and bw) else b)[h])))
    rmse = math.sqrt(sum(r * r for r in res) / len(res))
    exact = sum(1 for r in res if abs(r) <= EXACT_TOL) / len(res)
    quality = "słabe"
    for lim, name in QUALITY:
        if rmse <= lim:
            quality = name
            break
    return {"a": round(a, 4), "b": b, "bw": bw, "rmse": round(rmse, 4), "exact": round(exact, 3), "max_err": round(max(abs(r) for r in res), 3),
            "pairs": len(pairs), "days": len(days), "quality": quality}


def predict(rce_day: list[float | None] | None, model: dict[str, Any] | None, day: date | None = None) -> list[float | None] | None:
    """Cena zakupu na 24 godziny z RCE doby i dopasowanego modelu (None bez modelu albo bez RCE).
    Dla weekendu (gdy model ma osobne `bw`) używa opłat weekendowych."""
    if not rce_day or not model:
        return None
    a, b = _num(model.get("a")), model.get("b")
    bw = model.get("bw")
    if day is not None and day.weekday() >= 5 and isinstance(bw, list) and len(bw) == 24:
        b = bw
    if a is None or not isinstance(b, list) or len(b) != 24:
        return None
    out: list[float | None] = []
    for h in range(24):
        x, bh = _num(rce_day[h]) if h < len(rce_day) else None, _num(b[h])
        out.append(None if x is None or bh is None else round(a * x + bh, 4))
    return out


def prune(rce: dict[str, Any], today: date) -> dict[str, list[float | None]]:
    """Zostawia ostatnie KEEP_DAYS dób i jutro; wyrzuca śmieci ze złego stanu."""
    lo, hi = today - timedelta(days=KEEP_DAYS), today + timedelta(days=1)
    out: dict[str, list[float | None]] = {}
    for k, v in (rce or {}).items():
        try:
            d = date.fromisoformat(str(k)[:10])
        except ValueError:
            continue
        if lo <= d <= hi and isinstance(v, list) and len(v) == 24:
            out[d.isoformat()] = [_num(x) for x in v]
    return out


def series(day: date, prices: list[float | None] | None, tz_offset: str = "") -> list[dict[str, Any]]:
    """Lista {start, price} w formacie, który czytnik cen EMS (i inne integracje) rozumie."""
    if not prices:
        return []
    return [{"start": f"{day.isoformat()}T{h:02d}:00:00{tz_offset}", "price": p} for h, p in enumerate(prices) if p is not None]
