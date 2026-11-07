"""Taryfa strefowa (G12w i pokrewne): konfigurowalne okna szczytu + nauka cen peak/off-peak."""
from __future__ import annotations

import logging
import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .helpers import ThrottledStore
from .holidays_pl import is_holiday

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = "bms_komp_dec_g12w_prices"
STORAGE_VERSION = 1
PEAK_HOURS_MORNING = (6, 13)      # domyślne okna (Tauron G12w) — zachowane dla zgodności
PEAK_HOURS_EVENING = (15, 22)
DEFAULT_PEAKS = (PEAK_HOURS_MORNING, PEAK_HOURS_EVENING)
DEFAULT_PEAKS_TEXT = "6-13,15-22"
DEFAULT_OFF_PEAK_RATIO = 0.71  # off_peak ≈ 0.71 * peak (Tauron G12w)
MAX_PEAK_SPANS = 2             # planer ma dwa zestawy sprzedaży (poranny/wieczorny)

# Tryb taryfy: „zone” = stałe okna z konfiguracji (G11/G12/G12w…), „dynamic” = okna liczone z godzinowych cen zakupu
# (np. Pstryk), „auto” = godzinowe ceny, gdy encja zakupu je podaje i ceny naprawdę się zmieniają (≥ 4 poziomy w dobie).
TARIFF_MODES = ("auto", "zone", "dynamic")
TARIFF_MODE_LEGACY = "zone"        # wpisy sprzed 0.8.0 (bez tego pola) zachowują dotychczasowe zachowanie
TARIFF_MODE_NEW = "auto"           # domyślnie dla nowych instalacji
DYN_MIN_LEVELS = 4                 # auto: lista z ≤ 3 poziomami cen to taryfa strefowa, nie dynamiczna
DYN_CHEAP_HOURS = 6                # „tania cena” doby = średnia 6 najtańszych godzin
DYN_MARGIN = 0.05                  # zł/kWh ponad stratę cyklu — dopiero wtedy godzina jest „droga”
DYN_BLIP_SHARE = 0.10             # szczyt o „wadze” < 10% największego to drobny skok ceny, a nie osobne okno

_NONE_WORDS = {"brak", "none", "no", "nie", "flat", "g11", "-", "—", "–"}
_SPAN_RE = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?\s*[-–—]\s*(\d{1,2})(?::(\d{2}))?\s*$")


def parse_peaks(text: str | None) -> tuple[tuple[tuple[int, int], ...] | None, str | None]:
    """„6-13,15-22” → ((6, 13), (15, 22)). Zwraca (okna, błąd); przy błędzie okna = None.

    „brak” oznacza taryfę jednostrefową (bez szczytu). Okna tylko w pełnych godzinach, rosnąco,
    bez przecięć przez północ (dla szczytu przez północ podaj dwa okna, np. „0-6,22-24”)."""
    raw = (text or "").strip().lower()
    if not raw:
        return DEFAULT_PEAKS, None
    if raw in _NONE_WORDS:
        return (), None
    spans: list[tuple[int, int]] = []
    for part in re.split(r"[;,]", raw):
        if not part.strip():
            continue
        m = _SPAN_RE.match(part)
        if not m:
            return None, f"nieczytelne okno „{part.strip()}” (oczekiwano np. 6-13)"
        a, am, b, bm = int(m.group(1)), m.group(2), int(m.group(3)), m.group(4)
        if (am not in (None, "00")) or (bm not in (None, "00")):
            return None, f"okno „{part.strip()}” — dozwolone tylko pełne godziny"
        if not (0 <= a < b <= 24):
            return None, f"okno „{part.strip()}” — godziny muszą spełniać 0 ≤ start < koniec ≤ 24"
        spans.append((a, b))
    if not spans:
        return None, "brak okien"
    spans.sort()
    merged: list[list[int]] = []
    for a, b in spans:
        if merged and a < merged[-1][1]:
            return None, f"okna {merged[-1][0]}-{merged[-1][1]} i {a}-{b} nachodzą na siebie"
        if merged and a == merged[-1][1]:
            merged[-1][1] = b                       # styczne okna scalamy
        else:
            merged.append([a, b])
    if len(merged) > MAX_PEAK_SPANS:
        return None, f"obsługiwane są najwyżej {MAX_PEAK_SPANS} okna szczytu"
    return tuple((a, b) for a, b in merged), None


