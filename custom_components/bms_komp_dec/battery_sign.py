"""Znak mocy baterii: czy ładowanie to wartość dodatnia, czy ujemna.

Falowniki różnie raportują moc baterii (Deye przez ha-solarman: ładowanie < 0, rozładowanie > 0;
inne marki odwrotnie). Zamiast zaszytej stałej w karcie:
  1. ręczne ustawienie `number.bms_battery_charge_sign` (−1 / +1) ma pierwszeństwo,
  2. inaczej uczymy się z danych: gdy SOC rośnie, a średnia moc ma dany znak, to ten znak = ładowanie,
  3. dopóki dane nie są jednoznaczne, obowiązuje konwencja Deye (−1), więc stan jest taki sam jak dotąd.
"""
from __future__ import annotations

from collections import deque
from typing import Any

DEFAULT_SIGN = -1                 # konwencja Deye: ładowanie = moc ujemna
SAMPLE_EVERY_S = 60               # próbkowanie (tick co 30 s → zapis co ~minutę)
WINDOW_S = 15 * 60                # okno porównania SOC
KEEP_S = 40 * 60
MIN_ABS_POWER_W = 300.0           # słabszy przepływ jest zbyt niepewny (szum, pobór własny)
MIN_DELTA_SOC = 2.0               # SOC jest zwykle całkowity — mniej to za mało
MIN_SAME_SIGN = 0.8               # ułamek próbek o tym samym znaku w oknie
MAX_GAP_S = 150                   # największa przerwa między próbkami w oknie
MIN_VOTES = 4
MIN_RATIO = 0.8
MAX_VOTES = 40


class SignLearner:
    def __init__(self, votes: dict[str, int] | None = None) -> None:
        v = votes if isinstance(votes, dict) else {}
        self.votes = {"pos": int(v.get("pos", 0) or 0), "neg": int(v.get("neg", 0) or 0)}
        self._buf: deque[tuple[float, float, float]] = deque()    # (ts, soc, power)
        self._last_sample = 0.0
        self._last_vote = 0.0

    # ---------------------------------------------------------------- uczenie
    def add(self, ts: float, soc: float | None, power: float | None) -> bool:
        """Dodaje próbkę; zwraca True, gdy powstał nowy głos (do zapisu stanu)."""
        if soc is None or power is None:
            return False
        if ts - self._last_sample < SAMPLE_EVERY_S - 1:
            return False
        self._last_sample = ts
        self._buf.append((ts, float(soc), float(power)))
        while self._buf and ts - self._buf[0][0] > KEEP_S:
            self._buf.popleft()
        if ts - self._last_vote < WINDOW_S:
            return False
        old = [s for s in self._buf if ts - s[0] >= WINDOW_S - SAMPLE_EVERY_S]
        if not old:
            return False
        start = old[-1]                                  # najświeższa próbka, która jest już „stara”
        span = [s for s in self._buf if s[0] >= start[0]]
        if len(span) < 5:
            return False
        # dane muszą być ciągłe (restart HA / brak odczytu psuje porównanie SOC)
        if any(b[0] - a[0] > MAX_GAP_S for a, b in zip(span, span[1:])):
            return False
        d_soc = span[-1][1] - start[1]
        avg = sum(s[2] for s in span) / len(span)
        if abs(d_soc) < MIN_DELTA_SOC or abs(avg) < MIN_ABS_POWER_W:
            return False
        # SOC ma zmieniać się w jedną stronę (przy zmiennym obciążeniu nie wnioskujemy)
        against = sum(1 for a, b in zip(span, span[1:]) if (b[1] - a[1]) * d_soc < 0)
        if against > 1:
            return False
        same = sum(1 for s in span if (s[2] > 0) == (avg > 0) and abs(s[2]) > 50) / len(span)
        if same < MIN_SAME_SIGN:
            return False
        charging_positive = (d_soc > 0) == (avg > 0)     # SOC rośnie przy dodatniej mocy (lub maleje przy ujemnej)
        self.votes["pos" if charging_positive else "neg"] += 1
        tot = self.votes["pos"] + self.votes["neg"]
        if tot > MAX_VOTES:                               # starsze głosy tracą na wadze
            self.votes = {k: int(round(v / 2)) for k, v in self.votes.items()}
        self._last_vote = ts
        return True

    # --------------------------------------------------------------- odczyt
    def detected(self) -> int | None:
        pos, neg = self.votes["pos"], self.votes["neg"]
        tot = pos + neg
        if tot < MIN_VOTES:
            return None
        if pos / tot >= MIN_RATIO:
            return 1
        if neg / tot >= MIN_RATIO:
            return -1
        return None

    def result(self, manual: float | None) -> dict[str, Any]:
        """{'sign': ±1, 'source': 'ręcznie'|'wykryty'|'domyślny', 'votes': {...}} (sign = znak mocy przy ŁADOWANIU)."""
        if manual is not None and abs(manual) >= 0.5:
            return {"sign": 1 if manual > 0 else -1, "source": "ręcznie", "votes": dict(self.votes)}
        det = self.detected()
        if det is not None:
            return {"sign": det, "source": "wykryty z danych", "votes": dict(self.votes)}
        return {"sign": DEFAULT_SIGN, "source": "domyślny (Deye)", "votes": dict(self.votes)}