@dataclass(frozen=True)
class TariffProfile:
    """Opis taryfy: kiedy trwa szczyt i czy weekendy/święta są całodobowo pozaszczytowe."""
    peaks: tuple[tuple[int, int], ...] = DEFAULT_PEAKS
    weekend_offpeak: bool = True
    holiday_offpeak: bool = True

    def peak_day(self, d: date) -> bool:
        """Czy w danym dniu obowiązują w ogóle godziny szczytu."""
        if not self.peaks:
            return False
        if self.weekend_offpeak and d.weekday() >= 5:
            return False
        if self.holiday_offpeak and is_holiday(d):
            return False
        return True

    def is_peak(self, dt: datetime) -> bool:
        if not self.peak_day(dt.date()):
            return False
        h = dt.hour
        return any(a <= h < b for a, b in self.peaks)

    def night_window(self) -> tuple[int, int] | None:
        """(start, koniec) taniego okna przechodzącego przez północ: od końca ostatniego szczytu
        do początku pierwszego (np. (22, 6)). None, gdy taki przedział nie istnieje."""
        if not self.peaks:
            return None
        start, end = self.peaks[-1][1], self.peaks[0][0]
        if start >= 24 and end <= 0:
            return None
        return start, end

    def midday_window(self) -> tuple[int, int] | None:
        """Tanie okno między dwoma szczytami (np. (13, 15)); None, gdy szczyt jest jeden."""
        if len(self.peaks) < 2:
            return None
        a, b = self.peaks[0][1], self.peaks[1][0]
        return (a, b) if b > a else None

    # --- interfejs „na dany dzień” (wspólny z taryfą dynamiczną); w taryfie strefowej okna są co dzień takie same
    def peaks_for(self, d: date) -> tuple[tuple[int, int], ...]:
        return self.peaks

    def midday_window_for(self, d: date) -> tuple[int, int] | None:
        return self.midday_window()

    def night_start_for(self, d: date) -> int | None:
        return self.peaks[-1][1] if self.peaks else None

    def night_bounds(self, now: datetime) -> tuple[int | None, int | None, int | None] | None:
        """(początek nocy dziś, pierwszy szczyt dziś, pierwszy szczyt jutro) — w taryfie strefowej (ns, ne, ne)."""
        nw = self.night_window()
        return None if nw is None else (nw[0], nw[1], nw[1])

    def dynamic_for(self, d: date) -> bool:
        return False

    @property
    def mode(self) -> str:
        return "zone"

    def label(self) -> str:
        return ", ".join(f"{a}–{b}" for a, b in self.peaks) if self.peaks else "brak (taryfa jednostrefowa)"

    def as_text(self) -> str:
        return ",".join(f"{a}-{b}" for a, b in self.peaks) if self.peaks else "brak"


def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def price_levels(prices) -> int:
    """Ile różnych poziomów cen (z dokładnością do 0,001 zł) ma lista godzinowa."""
    return len({round(float(p), 3) for p in (prices or []) if _finite(p)})


def derive_peaks(prices, eff: float = 0.9, min_hours: int = 22) -> tuple[tuple[int, int], ...] | None:
    """Okna „szczytu” z godzinowych cen zakupu jednej doby (lista 24 wartości, None = brak ceny).

    Szczyt = godziny, w których prąd z sieci jest droższy niż energia naładowana w najtańszych godzinach doby
    po stratach cyklu baterii (+ DYN_MARGIN) — wtedy opłaca się brać energię z baterii zamiast z sieci.
    Planer ma dwa zestawy sprzedaży i jedno okno „między szczytami”, więc wynik to najwyżej 2 okna:
    luki 1-godzinne są scalane, a nadmiarowe okna łączone z najbliższym sąsiadem (luka staje się szczytem —
    ostrożnie: bateria ma wtedy pokryć więcej godzin). Za mało cen → None (wtedy okna z konfiguracji)."""
    if not isinstance(prices, (list, tuple)):
        return None
    vals = [(h, float(p)) for h, p in enumerate(list(prices)[:24]) if _finite(p)]
    if len(vals) < max(1, min_hours):
        return None
    eff = min(1.0, max(0.5, float(eff) if _finite(eff) else 0.9))
    cheap = sorted(p for _, p in vals)[:DYN_CHEAP_HOURS]
    low = sum(cheap) / len(cheap)
    thr = low + abs(low) * (1.0 / eff - 1.0) + DYN_MARGIN
    price = dict(vals)
    runs: list[list[int]] = []
    for h, p in vals:
        if p < thr:
            continue
        if runs and h - runs[-1][1] <= 1:
            runs[-1][1] = h + 1
        else:
            runs.append([h, h + 1])

    def excess(r: list[int]) -> float:     # „waga” szczytu: o ile drożej niż próg, zsumowane po godzinach
        return sum(max(0.0, price.get(h, thr) - thr) for h in range(r[0], r[1]))

    if len(runs) > MAX_PEAK_SPANS:
        # najpierw odrzuć drobne skoki ceny (np. jedna godzina tuż nad progiem) — nie są powodem do przesuwania okien
        top = max(excess(r) for r in runs)
        runs = [r for r in runs if excess(r) >= DYN_BLIP_SHARE * top]
    while len(runs) > MAX_PEAK_SPANS:
        i = min(range(len(runs) - 1), key=lambda k: (runs[k + 1][0] - runs[k][1], k))
        runs[i][1] = runs[i + 1][1]
        del runs[i + 1]
    return tuple((a, b) for a, b in runs)


class DynamicTariffProfile:
    """Taryfa z godzinowych cen zakupu (np. Pstryk): okna szczytu liczone osobno dla każdego dnia.

    Ma ten sam interfejs co TariffProfile. Dzień bez pełnej listy cen (np. jutro przed publikacją) albo —
    w trybie „auto” — z cenami w ≤ 3 poziomach (to taryfa strefowa) używa okien z konfiguracji (`base`)."""

    def __init__(self, base: TariffProfile, prices_fn: Callable[[date], list | None], mode: str = "auto",
                 eff_fn: Callable[[], float] | None = None, source: str | None = None) -> None:
        self.base = base
        self._prices_fn = prices_fn
        self._mode = mode if mode in ("auto", "dynamic") else "auto"
        self._eff_fn = eff_fn
        self.source = source
        self._cache: dict[date, tuple[tuple, tuple[tuple[int, int], ...] | None]] = {}

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def weekend_offpeak(self) -> bool:
        return self.base.weekend_offpeak

    @property
    def holiday_offpeak(self) -> bool:
        return self.base.holiday_offpeak

    @staticmethod
    def _today() -> date:
        return dt_util.now().date()

    def spans_for(self, d: date) -> tuple[tuple[int, int], ...] | None:
        """Okna szczytu z cen dla dnia d albo None (brak cen / taryfa strefowa w trybie auto)."""
        try:
            prices = self._prices_fn(d)
            eff = self._eff_fn() if self._eff_fn else 0.9
            key = (tuple(prices) if prices else None, eff)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("EMS: nie udało się odczytać cen godzinowych dla %s", d, exc_info=True)
            return None
        hit = self._cache.get(d)
        if hit is not None and hit[0] == key:
            return hit[1]
        spans = None
        try:
            if prices and (self._mode == "dynamic" or price_levels(prices) >= DYN_MIN_LEVELS):
                spans = derive_peaks(prices, eff)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("EMS: nie udało się wyznaczyć okien taryfy dynamicznej dla %s", d, exc_info=True)
            spans = None
        if len(self._cache) > 8:
            self._cache.clear()
        self._cache[d] = (key, spans)
        return spans

    def invalidate(self) -> None:
        self._cache.clear()

    def dynamic_for(self, d: date) -> bool:
        return self.spans_for(d) is not None

    def peaks_for(self, d: date) -> tuple[tuple[int, int], ...]:
        s = self.spans_for(d)
        return s if s is not None else self.base.peaks_for(d)

    @property
    def peaks(self) -> tuple[tuple[int, int], ...]:
        return self.peaks_for(self._today())

    def peak_day(self, d: date) -> bool:
        s = self.spans_for(d)
        return bool(s) if s is not None else self.base.peak_day(d)

    def is_peak(self, dt: datetime) -> bool:
        s = self.spans_for(dt.date())
        if s is None:
            return self.base.is_peak(dt)
        return any(a <= dt.hour < b for a, b in s)

    def midday_window_for(self, d: date) -> tuple[int, int] | None:
        p = self.peaks_for(d)
        if len(p) < 2:
            return None
        a, b = p[0][1], p[1][0]
        return (a, b) if b > a else None

    def midday_window(self) -> tuple[int, int] | None:
        return self.midday_window_for(self._today())

    def night_start_for(self, d: date) -> int | None:
        p = self.peaks_for(d)
        return p[-1][1] if p else None

    def night_bounds(self, now: datetime) -> tuple[int | None, int | None, int | None] | None:
        """(początek taniej nocy dziś, pierwszy szczyt dziś, pierwszy szczyt jutro); None w polu = brak szczytu."""
        d0 = now.date()
        pt, pm = self.peaks_for(d0), self.peaks_for(d0 + timedelta(days=1))
        ns = pt[-1][1] if pt else 0
        return ns, (pt[0][0] if pt else None), (pm[0][0] if pm else None)

    def night_window(self) -> tuple[int, int] | None:
        d0 = self._today()
        pt, pm = self.peaks_for(d0), self.peaks_for(d0 + timedelta(days=1))
        if not pm:
            return None
        start, end = (pt[-1][1] if pt else 0), pm[0][0]
        if start >= 24 and end <= 0:
            return None
        return start, end

    def label(self) -> str:
        d0 = self._today()
        txt = ", ".join(f"{a}–{b}" for a, b in self.peaks_for(d0)) or "brak drogich godzin"
        if self.dynamic_for(d0):
            return f"dynamiczna (z cen godzinowych): szczyt dziś {txt}"
        return f"dynamiczna — dziś brak pełnych cen godzinowych, okna z konfiguracji: {txt}"

    def as_text(self) -> str:
        p = self.peaks
        return ",".join(f"{a}-{b}" for a, b in p) if p else "brak"


_PROFILE: TariffProfile | DynamicTariffProfile = TariffProfile()


def get_profile() -> TariffProfile | DynamicTariffProfile:
    return _PROFILE


def set_profile(profile: TariffProfile | DynamicTariffProfile | None) -> None:
    global _PROFILE
    _PROFILE = profile or TariffProfile()


def tariff_mode_from_config(cfg: dict) -> str:
    """Tryb taryfy z ustawień; brak pola (wpis sprzed 0.8.0) albo zła wartość → „zone” (bez zmiany zachowania)."""
    m = str(cfg.get("tariff_mode") or TARIFF_MODE_LEGACY).strip().lower()
    return m if m in TARIFF_MODES else TARIFF_MODE_LEGACY


def make_profile(cfg: dict, prices_fn: Callable[[date], list | None] | None = None,
                 eff_fn: Callable[[], float] | None = None, source: str | None = None):
    """Profil taryfy z ustawień: strefowy albo dynamiczny (gdy tryb ≠ „zone” i jest źródło cen godzinowych)."""
    base = profile_from_config(cfg)
    mode = tariff_mode_from_config(cfg)
    if mode == "zone" or prices_fn is None:
        return base
    return DynamicTariffProfile(base, prices_fn, mode=mode, eff_fn=eff_fn, source=source)


def profile_from_config(cfg: dict) -> TariffProfile:
    """Profil z ustawień integracji; błędne wartości → domyślna taryfa G12w (z ostrzeżeniem w logu)."""
    peaks, err = parse_peaks(str(cfg.get("tariff_peaks") or ""))
    if peaks is None:
        _LOGGER.warning("EMS: nieprawidłowe okna szczytu taryfy (%s) — używam domyślnych %s", err, DEFAULT_PEAKS_TEXT)
        peaks = DEFAULT_PEAKS
    return TariffProfile(
        peaks=peaks,
        weekend_offpeak=bool(cfg.get("tariff_weekend_offpeak", True)),
        holiday_offpeak=bool(cfg.get("tariff_holiday_offpeak", True)),
    )


def is_g12w_peak(dt: datetime) -> bool:
    """Czy dt leży w szczycie bieżącej taryfy (domyślnie G12w: Pn-Pt 6-13 i 15-22).

    Domyślnie weekendy i święta ustawowe są całodobowo pozaszczytowe (jak w G12w) —
    sprawdź swoją taryfę; okna i te założenia można zmienić w konfiguracji integracji."""
    return _PROFILE.is_peak(dt)


def next_offpeak_window(now: datetime) -> tuple[datetime, datetime, bool] | None:
    """(początek, koniec, trwa_teraz) najbliższego okna pozaszczytowego (szukamy do 8 dni naprzód — długi weekend z świętem to kilka dób bez szczytu)."""
    if not _PROFILE.peaks:
        return None                      # taryfa jednostrefowa — nie ma „taniego okna”
    t = now.replace(minute=0, second=0, microsecond=0)
    if not is_g12w_peak(t):
        start, in_now = t, True
    else:
        start, in_now = None, False
        for i in range(1, 193):
            c = t + timedelta(hours=i)
            if not is_g12w_peak(c):
                start = c
                break
        if start is None:
            return None
    end = start
    for _ in range(192):
        end = end + timedelta(hours=1)
        if is_g12w_peak(end):
            break
    return start, end, in_now


class G12wTariff:
    """Uczy się cen peak/off-peak z pojedynczego sensora bieżącej ceny."""

    def __init__(self, hass: HomeAssistant, entity_id: str,
                 hourly_fn: Callable[[date], list | None] | None = None) -> None:
        self.hass = hass
        self.entity_id = entity_id
        self._hourly_fn = hourly_fn      # ceny godzinowe zakupu (taryfa dynamiczna); None = tylko kubełki
        self._store = ThrottledStore(hass, STORAGE_VERSION, STORAGE_KEY, delay=60)
        self.prices: dict[str, float | None] = {"peak": None, "off_peak": None}

    async def async_load(self) -> None:
        data = await self._store.async_load()
        if isinstance(data, dict) and isinstance(data.get("prices"), dict):
            for k in ("peak", "off_peak"):
                v = data["prices"].get(k)
                if _finite(v):
                    self.prices[k] = float(v)

    def sample(self) -> None:
        """Zapisz bieżącą cenę do bucketu peak/off_peak."""
        st = self.hass.states.get(self.entity_id)
        if not st or st.state in ("unknown", "unavailable", ""):
            return
        try:
            price = float(st.state)
        except (ValueError, TypeError):
            return
        if not math.isfinite(price) or price <= 0 or price > 20:
            return      # „nan”/„inf” w stanie encji nie może trafić do nauczonych cen
        now = dt_util.now()
        if _PROFILE.dynamic_for(now.date()):
            return      # taryfa dynamiczna: dwa kubełki z jednej bieżącej ceny dałyby przypadkowe wartości
        bucket = "peak" if is_g12w_peak(now) else "off_peak"
        if self.prices.get(bucket) != price:
            self.prices[bucket] = price
            self._store.request_save(lambda: {"prices": dict(self.prices)})

    def hourly_price(self, dt: datetime) -> float | None:
        """Cena godzinowa zakupu z listy (taryfa dynamiczna) albo None."""
        if self._hourly_fn is None:
            return None
        try:
            arr = self._hourly_fn(dt.date())
        except Exception:  # noqa: BLE001
            return None
        if not arr or dt.hour >= len(arr):
            return None
        v = arr[dt.hour]
        return float(v) if _finite(v) else None

    def get_price(self, dt: datetime) -> float:
        """Cena dla danego czasu: godzinowa (taryfa dynamiczna) albo nauczona strefowa (+ fallback ratio)."""
        if _PROFILE.dynamic_for(dt.date()):
            hp = self.hourly_price(dt)
            if hp is not None:
                return hp
        bucket = "peak" if is_g12w_peak(dt) else "off_peak"
        p = self.prices.get(bucket)
        if _finite(p):
            return p
        if bucket == "off_peak":
            peak = self.prices.get("peak")
            if _finite(peak):
                return peak * DEFAULT_OFF_PEAK_RATIO
        else:
            off = self.prices.get("off_peak")
            if _finite(off):
                return off / DEFAULT_OFF_PEAK_RATIO
        return 0.7  # generic fallback

    def off_peak_slots(self, start: datetime, end: datetime) -> list[tuple[datetime, datetime, float]]:
        """Zwraca listę slotów off-peak (start, end, price) w zakresie [start, end)."""
        slots: list[tuple[datetime, datetime, float]] = []
        cur = start.replace(minute=0, second=0, microsecond=0)
        step = timedelta(hours=1)
        while cur < end:
            if not is_g12w_peak(cur):
                slots.append((cur, cur + step, self.get_price(cur)))
            cur += step
        return slots
