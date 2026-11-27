/**
 * EMS Centrum Energii - Integracja
 * Numer wersji: stała CARD_VERSION (niżej) — Układ: Pogoda -> Funkcje -> Sankey -> Bilans · zakładka Zysk i log
 */
(function () {
  'use strict';
  // Ochrona przed podwójnym wykonaniem (extra_js_url + zasób Lovelace ładują ten sam plik).
  if (window.__bmsPanelLoaded) return;
  window.__bmsPanelLoaded = true;
  console.info('>>> EMS PANEL v0.3.0 ZAŁADOWANY <<<');
  // true = ujemna moc baterii oznacza ładowanie (Deye/ha-solarman). Nadpisywane z backendu
  // (atrybut battery_charge_sign sensora reserve_soc: ręczne ustawienie albo wykryte z danych).
  let INVERT_BATTERY_SIGN = true;

  // Ładowanie Chart.js (dla wykresu historii): najpierw kopia z HA (frontend/vendor), a gdy jej nie ma — CDN.
  // Adapter dat ładujemy dopiero po Chart.js i w ustalonej kolejności (wcześniej oba skrypty ścigały się ze sobą).
  if (!window.__bmsChartLoading) {
    window.__bmsChartLoading = true;
    const VENDOR = '/bms_komp_dec/vendor/';
    const CDN_CHART = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js';
    const CDN_ADAPTER = 'https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js';
    const loadScript = (src) => new Promise((resolve) => {
      const el = document.createElement('script');
      el.src = src; el.async = false;
      el.onload = () => resolve(true);
      el.onerror = () => { el.remove(); resolve(false); };
      document.head.appendChild(el);
    });
    const adapterOk = () => {
      try { if (!window.Chart || !window.Chart._adapters || !window.Chart._adapters._date) return false; new window.Chart._adapters._date({}).formats(); return true; } catch (e) { return false; }
    };
    (async () => {
      try {
        if (!window.Chart) {
          if (!(await loadScript(VENDOR + 'chart.umd.min.js')) || !window.Chart) await loadScript(CDN_CHART);
        }
        if (window.Chart && !adapterOk()) {
          if (!(await loadScript(VENDOR + 'chartjs-adapter-date-fns.bundle.min.js')) || !adapterOk()) await loadScript(CDN_ADAPTER);
        }
      } catch (e) { console.warn('EMS: ładowanie Chart.js nie powiodło się', e); }
    })();
  }

  // Krótkie, zrozumiałe opisy ustawień zamiast nazw encji. Nazwa encji pojawia się tylko, gdy czegoś brakuje.
  const SETTING_HELP = {
    bateria_sprzedaz_start: 'Godzina, od której bateria sprzedaje energię do sieci (okno 1).',
    bateria_sprzedaz_stop: 'Godzina, o której sprzedaż z baterii się kończy (okno 1).',
    bateria_sprzedaz_start_2: 'Godzina, od której bateria sprzedaje energię do sieci (okno 2, dodatkowe).',
    bateria_sprzedaz_stop_2: 'Godzina, o której sprzedaż z baterii się kończy (okno 2, dodatkowe).',
    grid_import_sell_block_w: 'Gdy z sieci pobierasz więcej niż tyle watów, sprzedaż jest wstrzymywana. 0 = zabezpieczenie wyłączone.',
    grid_charge_power_kw: 'Maksymalna moc ładowania baterii z sieci. EMS wpisuje do falownika odpowiedni prąd (kW ÷ napięcie baterii), a plan liczy okna ładowania z tą mocą — niższa moc to dłuższe okno. 0 = EMS nie zmienia ustawienia falownika.',
    device_shed_soc: 'Gdy SOC baterii spadnie poniżej tej wartości (na 5 minut), EMS wyłącza urządzenia z przełącznikiem (zakładka Urządzenia → Edytuj → Sterowanie), poza oznaczonymi „nie dotyczy”. Włącza je z powrotem po odbiciu SOC o 5 punktów. Działa przy włączonym „Sterowaniu urządzeniami”. 0 = wyłączone.',
    grid_import_limit_kw: 'Limit poboru z sieci dla Twojego przyłącza (np. moc przyłączeniowa minus zapas). Gdy dom i ładowanie razem go przekraczają, EMS zmniejsza prąd ładowania baterii z sieci, a gdy jest zapas — przywraca. Reaguje co kilkanaście sekund, więc krótki szczyt jest możliwy. 0 = wyłączone.',
    pv_plan_pessimism_pct: 'Jak ostrożnie planer traktuje prognozę PV. 0 = środkowa wartość po korekcie, 100 = wersja pesymistyczna (Solcast p10 albo typowy błąd z historii). Wyższa wartość to mniej sprzedaży i więcej ładowania z sieci.',
    grid_import_sell_block_kwh: 'Gdy dziś z sieci pobrano więcej niż tyle kWh, sprzedaż z baterii jest wstrzymana do końca dnia. 0 = zabezpieczenie wyłączone.',
    minimalny_soc_dla_wylaczenia_sprzedazy: 'Gdy bateria spadnie poniżej tego poziomu, sprzedaż się wyłącza i falownik wraca do trybu automatycznego.',
    min_soc_for_sell: 'Tryb „Sprzedaż 6000W” włączy się tylko wtedy, gdy bateria ma co najmniej tyle procent.',
    min_soc_for_pv_export: 'Eksport nadwyżki z PV włączy się tylko wtedy, gdy bateria ma co najmniej tyle procent.',
    min_soc_for_pv_export_stop: 'Gdy bateria spadnie poniżej tego poziomu, eksport z PV zostaje przerwany i wraca zwykłe ładowanie.',
    pv_export_start: 'Od tej godziny PV nie ładuje baterii, tylko oddaje nadwyżkę do sieci (jeśli bateria ma wymagany poziom).',
    pv_export_stop: 'O tej godzinie wraca zwykłe ładowanie baterii z PV.',
    start_grid_charge: 'Godzina, od której bateria ładuje się z sieci (okno 1).',
    stop_grid_charge: 'Godzina, o której ładowanie z sieci się kończy (okno 1).',
    start_grid_charge_2: 'Godzina, od której bateria ładuje się z sieci (okno 2, dodatkowe).',
    stop_grid_charge_2: 'Godzina, o której ładowanie z sieci się kończy (okno 2, dodatkowe).',
  };

  const COLORS = {
    pv: '#fbbf24',
    load: '#22d3ee',
    battery: '#a855f7',
    batteryCharge: '#3b82f6',
    batteryDischarge: '#f97316',
    gridImport: '#f43f5e',
    gridExport: '#10b981',
    actual: '#10b981',
    actualLight: '#34d399',
    forecast: '#60a5fa',
    forecastDark: '#2563eb',
    tomorrow: '#fbbf24',
    tomorrowDark: '#d97706',
    priceMax: '#10b981',
    priceMin: '#f43f5e',
    priceNow: '#fbbf24',
    neutral: '#0a84ff',
    histPrice: '#3b82f6',      
    histPv: '#EAB308',         
    histLoad: '#ec4899',       
    histSoc: '#84cc16',        
    histSell: '#ef4444',       
  };


  // ---------- motyw (jasny / ciemny) ----------
  const THEME_KEY = 'bms_panel_theme';
  const PALETTE = {
    dark:  { muted: '#8e8e93', muted2: '#6e6e73', text: '#ffffff', text2: '#e5e5ea', grid: 'rgba(255,255,255,0.07)', line: 'rgba(255,255,255,0.15)', night: 'rgba(255,255,255,0.04)', tip: 'rgba(44,44,46,0.96)' },
    light: { muted: '#6c6c70', muted2: '#8e8e93', text: '#1c1c1e', text2: '#3a3a3c', grid: 'rgba(60,60,67,0.10)',  line: 'rgba(60,60,67,0.18)',  night: 'rgba(60,60,67,0.06)',  tip: 'rgba(244,244,247,0.97)' },
  };
  const THEME = { mode: 'dark' };
  const TC = (k) => PALETTE[THEME.mode][k];


  // ---------- styl wyglądu (skin): „Klasyczny” (domyślny) albo „Material 3” — wybór w Ustawieniach → Wygląd ----------
  // Działa niezależnie od motywu jasny/ciemny. To wyłącznie warstwa stylów (zmienne i wygląd komponentów) — układ i dane
  // są te same, więc wyłączenie stylu przywraca dokładnie dotychczasowy wygląd.
  const SKIN_KEY = 'bms_panel_skin';
  const SKINS = { classic: 'Klasyczny', m3: 'Material 3', glass: 'Szkło', matrix: 'Matryca', space: 'Przestrzeń', comfort: 'Komfort', hero: 'Bohater' };
  const SKIN_HOME = { glass: 1, matrix: 1, space: 1, comfort: 1, hero: 1 };   // style z własnym ekranem głównym (_drawSkinHome)
  // ---- Układ panelu (Ustawienia → Wygląd → Układ panelu): kolejność i ukrywanie kafelków, osobno dla każdej przeglądarki.
  // Kafelek to element z atrybutem data-tile w szablonie. Zmiana układu tylko przestawia / chowa istniejące elementy —
  // nie zmienia danych ani sterowania. Alerty (cena, próg falownika, status, „dlaczego”) nie są kafelkami i zawsze zostają.
  const LOOK_SKIN_SUB = { classic: 'dotychczasowy wygląd (domyślny)', m3: 'tonalne karty, pigułkowa nawigacja', glass: 'rozmyte szklane karty, pływający pasek', matrix: 'czerń lub papier, kwadratowe piksele, bursztyn',
    space: 'duże szklane okno, boczny pasek na szerokim ekranie', comfort: 'duży nagłówek, bardzo zaokrąglone płaskie karty', hero: 'ciemnozielona karta baterii, białe karty, zielony akcent' };
  const LAYOUT_KEY = 'bms_panel_layout';
  const LAYOUT_TABS = [
    { tab: 'main', label: 'Główny', tiles: [['main-active', 'Aktywne funkcje'], ['main-flow', 'Schemat przepływu mocy (dom)'], ['main-plan', 'Plan dnia']] },
    { tab: 'charts', label: 'Plan', tiles: [['ch-plan24', 'Plan na najbliższe 24 h'], ['ch-hourly', 'Plan godzina po godzinie'], ['ch-override', 'Ręczne nadpisanie planu'], ['ch-history7', 'Historia poziomu baterii (7 dni)'],
      ['ch-energy', 'Historia energii i cen'], ['ch-loadcons', 'Zużycie domu — wczoraj / dziś / jutro'], ['ch-fc7d', 'Prognoza 7-dniowa zużycia domu'], ['ch-hourly-today', 'Profil godzinowy dziś'],
      ['ch-hourly-tomorrow', 'Profil godzinowy jutra'], ['ch-pvprod', 'Produkcja PV dziś — rzeczywista vs prognoza'], ['ch-prices', 'Ceny sprzedaży prądu — dziś vs jutro']] },
    { tab: 'ems', label: 'EMS', tiles: [['ems-profiles', 'Profile pracy'], ['ems-backup', 'Kopia ustawień'], ['ems-schedule', 'Inteligentny harmonogram'], ['ems-sell', 'Przełączniki sprzedaży'], ['ems-pvblock', 'Blokada ładowania PV'], ['ems-export', 'Eksport z PV i blokada ładowania'],
      ['ems-gridpower', 'Moc ładowania z sieci i ochrona przyłącza'], ['ems-gridcharge', 'Ładowanie z sieci']] },
    { tab: 'log', label: 'Zysk i log', tiles: [['log-bilans', 'Bilans w PLN'], ['log-today', 'Co EMS zrobił dziś'], ['log-savings', 'Oszczędności'], ['log-sim', 'Symulacja roczna i zwrot z inwestycji'],
      ['log-accuracy', 'Trafność prognoz'], ['log-report', 'Raport miesięczny'], ['log-health', 'Zdrowie i sprawność baterii'], ['log-auto', 'Funkcje automatyczne'], ['log-journal', 'Dziennik decyzji']] },
    { tab: '*', label: 'Wszystkie zakładki', fixed: true, tiles: [['weather', 'Pogoda i prognoza PV (7 dni)']] },
  ];
  const LAYOUT_HOME = {}, LAYOUT_LABEL = {};
  LAYOUT_TABS.forEach((g) => g.tiles.forEach((t) => { LAYOUT_HOME[t[0]] = g.tab; LAYOUT_LABEL[t[0]] = t[1]; }));
  // ---- Wygląd per użytkownik Home Assistant: styl, motyw i układ podążają za kontem (dane użytkownika HA, komendy websocket
  // frontend/get_user_data i frontend/set_user_data — dostępne dla każdego zalogowanego użytkownika, nie tylko administratora).
  // localStorage zostaje szybkim cache'em (panel rysuje się od razu), a nowszy zapis (znacznik czasu) wygrywa. Brak user.id,
  // starszy HA albo błąd połączenia → wygląd zapisuje się tylko w tej przeglądarce, bez komunikatów. Przeglądarka współdzielona
  // przez dwóch użytkowników nie dziedziczy wyglądu poprzedniego: po zmianie konta lokalny cache jest czyszczony i ściągany od nowa.
  const PREFS_KEY = 'bms_komp_dec_prefs', PREFS_META = 'bms_panel_prefs_meta';
  const PREFS = {
    subs: new Set(), hass: null, uid: '', off: false, bad: false, busy: false, last: 0, timer: null, fails: 0,
    active() { return !!(this.uid && !this.off && !this.bad); },
    meta() { let m = null; try { m = JSON.parse(localStorage.getItem(PREFS_META) || 'null'); } catch (e) { m = null; } return m && typeof m === 'object' ? { u: String(m.u || ''), t: Number(m.t) || 0 } : { u: '', t: 0 }; },
    setMeta(m) { try { localStorage.setItem(PREFS_META, JSON.stringify(m)); } catch (e) { /* storage niedostępny */ } },
    read() {
      const g = (k) => { try { return localStorage.getItem(k); } catch (e) { return null; } };
      let layout = null; try { layout = JSON.parse(g(LAYOUT_KEY) || 'null'); } catch (e) { layout = null; }
      const skin = g(SKIN_KEY), theme = g(THEME_KEY);
      return { v: 1, skin: Object.prototype.hasOwnProperty.call(SKINS, skin) ? skin : null, theme: theme === 'light' || theme === 'dark' ? theme : null, layout: layout && typeof layout === 'object' ? layout : null };
    },
    write(p) {
      const set = (k, v) => { try { if (v === null || v === undefined) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) { /* storage niedostępny */ } };
      set(SKIN_KEY, p && Object.prototype.hasOwnProperty.call(SKINS, p.skin) ? p.skin : null);
      set(THEME_KEY, p && (p.theme === 'light' || p.theme === 'dark') ? p.theme : null);
      set(LAYOUT_KEY, p && p.layout && typeof p.layout === 'object' && !Array.isArray(p.layout) ? JSON.stringify(p.layout) : null);
    },
    has(p) { return !!(p.skin || p.theme || p.layout); },
    // wywoływane przy każdym nowym obiekcie hass; synchronizacja startuje raz na użytkownika
    attach(card, hass) {
      const fresh = !this.subs.has(card); this.subs.add(card);
      if (!hass || typeof hass.callWS !== 'function') return;
      this.hass = hass;
      const uid = hass.user && hass.user.id ? String(hass.user.id) : '';
      if (!uid || this.off) return;
      if (uid === this.uid) { if (fresh) this.pull(false); return; }   // nowa karta na otwartej stronie: odśwież z konta (nie częściej niż co 30 s)
      this.uid = uid; this.fails = 0; this.begin();
    },
    begin() {
      const m = this.meta();
      if (m.u && m.u !== this.uid) { this.write(null); this.setMeta({ u: this.uid, t: 0 }); this.notify(); }   // inny użytkownik tej samej przeglądarki
      else if (m.u !== this.uid) this.setMeta({ u: this.uid, t: m.t });                                          // pierwszy kontakt: lokalne ustawienia zostają, zostaną wysłane na konto
      this.pull(true);
    },
    pull(force) {
      const h = this.hass, uid = this.uid; if (!h || !uid || this.off || this.busy) return;
      const now = Date.now(); if (!force && now - this.last < 30000) return;
      this.last = now; this.busy = true;
      Promise.resolve().then(() => h.callWS({ type: 'frontend/get_user_data', key: PREFS_KEY })).then((r) => {
        this.busy = false; if (uid !== this.uid) return;
        this.fails = 0; this.bad = false;
        const sv = r && r.value && typeof r.value === 'object' && r.value.v === 1 ? r.value : null, st = Number(sv && sv.t) || 0, m = this.meta();
        if (sv && st > m.t) { this.write(sv); this.setMeta({ u: uid, t: st }); this.notify(); }
        else if (m.t > st || (!sv && this.has(this.read()))) { if (!m.t) this.setMeta({ u: uid, t: Date.now() }); this.push(); }
      }).catch((e) => { this.busy = false; this.bad = true; this.fails++; if (this.fails >= 3 || (e && (e.code === 'unknown_command' || e.code === 'unauthorized'))) this.off = true; });
    },
    // lokalna zmiana (styl, motyw, układ): znacznik czasu + wysłanie na konto z krótkim opóźnieniem (seria kliknięć = jeden zapis)
    touch() {
      if (!this.uid) return;
      this.setMeta({ u: this.uid, t: Date.now() });
      if (this.off) return;
      clearTimeout(this.timer); this.timer = setTimeout(() => this.push(), 1200);
    },
    push() {
      const h = this.hass; if (!h || !this.uid || this.off) return;
      const m = this.meta(), val = Object.assign(this.read(), { t: m.t || Date.now() });
      Promise.resolve().then(() => h.callWS({ type: 'frontend/set_user_data', key: PREFS_KEY, value: val })).then(() => { this.fails = 0; this.bad = false; }).catch((e) => {
        this.fails++; this.bad = true;
        if (e && e.code === 'unknown_command') { this.off = true; return; }
        if (this.fails <= 3) { clearTimeout(this.timer); this.timer = setTimeout(() => this.push(), this.fails * 15000); }
      });
    },
    notify() {
      this.subs.forEach((c) => { try { if (!c.isConnected) { this.subs.delete(c); return; } c._prefsApplied(); } catch (e) { /* karta mogła zostać zdjęta */ } });
    },
  };
  try { document.addEventListener('visibilitychange', () => { if (!document.hidden) PREFS.pull(false); }); } catch (e) { /* brak dokumentu */ }
  const SKIN_M3 = `
    :host([data-skin="m3"]) { --bg:#f4fbf8; --card:#e8f1ed; --surface:rgba(23,29,27,0.06); --line:rgba(111,121,117,0.22); --text:#171d1b; --text2:#3f4945; --muted:#566360; --muted2:#6f7975; --accent:#0b6b5d; --green:#1b6c2e; --orange:#8a5a00; --red:#ba1a1a; --input-bg:#f4fbf8; --seg-bg:#dde8e4; --seg-active:#bdf0e3; --shadow:0 1px 2px rgba(0,0,0,0.10),0 1px 3px 1px rgba(0,0,0,0.06); --pf-bg:#e8f1ed; --tonal:#d4e8e1; --on-tonal:#0e201c; --tert:#e1dcff; --on-tert:#1d1a47; --tab-on:#bdf0e3; --tab-on-fg:#00201b; --tab-off:#3f4945; --tab-bg:#e3ede9; --tab-line:transparent; --m3-pv:#c98a00; --m3-pvc:#ffe3a0; --m3-pvt:#6d4b00; --m3-grid:#0a7ea8; --m3-gridc:#c2e8ff; --m3-gridt:#004c69; --m3-sell:#7a55c2; --m3-sellc:#e9deff; --m3-sellt:#3b2470; --m3-batt:#0b6b5d; --m3-idle:#d5dfdb; color-scheme: light; }
    :host([data-skin="m3"][data-theme="dark"]) { --bg:#0f1513; --card:#1a201e; --surface:rgba(255,255,255,0.06); --line:rgba(255,255,255,0.10); --text:#dee4e0; --text2:#bfc9c4; --muted:#9aa5a0; --muted2:#89938f; --accent:#7fd8c6; --green:#8fd99b; --orange:#f3c04f; --red:#ffb4ab; --input-bg:#222826; --seg-bg:#262b29; --seg-active:#005046; --shadow:none; --pf-bg:#1a201e; --tonal:#33433e; --on-tonal:#d4e8e1; --tert:#42407a; --on-tert:#e1dcff; --tab-on:#005046; --tab-on-fg:#bdf0e3; --tab-off:#bfc9c4; --tab-bg:#1b211f; --m3-pv:#f3c04f; --m3-pvc:#5a4300; --m3-pvt:#ffe3a0; --m3-grid:#7bd0f6; --m3-gridc:#004d67; --m3-gridt:#c2e8ff; --m3-sell:#cfbcff; --m3-sellc:#4a3c80; --m3-sellt:#e9deff; --m3-batt:#7fd8c6; --m3-idle:#2a302e; color-scheme: dark; }
    :host([data-skin="m3"]) { font-family: Roboto, "Google Sans", "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif; border-radius: 28px; }
    :host([data-skin="m3"]) .header .title { font-weight: 500; letter-spacing: -0.2px; }
    :host([data-skin="m3"]) .section-title { text-transform: none; font-size: 15px; font-weight: 600; letter-spacing: 0; color: var(--text); padding-left: 4px; }
    :host([data-skin="m3"]) .chart-card, :host([data-skin="m3"]) .soc-card, :host([data-skin="m3"]) .pf-wrapper { border-radius: 24px; box-shadow: none; }
    :host([data-skin="m3"]) .weather-tile { border-radius: 16px; background: var(--card); border: none; }
    :host([data-skin="m3"]) .btn, :host([data-skin="m3"]) .ds-item { border-radius: 20px; background: var(--tonal); color: var(--on-tonal); box-shadow: none; }
    :host([data-skin="m3"]) .btn:hover { background: var(--tonal); filter: brightness(0.96); }
    :host([data-skin="m3"]) .btn.active { background: var(--tert); color: var(--on-tert); border: none; }
    :host([data-skin="m3"]) .why-box { background: var(--tert); color: var(--on-tert); border: none; border-radius: 20px; }
    :host([data-skin="m3"]) .why-box * { color: inherit; }
    :host([data-skin="m3"]) .badge { border-radius: 8px; background: transparent; border: 1px solid var(--muted2); box-shadow: none; color: var(--text2); }
    :host([data-skin="m3"]) .badge.on { background: var(--tonal); color: var(--on-tonal); border-color: transparent; }
    :host([data-skin="m3"]) .price-pill { border-radius: 16px; background: var(--card); box-shadow: none; }
    :host([data-skin="m3"]) .socbar { height: 12px; border-radius: 6px; }
    :host([data-skin="m3"]) .socbar > div { background: var(--accent); border-radius: 6px; }
    :host([data-skin="m3"]) .suggest-item { border-radius: 20px; background: var(--card); }
    :host([data-skin="m3"]) select, :host([data-skin="m3"]) input[type="time"], :host([data-skin="m3"]) input[type="number"] { border-radius: 8px; border: 1px solid var(--muted2); }
    :host([data-skin="m3"]) .sb-item, :host([data-skin="m3"]) .floor-alert { border-radius: 16px; }
    /* ekran główny w układzie Material 3: karta baterii, schemat przepływu, kafelki, pasek planu */
    :host([data-skin="m3"]) .nodes-card { background: transparent; box-shadow: none; padding: 0; border-radius: 0; overflow: visible; }
    :host([data-skin="m3"]) .m3-home { display: flex; flex-direction: column; gap: 10px; }
    :host([data-skin="m3"]) .m3-hero { background: var(--seg-active); color: var(--text); border-radius: 28px; padding: 16px 18px; }
    :host([data-skin="m3"]) .m3-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }
    :host([data-skin="m3"]) .m3-lbl { font-size: 12px; font-weight: 600; letter-spacing: .6px; text-transform: uppercase; opacity: .8; }
    :host([data-skin="m3"]) .m3-big { font-size: 52px; font-weight: 300; letter-spacing: -2px; line-height: 1; margin-top: 8px; }
    :host([data-skin="m3"]) .m3-big span { font-size: 26px; letter-spacing: 0; }
    :host([data-skin="m3"]) .m3-right { text-align: right; font-size: 13px; line-height: 1.5; }
    :host([data-skin="m3"]) .m3-right b { font-size: 18px; font-weight: 600; }
    :host([data-skin="m3"]) .m3-lp { position: relative; height: 12px; border-radius: 6px; background: rgba(0,0,0,0.14); margin-top: 14px; }
    :host([data-skin="m3"]) .m3-lp .v { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 6px; background: var(--accent); }
    :host([data-skin="m3"]) .m3-lp .m { position: absolute; top: -4px; bottom: -4px; width: 2px; border-radius: 1px; background: var(--text); opacity: .55; }
    :host([data-skin="m3"]) .m3-lg { position: relative; height: 16px; margin-top: 6px; font-size: 11px; opacity: .85; }
    :host([data-skin="m3"]) .m3-lg span { position: absolute; transform: translateX(-50%); white-space: nowrap; }
    :host([data-skin="m3"]) .m3-flow { background: var(--card); border-radius: 24px; padding: 10px 12px 8px; }
    :host([data-skin="m3"]) .m3-ct { display: flex; justify-content: space-between; font-size: 14px; font-weight: 600; }
    :host([data-skin="m3"]) .m3-ct small { font-size: 12px; font-weight: 400; color: var(--muted); }
    :host([data-skin="m3"]) .m3-flow svg { width: 100%; height: auto; display: block; }
    :host([data-skin="m3"]) .m3-flow text { font-family: inherit; font-size: 12px; font-weight: 600; }
    :host([data-skin="m3"]) .m3-kpis { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
    :host([data-skin="m3"]) .m3-cap { padding: 11px 13px; border-radius: 20px; background: var(--card); }
    :host([data-skin="m3"]) .m3-day { display: flex; flex-wrap: wrap; gap: 2px 12px; justify-content: center; font-size: 11px; color: var(--muted); padding: 2px 8px 4px; }
    :host([data-skin="m3"]) .m3-kpi { background: var(--card); border-radius: 20px; padding: 11px 13px; min-width: 0; }
    :host([data-skin="m3"]) .m3-kpi .l { font-size: 10.5px; font-weight: 600; letter-spacing: .6px; text-transform: uppercase; color: var(--muted); }
    :host([data-skin="m3"]) .m3-kpi .v { font-size: 20px; font-weight: 500; margin-top: 3px; letter-spacing: -.3px; white-space: nowrap; }
    :host([data-skin="m3"]) .m3-kpi .s { font-size: 11px; color: var(--muted); margin-top: 1px; }
    :host([data-skin="m3"]) .m3-chip .v { font-size: 14px; white-space: normal; line-height: 1.25; }
    :host([data-skin="m3"]) .m3-chips > :last-child:nth-child(odd) { grid-column: 1 / -1; }
    :host([data-skin="m3"]) .m3-strip-card { background: var(--card); border-radius: 24px; padding: 12px 16px 12px; }
    :host([data-skin="m3"]) .m3-strip { display: flex; gap: 2px; height: 30px; margin-top: 10px; }
    :host([data-skin="m3"]) .m3-strip i { flex: 1; border-radius: 4px; }
    :host([data-skin="m3"]) .m3-strip i.now { outline: 2px solid var(--text); outline-offset: 1px; }
    :host([data-skin="m3"]) .m3-ax { display: flex; justify-content: space-between; font-size: 10px; color: var(--muted); margin-top: 4px; }
    :host([data-skin="m3"]) .m3-leg { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
    :host([data-skin="m3"]) .m3-leg span { height: 26px; border-radius: 8px; padding: 0 10px; display: inline-flex; align-items: center; font-size: 12px; font-weight: 600; }
    /* dolna nawigacja: pasek jak w Material 3 — wskaźnik-pigułka za ikoną, etykieta pod spodem */
    :host([data-skin="m3"]) .tabs.bottom { border: none; border-radius: 28px; box-shadow: 0 2px 10px rgba(0,0,0,0.18); padding: 8px 6px 6px; }
    :host([data-skin="m3"]) .tabs.bottom .tab { border-radius: 16px; gap: 4px; }
    :host([data-skin="m3"]) .tabs.bottom .tab.active { background: transparent; color: var(--text); }
    :host([data-skin="m3"]) .tabs.bottom .tab .ti { padding: 3px 16px; border-radius: 14px; transition: background .2s; }
    :host([data-skin="m3"]) .tabs.bottom .tab.active .ti { background: var(--tab-on); color: var(--tab-on-fg); }
    :host([data-skin="m3"]) .tabs.bottom .tab .tls { font-size: 11px; font-weight: 600; }
    :host([data-skin="m3"]) .tabs.bottom .tab.warn .ti::after { right: 6px; top: 0; }
    /* Diagnostyka */
    :host([data-skin="m3"]) .dg-card { border-radius: 24px; box-shadow: none; }
    :host([data-skin="m3"]) .dg-pill { border-radius: 8px; background: transparent; border: 1px solid var(--muted2); color: var(--text2); }
    :host([data-skin="m3"]) .dg-pill.on { background: var(--seg-active); border-color: transparent; color: var(--text); }
    :host([data-skin="m3"]) .dg-tile { border-radius: 16px; }
  `;

  // Kwadratowe „piksele” stylu Matryca (siatka 5×7) — własny zestaw znaków potrzebnych na ekranie głównym (cyfry, jednostki, znaki).
  const SK_GLYPHS = {
    A:'01110,10001,10001,11111,10001,10001,10001', B:'11110,10001,10001,11110,10001,10001,11110', C:'01110,10001,10000,10000,10000,10001,01110',
    D:'11110,10001,10001,10001,10001,10001,11110', E:'11111,10000,10000,11110,10000,10000,11111', G:'01110,10001,10000,10111,10001,10001,01111',
    H:'10001,10001,10001,11111,10001,10001,10001', K:'10001,10010,10100,11000,10100,10010,10001', L:'10000,10000,10000,10000,10000,10000,11111',
    M:'10001,11011,10101,10101,10001,10001,10001', N:'10001,11001,10101,10011,10001,10001,10001', O:'01110,10001,10001,10001,10001,10001,01110',
    P:'11110,10001,10001,11110,10000,10000,10000', R:'11110,10001,10001,11110,10100,10010,10001', S:'01111,10000,10000,01110,00001,00001,11110',
    T:'11111,00100,00100,00100,00100,00100,00100', U:'10001,10001,10001,10001,10001,10001,01110', V:'10001,10001,10001,10001,10001,01010,00100',
    W:'10001,10001,10001,10101,10101,11011,10001', Z:'11111,00001,00010,00100,01000,10000,11111', 'Ł':'10000,10000,10100,11000,10000,10000,11111',
    '0':'01110,10001,10011,10101,11001,10001,01110', '1':'00100,01100,00100,00100,00100,00100,01110', '2':'01110,10001,00001,00010,00100,01000,11111',
    '3':'11110,00001,00001,01110,00001,00001,11110', '4':'00010,00110,01010,10010,11111,00010,00010', '5':'11111,10000,11110,00001,00001,10001,01110',
    '6':'00110,01000,10000,11110,10001,10001,01110', '7':'11111,00001,00010,00100,01000,01000,01000', '8':'01110,10001,10001,01110,10001,10001,01110',
    '9':'01110,10001,10001,01111,00001,00010,01100', '%':'11001,11010,00010,00100,01000,01011,10011', '.':'00000,00000,00000,00000,00000,01100,01100',
    ',':'00000,00000,00000,00000,01100,00100,01000', ':':'00000,01100,01100,00000,01100,01100,00000', '+':'00000,00100,00100,11111,00100,00100,00000',
    '-':'00000,00000,00000,11111,00000,00000,00000', '−':'00000,00000,00000,11111,00000,00000,00000', '/':'00001,00010,00010,00100,01000,01000,10000',
    ' ':'00000,00000,00000,00000,00000,00000,00000',
  };
  // Ikony (siatka 24×24) do schematu przepływu: pełne (Szkło, Przestrzeń, Komfort) i konturowe (Matryca) — własne rysunki.
  const SK_ICO = {
    pv: '<circle cx="12" cy="12" r="4.4"/><path d="M11 1h2v3.5h-2zM11 19.5h2V23h-2zM1 11h3.5v2H1zM19.5 11H23v2h-3.5zM4.2 5.6l1.4-1.4 2.5 2.5-1.4 1.4zM17.9 17.3l1.4-1.4 2.5 2.5-1.4 1.4zM3.6 18.4l2.5-2.5 1.4 1.4-2.5 2.5zM16.5 6.7l2.5-2.5 1.4 1.4-2.5 2.5z"/>',
    home: '<path d="M12 3 2 12h3v8h5.5v-5.5h3V20H19v-8h3z"/>',
    batt: '<path d="M9 2h6v2h2a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h2zM8 11v9h8v-9z"/>',
    grid: '<path d="M16 7V3h-2v4h-4V3H8v4H6v7.5L9.5 18v3h5v-3l3.5-3.5V7z"/>',
  };
  const SK_ICO_LINE = {
    pv: '<circle cx="12" cy="12" r="4"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2"/>',
    home: '<path d="M3 11 12 3l9 8M5 9v11h14V9"/>',
    batt: '<rect x="7" y="4" width="10" height="17" rx="2"/><path d="M10 2h4M10 14l2-4 2 4"/>',
    grid: '<path d="M9 3v5M15 3v5M7 8h10v4a5 5 0 0 1-10 0zM12 17v4"/>',
  };

  // ---------- kolejne style: Szkło, Matryca, Przestrzeń, Komfort (własne projekty, inspirowane znanymi kierunkami wizualnymi) ----------
  // Każdy styl to zmienne kolorów + wygląd komponentów (jak Material 3) i własny ekran główny (_drawSkinHome). Znak „&” w CSS = selektor hosta stylu,
  // „&D” = ten sam styl w ciemnym motywie. Domyślnym pozostaje „Klasyczny”.
  const mkSkin = (n, css) => css.replace(/&D/g, `:host([data-skin="${n}"][data-theme="dark"])`).replace(/&/g, `:host([data-skin="${n}"])`);
  const SK_ALL = ['glass', 'matrix', 'space', 'comfort', 'hero'];
  const skSel = (s) => SK_ALL.map((n) => `:host([data-skin="${n}"]) ${s}`).join(', ');
  const SKIN_COMMON = `
    ${skSel('.chart-card.nodes-card')} { background: transparent; box-shadow: none; padding: 0; border: none; border-radius: 0; overflow: visible; backdrop-filter: none; container: sk / inline-size; }
    ${skSel('.sk-home')} { display: grid; gap: 12px; grid-template-columns: minmax(0, 1fr); }
    ${skSel('.sk-hero')} { display: flex; gap: 16px; align-items: center; padding: 14px 18px; min-width: 0; }
    ${skSel('.sk-ring')} { flex: none; width: 120px; height: 120px; }
    ${skSel('.sk-htx')} { flex: 1; min-width: 0; }
    ${skSel('.sk-lbl')} { font-size: 12px; font-weight: 600; letter-spacing: .6px; text-transform: uppercase; color: var(--muted); }
    ${skSel('.sk-big')} { font-size: 26px; font-weight: 600; letter-spacing: -.5px; margin: 2px 0 4px; white-space: nowrap; }
    ${skSel('.sk-sub')} { font-size: 13px; color: var(--muted); line-height: 1.5; }
    ${skSel('.sk-note')} { font-size: 11.5px; color: var(--muted); margin-top: 6px; }
    ${skSel('.sk-ct')} { display: flex; justify-content: space-between; align-items: baseline; font-size: 15px; font-weight: 600; }
    ${skSel('.sk-ct small')} { font-size: 12px; font-weight: 500; color: var(--muted); }
    ${skSel('.sk-flow')} { padding: 12px 16px 6px; }
    ${skSel('.sk-flow svg')} { width: 100%; height: auto; display: block; }
    ${skSel('.sk-kpis')} { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    ${skSel('.sk-extra')} { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
    ${skSel('.sk-cap')} { padding: 11px 14px; font-size: 12px; }
    ${skSel('.sk-kpi')} { padding: 11px 14px; min-width: 0; }
    ${skSel('.sk-kpi .l')} { font-size: 11px; font-weight: 600; letter-spacing: .5px; text-transform: uppercase; color: var(--muted); }
    ${skSel('.sk-kpi .v')} { font-size: 20px; font-weight: 600; letter-spacing: -.3px; margin-top: 3px; white-space: nowrap; }
    ${skSel('.sk-kpi .s')} { font-size: 11.5px; color: var(--muted); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    ${skSel('.sk-chip .v')} { font-size: 14px; white-space: normal; line-height: 1.25; }
    ${skSel('.sk-chips > :last-child:nth-child(odd)')} { grid-column: 1 / -1; }
    ${skSel('.sk-strip-card')} { padding: 12px 16px 10px; }
    ${skSel('.sk-strip')} { display: flex; gap: 2.5px; height: 26px; margin-top: 10px; }
    ${skSel('.sk-strip i')} { flex: 1; border-radius: 7px; }
    ${skSel('.sk-strip i.now')} { outline: 2px solid var(--text); outline-offset: 1px; }
    ${skSel('.sk-ax')} { display: flex; justify-content: space-between; font-size: 10.5px; color: var(--muted); margin-top: 5px; }
    ${skSel('.sk-leg')} { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: 11.5px; color: var(--muted); margin-top: 8px; }
    ${skSel('.sk-leg b')} { display: inline-block; width: 9px; height: 9px; border-radius: 3px; margin-right: 5px; vertical-align: -1px; }
    ${skSel('.sk-dots')} { display: block; max-width: 100%; }
    @container sk (min-width: 640px) {
      ${skSel('.sk-home')} { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); grid-template-areas: "hero flow" "kpis strip" "extra strip"; }
      ${skSel('.sk-hero')} { grid-area: hero; } ${skSel('.sk-flow')} { grid-area: flow; } ${skSel('.sk-kpis')} { grid-area: kpis; } ${skSel('.sk-strip-card')} { grid-area: strip; } ${skSel('.sk-extra')} { grid-area: extra; }
    }
  `;

  // „Szkło”: półprzezroczyste, rozmyte karty na kolorowym tle, pływający szklany pasek zakładek
  const SKIN_GLASS = mkSkin('glass', `
    & { --bg:#eef2fb; --card:rgba(255,255,255,0.55); --surface:rgba(255,255,255,0.5); --line:rgba(255,255,255,0.85); --text:#0f1115; --text2:rgba(15,17,21,0.78); --muted:rgba(15,17,21,0.58); --muted2:rgba(15,17,21,0.44); --accent:#0a7aff; --green:#12a85c; --orange:#e07f00; --red:#e5484d; --input-bg:rgba(255,255,255,0.7); --seg-bg:rgba(20,30,60,0.08); --seg-active:rgba(255,255,255,0.95); --shadow:none; --pf-bg:rgba(255,255,255,0.5); --tab-on:#fff; --tab-on-fg:#0a7aff; --tab-off:rgba(15,17,21,0.66); --tab-bg:rgba(255,255,255,0.62); --tab-line:rgba(255,255,255,0.95); --sk-glass:linear-gradient(145deg,rgba(255,255,255,0.78),rgba(255,255,255,0.42)); --sk-hi:rgba(255,255,255,0.9); --sk-sh:0 10px 28px rgba(60,80,140,0.16); --sk-pv:#f59e0b; --sk-grid:#0aa5d6; --sk-sell:#7c4dff; --sk-batt:#14b866; --sk-idle:rgba(20,30,60,0.12); --sk-ring1:#3ed99a; --sk-ring2:#0f9f68; color-scheme: light;
      background: radial-gradient(70% 30% at 12% 6%,#9ec5ff 0,transparent 70%), radial-gradient(55% 26% at 95% 24%,#e0b8ff 0,transparent 70%), radial-gradient(70% 30% at 15% 62%,#a8f0d4 0,transparent 72%), radial-gradient(60% 28% at 95% 94%,#ffd1a3 0,transparent 70%), #eef2fb; }
    &D { --bg:#0a0f1f; --card:rgba(255,255,255,0.10); --surface:rgba(255,255,255,0.08); --line:rgba(255,255,255,0.20); --text:#fff; --text2:rgba(255,255,255,0.84); --muted:rgba(255,255,255,0.62); --muted2:rgba(255,255,255,0.5); --accent:#4d9bff; --green:#35e08a; --orange:#ffa94d; --red:#ff6b6b; --input-bg:rgba(255,255,255,0.12); --seg-bg:rgba(255,255,255,0.12); --seg-active:rgba(255,255,255,0.26); --pf-bg:rgba(255,255,255,0.08); --tab-on:rgba(255,255,255,0.26); --tab-on-fg:#fff; --tab-off:rgba(255,255,255,0.74); --tab-bg:rgba(255,255,255,0.14); --tab-line:rgba(255,255,255,0.28); --sk-glass:linear-gradient(145deg,rgba(255,255,255,0.20),rgba(255,255,255,0.07)); --sk-hi:rgba(255,255,255,0.34); --sk-sh:0 12px 32px rgba(0,0,0,0.32); --sk-pv:#ffd166; --sk-grid:#4fd8ff; --sk-sell:#b98aff; --sk-batt:#35e08a; --sk-idle:rgba(255,255,255,0.16); --sk-ring1:#9affd0; --sk-ring2:#2fd596; color-scheme: dark;
      background: radial-gradient(70% 30% at 12% 6%,#3556e0 0,transparent 70%), radial-gradient(55% 26% at 95% 24%,#a33bd0 0,transparent 70%), radial-gradient(70% 30% at 15% 62%,#0a9e76 0,transparent 72%), radial-gradient(60% 28% at 95% 94%,#e8590c 0,transparent 70%), #0a0f1f; }
    & .chart-card, & .soc-card, & .pf-wrapper, & .weather-tile, & .ds-item, & .btn, & .sk-card, & .sk-kpi, & .dg-card, & .why-box, & .suggest-item { background: var(--sk-glass); border: 1px solid var(--line); backdrop-filter: blur(24px) saturate(180%); -webkit-backdrop-filter: blur(24px) saturate(180%); box-shadow: inset 0 1.5px 0 var(--sk-hi), var(--sk-sh); color: var(--text); }
    & .chart-card, & .soc-card, & .pf-wrapper, & .sk-card, & .dg-card { border-radius: 28px; }
    & .btn, & .ds-item, & .sk-kpi, & .suggest-item, & .why-box { border-radius: 22px; }
    & .weather-tile { border-radius: 20px; }
    & .row { background: var(--card); }
    & .header .title { font-weight: 700; }
    & .bell, & .theme-seg { background: var(--sk-glass); border: 1px solid var(--line); backdrop-filter: blur(20px); box-shadow: inset 0 1px 0 var(--sk-hi); }
    & .tabs.bottom { border-radius: 34px; padding: 6px; background: var(--sk-glass); border: 1px solid var(--tab-line); backdrop-filter: blur(28px) saturate(190%); -webkit-backdrop-filter: blur(28px) saturate(190%); box-shadow: inset 0 1.5px 0 var(--sk-hi), 0 14px 34px rgba(0,0,0,0.26); }
    & .tabs.bottom::before { display: none; }
    & .tabs.bottom .tab { border-radius: 28px; }
    & .tabs.bottom .tab.active { background: var(--tab-on); color: var(--tab-on-fg); box-shadow: inset 0 1px 0 var(--sk-hi), 0 2px 10px rgba(0,0,0,0.14); }
    & select, & input[type="time"], & input[type="number"] { border-radius: 14px; background: var(--input-bg); border: 1px solid var(--line); }
    & .sk-strip i { border-radius: 8px; }
    & .sk-hero { background-image: radial-gradient(120% 90% at 0% 0%, rgba(255,255,255,0.22), transparent 55%), var(--sk-glass); }
  `);

  // „Matryca”: czerń lub papier, kwadratowe „piksele” zamiast gładkich linii, bursztynowy akcent, czcionka monospace
  const SKIN_MATRIX = mkSkin('matrix', `
    & { --bg:#f1f0eb; --card:#fbfbf8; --surface:#f6f5f0; --line:#d3d1c8; --text:#0c0c0c; --text2:#2a2a2a; --muted:#6b6a64; --muted2:#8d8c85; --accent:#d45a00; --green:#1c7c3c; --orange:#b86a00; --red:#c4302b; --input-bg:#fbfbf8; --seg-bg:#e6e4dc; --seg-active:#dcd9cf; --shadow:none; --pf-bg:#fbfbf8; --tab-on:#0c0c0c; --tab-on-fg:#f1f0eb; --tab-off:#55544e; --tab-bg:#fbfbf8; --tab-line:#d3d1c8; --sk-on:#0c0c0c; --sk-off:#d3d1c8; --sk-acc:#d45a00; color-scheme: light; }
    &D { --bg:#050505; --card:#0f0f0f; --surface:#141414; --line:#2a2a28; --text:#f2f2ef; --text2:#cfcfca; --muted:#8c8c86; --muted2:#6a6a66; --accent:#ffb000; --green:#7ee08a; --orange:#ffb000; --red:#ff6a5a; --input-bg:#141414; --seg-bg:#1a1a18; --seg-active:#2a2a27; --pf-bg:#0f0f0f; --tab-on:#f2f2ef; --tab-on-fg:#050505; --tab-off:#8c8c86; --tab-bg:#0a0a0a; --tab-line:#2a2a28; --sk-on:#f2f2ef; --sk-off:#2e2e2b; --sk-acc:#ffb000; color-scheme: dark; }
    & .date, & .section-title, & .sk-home, & .tabs, & .btn, & .badge, & .why-box, & .status-banner { font-family: "DejaVu Sans Mono", "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace; }
    & .chart-card, & .soc-card, & .pf-wrapper, & .sk-card, & .dg-card { background: var(--card); border: 1px solid var(--line); border-radius: 22px; box-shadow: none; }
    & .weather-tile, & .ds-item, & .sk-kpi, & .suggest-item, & .why-box { background: var(--card); border: 1px solid var(--line); border-radius: 16px; box-shadow: none; }
    & .sk-kpis { gap: 0; border: 1px solid var(--line); border-radius: 18px; background: var(--card); overflow: hidden; }
    & .sk-kpi { border: none; border-radius: 0; background: transparent; }
    & .sk-kpi + .sk-kpi { border-left: 1px dotted var(--line); }
    & .sk-chips .sk-kpi { border-top: 1px dotted var(--line); } & .sk-chips .sk-kpi:nth-child(-n+2) { border-top: none; } & .sk-chips .sk-kpi:nth-child(odd) { border-left: none; }
    & .btn { background: transparent; border: 1px solid var(--line); border-radius: 14px; box-shadow: none; text-transform: uppercase; letter-spacing: .5px; font-size: 12px; }
    & .btn.active { border-color: var(--accent); color: var(--accent); }
    & .row { background: var(--card); border-bottom: 1px dotted var(--line); }
    & .header .title { font-weight: 700; }
    & .date, & .section-title, & .sk-lbl, & .sk-kpi .l, & .sk-note, & .sk-ax, & .sk-leg { text-transform: uppercase; letter-spacing: .8px; }
    & .section-title { font-size: 11.5px; }
    & .bell, & .theme-seg { background: transparent; border: 1px solid var(--line); }
    & .theme-seg button.active, & .tab.active { background: var(--seg-active); color: var(--accent); box-shadow: none; }
    & .tabs { border-radius: 14px; background: var(--seg-bg); }
    & .tabs.bottom { background: var(--tab-bg); border: 1px solid var(--tab-line); border-radius: 18px; box-shadow: none; }
    & .tabs.bottom::before { display: none; }
    & .tabs.bottom .tab { border-radius: 12px; text-transform: uppercase; letter-spacing: .5px; }
    & .tabs.bottom .tab.active { background: transparent; color: var(--text); }
    & .tabs.bottom .tab.active::before { content: ''; position: absolute; top: 1px; left: 50%; width: 5px; height: 5px; margin-left: -2px; border-radius: 1px; background: var(--accent); }
    & select, & input[type="time"], & input[type="number"] { border-radius: 10px; background: var(--input-bg); border: 1px solid var(--line); font-family: inherit; }
    & .toggle-switch, & .sw { accent-color: var(--accent); }
    & .sk-strip i { border-radius: 2px; }
    & .sk-big { font-size: 22px; }
    & .sk-ct { text-transform: uppercase; letter-spacing: .8px; font-size: 12px; }
  `);

  // „Przestrzeń”: duże szklane okno na tle zmierzchu; na szerokim ekranie pionowy pasek zakładek z boku (rozwija się po najechaniu)
  const SKIN_SPACE = mkSkin('space', `
    & { --bg:#cfd9f1; --card:rgba(255,255,255,0.52); --surface:rgba(255,255,255,0.45); --line:rgba(255,255,255,0.78); --text:#12141c; --text2:rgba(18,20,28,0.8); --muted:rgba(18,20,28,0.6); --muted2:rgba(18,20,28,0.46); --accent:#2b6bff; --green:#12a85c; --orange:#d97800; --red:#d9383e; --input-bg:rgba(255,255,255,0.7); --seg-bg:rgba(30,40,80,0.10); --seg-active:rgba(255,255,255,0.9); --shadow:none; --pf-bg:rgba(255,255,255,0.45); --tab-on:rgba(30,40,80,0.16); --tab-on-fg:#12141c; --tab-off:rgba(18,20,28,0.68); --tab-bg:rgba(255,255,255,0.55); --tab-line:rgba(255,255,255,0.85); --sk-win:linear-gradient(160deg,rgba(255,255,255,0.62),rgba(255,255,255,0.38)); --sk-glass:rgba(255,255,255,0.55); --sk-hi:rgba(255,255,255,0.9); --sk-pv:#f59e0b; --sk-grid:#0aa5d6; --sk-sell:#7c4dff; --sk-batt:#14b866; --sk-idle:rgba(30,40,80,0.14); --sk-ring1:#3ed99a; --sk-ring2:#0f9f68; color-scheme: light;
      background: radial-gradient(circle at 80% 78%, rgba(255,236,190,0.7) 0, transparent 24%), linear-gradient(180deg,#9fc3ee 0%,#d8c9ee 46%,#ffd2b0 78%,#ffe6c8 100%); padding: 14px; }
    &D { --bg:#16213f; --card:rgba(255,255,255,0.09); --surface:rgba(255,255,255,0.07); --line:rgba(255,255,255,0.16); --text:#fff; --text2:rgba(255,255,255,0.86); --muted:rgba(255,255,255,0.64); --muted2:rgba(255,255,255,0.5); --accent:#7eb0ff; --green:#43e89a; --orange:#ffb454; --red:#ff7a7a; --input-bg:rgba(255,255,255,0.12); --seg-bg:rgba(255,255,255,0.12); --seg-active:rgba(255,255,255,0.28); --pf-bg:rgba(255,255,255,0.07); --tab-on:rgba(255,255,255,0.22); --tab-on-fg:#fff; --tab-off:rgba(255,255,255,0.76); --tab-bg:rgba(60,66,84,0.6); --tab-line:rgba(255,255,255,0.2); --sk-win:linear-gradient(160deg,rgba(80,86,104,0.55),rgba(38,42,56,0.62)); --sk-glass:rgba(255,255,255,0.09); --sk-hi:rgba(255,255,255,0.18); --sk-pv:#ffd166; --sk-grid:#4fd8ff; --sk-sell:#b98aff; --sk-batt:#43e89a; --sk-idle:rgba(255,255,255,0.16); --sk-ring1:#9affd0; --sk-ring2:#2fd596; color-scheme: dark;
      background: radial-gradient(circle at 80% 78%, rgba(255,217,160,0.38) 0, transparent 24%), linear-gradient(180deg,#16213f 0%,#4a4079 42%,#c76b6a 76%,#f2ad6a 100%); }
    & .app { background: var(--sk-win); border: 1px solid var(--line); border-radius: 40px; padding: 22px 24px; box-shadow: inset 0 1.5px 0 var(--sk-hi), 0 30px 70px rgba(0,0,0,0.35); backdrop-filter: blur(40px) saturate(150%); -webkit-backdrop-filter: blur(40px) saturate(150%); }
    & .chart-card, & .soc-card, & .pf-wrapper, & .sk-card, & .dg-card { background: var(--sk-glass); border: 1px solid var(--line); border-radius: 30px; box-shadow: inset 0 1px 0 var(--sk-hi), 0 8px 22px rgba(0,0,0,0.16); }
    & .weather-tile, & .ds-item, & .sk-kpi, & .suggest-item, & .why-box, & .btn { background: var(--sk-glass); border: 1px solid var(--line); border-radius: 24px; box-shadow: inset 0 1px 0 var(--sk-hi); }
    & .row { background: var(--card); }
    & .header .title { font-weight: 700; }
    & .bell, & .theme-seg { background: var(--sk-glass); border: 1px solid var(--line); }
    & .tabs.bottom { border-radius: 34px; padding: 6px; background: var(--tab-bg); border: 1px solid var(--tab-line); backdrop-filter: blur(30px); -webkit-backdrop-filter: blur(30px); box-shadow: inset 0 1px 0 var(--sk-hi), 0 14px 34px rgba(0,0,0,0.3); }
    & .tabs.bottom::before { display: none; }
    & .tabs.bottom .tab { border-radius: 26px; }
    & .tabs.bottom .tab.active { background: var(--tab-on); color: var(--tab-on-fg); box-shadow: inset 0 1px 0 var(--sk-hi); }
    & select, & input[type="time"], & input[type="number"] { border-radius: 14px; background: var(--input-bg); border: 1px solid var(--line); }
    & .sk-strip i { border-radius: 8px; }
    @media (max-width: 719px) { & .app { padding: 14px; border-radius: 30px; } }
    @media (max-width: 380px) { & .header .title .logo { height: 30px; } & .hdr-r { gap: 6px; } & .bell { width: 36px; } & .theme-seg button { width: 31px; } }
    @media (max-width: 335px) { & .header .title .logo { height: 26px; } & .hdr-r { gap: 5px; } & .bell { width: 34px; } & .theme-seg button { width: 29px; } }
    @media (min-width: 720px) {
      & .app { display: grid; grid-template-columns: 68px minmax(0, 1fr); column-gap: 18px; align-items: start; }
      & .app > * { grid-column: 2; min-width: 0; }
      & .app > .tabs.bottom { grid-column: 1; grid-row: 1 / span 40; align-self: start; position: sticky; top: 16px; bottom: auto; flex-direction: column; width: 68px; max-width: none; margin: 0; padding: 8px; gap: 6px; overflow: hidden; z-index: 40; transition: width .25s ease; }
      & .app > .tabs.bottom .tab { flex: 0 0 auto; flex-direction: row; justify-content: flex-start; gap: 12px; padding: 11px 12px; width: 100%; }
      & .app > .tabs.bottom .tab .tl { display: none; }
      & .app > .tabs.bottom:hover, & .app > .tabs.bottom:focus-within { width: 192px; }
      & .app > .tabs.bottom:hover .tab .tl, & .app > .tabs.bottom:focus-within .tab .tl { display: inline; }
    }
  `);

  // „Komfort”: duży nagłówek, bardzo zaokrąglone płaskie karty, niebieski akcent, płaski dolny pasek z pigułką pod ikoną
  const SKIN_COMFORT = mkSkin('comfort', `
    & { --bg:#f2f3f6; --card:#fff; --surface:#fff; --line:rgba(20,22,26,0.09); --text:#14161a; --text2:#3a3f48; --muted:#6a707c; --muted2:#8b919c; --accent:#2f6df6; --green:#1fa463; --orange:#f08c00; --red:#e03e45; --input-bg:#e9ebf0; --seg-bg:#e9ebf0; --seg-active:#fff; --shadow:none; --pf-bg:#fff; --tab-on:rgba(47,109,246,0.13); --tab-on-fg:#2f6df6; --tab-off:#6a707c; --tab-bg:#fff; --tab-line:transparent; --sk-pv:#f08c00; --sk-grid:#1496d6; --sk-sell:#7b5cf0; --sk-batt:#1fa463; --sk-idle:#dfe2e8; color-scheme: light; font-family: "Samsung Sans", "Roboto Flex", Roboto, "Segoe UI", system-ui, sans-serif; }
    &D { --bg:#000; --card:#1c1d21; --surface:#1c1d21; --line:rgba(255,255,255,0.09); --text:#f3f4f6; --text2:#d4d7de; --muted:#9a9fab; --muted2:#7d828d; --accent:#5b9bff; --green:#3ddc8c; --orange:#ffb04a; --red:#ff6f74; --input-bg:#2a2c32; --seg-bg:#2a2c32; --seg-active:#3a3d45; --pf-bg:#1c1d21; --tab-on:rgba(91,155,255,0.2); --tab-on-fg:#7eb0ff; --tab-off:#9a9fab; --tab-bg:#121316; --sk-pv:#ffb04a; --sk-grid:#4cc3ff; --sk-sell:#a58bff; --sk-batt:#3ddc8c; --sk-idle:#33353c; color-scheme: dark; }
    & .header { min-height: 92px; align-items: flex-end; padding: 22px 8px 6px; }
    & .header .title .logo { height: 44px; }
    @media (max-width: 480px) { & .header { padding: 16px 4px 6px; min-height: 0; } & .header .title .logo { height: 34px; } }
    @media (max-width: 400px) { & .header .title .logo { height: 30px; } }
    @media (max-width: 335px) { & .header .title .logo { height: 26px; } }
    & .date { font-size: 13.5px; }
    & .chart-card, & .soc-card, & .pf-wrapper, & .sk-card, & .dg-card { background: var(--card); border: none; border-radius: 28px; box-shadow: none; }
    & .weather-tile, & .ds-item, & .sk-kpi, & .suggest-item, & .why-box { background: var(--card); border: none; border-radius: 22px; box-shadow: none; }
    & .btn, & .ds-item { background: var(--seg-bg); border: none; border-radius: 22px; box-shadow: none; }
    & .btn.active { background: var(--tab-on); color: var(--tab-on-fg); }
    & .row { background: var(--card); border-bottom: 1px solid var(--line); }
    & .section-title { text-transform: none; font-size: 13.5px; font-weight: 600; letter-spacing: 0; color: var(--accent); padding-left: 10px; }
    & .bell, & .theme-seg { background: var(--card); }
    & .tabs { border-radius: 24px; }
    & .tabs.bottom { border: none; border-radius: 26px 26px 0 0; box-shadow: 0 -1px 0 var(--line); padding: 9px 8px 8px; margin: 16px -14px -14px; width: auto; max-width: none; background: var(--tab-bg); }
    & .tabs.bottom::before { display: none; }
    & .tabs.bottom .tab { border-radius: 18px; gap: 4px; }
    & .tabs.bottom .tab.active { background: transparent; color: var(--text); }
    & .tabs.bottom .tab .ti { padding: 4px 22px; border-radius: 17px; transition: background .2s; }
    & .tabs.bottom .tab.active .ti { background: var(--tab-on); color: var(--tab-on-fg); }
    & .tabs.bottom .tab .tls { font-size: 11px; font-weight: 500; }
    & .tabs.bottom .tab.active .tls { font-weight: 700; }
    & select, & input[type="time"], & input[type="number"] { border-radius: 14px; background: var(--input-bg); border: none; }
    & .toggle-switch, & .sw { accent-color: var(--accent); }
    & .sk-flow { padding-bottom: 4px; }
    & .sk-big { font-weight: 600; }
  `);


  // „Bohater”: ciemnozielona karta baterii z miętowym pierścieniem, białe zaokrąglone karty, zielony akcent, pigułkowy dolny pasek
  const SKIN_HERO = mkSkin('hero', `
    & { --bg:#f0f1f4; --card:#fff; --surface:#fff; --line:rgba(23,28,38,0.08); --text:#171c26; --text2:#2f3644; --muted:#5a6373; --muted2:#808999; --accent:#0f7b57; --green:#0f7b57; --orange:#e8890c; --red:#d64545; --input-bg:#e9ebf0; --seg-bg:#e3e6ec; --seg-active:#fff; --shadow:none; --pf-bg:#fff; --tab-on:#0f7b57; --tab-on-fg:#fff; --tab-off:#5a6373; --tab-bg:#fff; --tab-line:transparent; --sk-pv:#e8890c; --sk-grid:#2b7be4; --sk-sell:#e8890c; --sk-batt:#17a673; --sk-idle:#e3e6ec; color-scheme: light; font-family: Manrope, "Segoe UI", Roboto, system-ui, sans-serif; }
    &D { --bg:#0d1411; --card:#18211d; --surface:#18211d; --line:rgba(255,255,255,0.08); --text:#e6eee9; --text2:#c9d6cf; --muted:#9db0a6; --muted2:#7c8f85; --accent:#2fb583; --green:#2fb583; --orange:#f0a030; --red:#ff7a6e; --input-bg:#26332d; --seg-bg:#26332d; --seg-active:#33433b; --pf-bg:#18211d; --tab-on:#2fb583; --tab-on-fg:#08241a; --tab-off:#9db0a6; --tab-bg:#18211d; --sk-pv:#f0a030; --sk-grid:#4d94f0; --sk-sell:#f0a030; --sk-batt:#2fb583; --sk-idle:#26332d; color-scheme: dark; }
    & .header { text-align: left; padding: 8px 6px 4px; }
    & .header .title { font-weight: 800; }
    & .chart-card, & .soc-card, & .pf-wrapper, & .sk-card, & .dg-card { background: var(--card); border: none; border-radius: 24px; box-shadow: none; }
    & .weather-tile, & .ds-item, & .sk-kpi, & .suggest-item, & .why-box { background: var(--card); border: none; border-radius: 20px; box-shadow: none; }
    & .btn { background: var(--seg-bg); border: none; border-radius: 16px; box-shadow: none; }
    & .btn.active { background: var(--tab-on); color: var(--tab-on-fg); }
    & .row { background: var(--card); border-bottom: 1px solid var(--line); }
    & .section-title { text-transform: none; font-size: 13.5px; font-weight: 700; letter-spacing: 0; color: var(--accent); padding-left: 8px; }
    & .bell, & .theme-seg { background: var(--card); }
    & .tabs { border-radius: 999px; }
    & .tabs.bottom { border: none; border-radius: 999px; padding: 6px; background: var(--tab-bg); box-shadow: 0 6px 22px rgba(23,28,38,0.12); }
    & .tabs.bottom::before { display: none; }
    & .tabs.bottom .tab { border-radius: 999px; }
    & .tabs.bottom .tab.active { background: var(--tab-on); color: var(--tab-on-fg); box-shadow: none; }
    & select, & input[type="time"], & input[type="number"] { border-radius: 14px; background: var(--input-bg); border: none; }
    & .toggle-switch, & .sw { accent-color: var(--accent); }
    & .sk-hero { background: #0b3b2c; border-radius: 32px; padding: 20px 22px; --text:#fff; --muted:#b9d9cb; --sk-idle:#1d5a46; --sk-batt:#5fe0a8; --sk-ring1:#5fe0a8; --sk-ring2:#5fe0a8; --card:#0b3b2c; color: #fff; }
    &D .sk-hero { background: #12382b; --card:#12382b; --sk-idle:#1f5a46; }
    & .sk-hero .sk-sub, & .sk-hero .sk-note, & .sk-hero .sk-lbl { color: #b9d9cb; }
    & .sk-big { font-weight: 800; }
    & .sk-strip i { border-radius: 8px; }
  `);

  const STYLES = `
    :host { --bg:#000; --card:#1c1c1e; --surface:rgba(255,255,255,0.06); --line:rgba(255,255,255,0.10); --text:#fff; --text2:#e5e5ea; --muted:#8e8e93; --muted2:#6e6e73; --accent:#0a84ff; --green:#30d158; --orange:#ff9f0a; --red:#ff453a; --input-bg:#2c2c2e; --seg-bg:rgba(118,118,128,0.24); --seg-active:#636366; --shadow:none; --pf-bg:#1c1c1e; color-scheme: dark; }
    :host([data-theme="light"]) { --bg:#e4e4e9; --card:#f0f0f4; --surface:rgba(60,60,67,0.07); --line:rgba(60,60,67,0.12); --text:#1c1c1e; --text2:#3a3a3c; --muted:#6c6c70; --muted2:#8e8e93; --accent:#0a84ff; --green:#34c759; --orange:#ff9500; --red:#ff3b30; --input-bg:#e4e4e9; --seg-bg:rgba(118,118,128,0.14); --seg-active:#f7f7fa; --shadow:0 1px 2px rgba(0,0,0,0.05),0 6px 18px rgba(0,0,0,0.07); --pf-bg:#f0f0f4; color-scheme: light; }
    :host { display: block; background: var(--bg); color: var(--text); border-radius: 22px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; overflow-x: hidden; overflow-x: clip; }
    * { box-sizing: border-box; }
    .app { padding: 14px; width: 100%; max-width: 1200px; margin: 0 auto; }
    .header { text-align: center; margin-bottom: 16px; }
    .header .title { font-size: clamp(22px, 5vw, 28px); font-weight: 800; letter-spacing: -0.5px; }
    .date { font-size: 13px; color: var(--muted); margin-top: 6px; }
    .tabs { display: flex; gap: 4px; padding: 4px; background: var(--surface); border-radius: 12px; margin-bottom: 12px; overflow-x: auto; scrollbar-width: none; }
    .tabs::-webkit-scrollbar { display: none; }
    .tab { flex: 1 1 0; padding: 10px 12px; border: none; background: transparent; color: var(--muted); font-weight: 600; border-radius: 8px; cursor: pointer; transition: 0.2s; white-space: nowrap; font-size: 14px; min-width: 0; text-overflow: ellipsis; overflow: hidden; }
    .tab.active { background: var(--seg-active); color: var(--text); box-shadow: 0 2px 8px rgba(0,0,0,0.12); }
    @media (max-width: 640px) { .tab { flex: 0 0 auto; padding: 10px 14px; overflow: visible; text-overflow: clip; } }
    .section { margin-top: 16px; }
    /* Układ panelu: ukryty kafelek, odstępy po przestawieniu, komunikat gdy ukryto wszystko */
    [data-tile-off] { display: none !important; }
    /* „Co EMS planuje na najbliższe 24 h” (tabela planu i mała karta) */
    .ps { background: var(--surface); border-radius: 14px; padding: 10px 12px; margin: 0 0 12px; font-size: 13px; color: var(--text2); }
    .ps-h { font-weight: 700; color: var(--text); margin-bottom: 4px; font-size: 13.5px; cursor: pointer; list-style: none; display: flex; justify-content: space-between; align-items: center; gap: 8px; }
    .ps-h::-webkit-details-marker { display: none; }
    .ps-h::after { content: '▾'; color: var(--muted); }
    .ps:not([open]) > .ps-h { margin-bottom: 0; }
    .ps:not([open]) > .ps-h::after { content: '▸'; }
    .ps-l { display: flex; gap: 8px; align-items: baseline; padding: 2px 0; line-height: 1.4; }
    .ps-l i { font-style: normal; flex: none; width: 22px; text-align: center; }
    .ps-l b { color: var(--text); font-weight: 600; }
    .ps-n { font-size: 11px; color: var(--muted); margin-top: 4px; line-height: 1.4; }
    /* okno „Wygląd” (przycisk 🎨) — korzysta z ramki okna powiadomień (.inb-ov / .inb) */
    .look-skins { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 8px; }
    .look-sk { text-align: left; border: 2px solid var(--line); background: var(--surface); color: var(--text); border-radius: 14px; padding: 10px 12px; cursor: pointer; font-family: inherit; display: flex; flex-direction: column; gap: 3px; }
    .look-sk b { font-size: 14px; } .look-sk span { font-size: 11.5px; color: var(--muted); }
    .look-sk.on { border-color: var(--accent); background: var(--seg-active); }
    .look-row { display: flex; gap: 8px; }
    .look-row button { flex: 1; padding: 10px; border-radius: 12px; border: 2px solid var(--line); background: var(--surface); color: var(--text); font-size: 14px; cursor: pointer; font-family: inherit; }
    .look-row button.on { border-color: var(--accent); background: var(--seg-active); font-weight: 700; }
    .look-note { font-size: 12px; color: var(--muted); margin: 4px 0 8px; }
    .inb-btns button[disabled] { opacity: .4; cursor: default; }
    /* tryb edycji układu: pasek u góry, sterowanie na kafelkach, zawartość kafelków przycięta i nieklikalna (żeby nic nie przełączyć przez pomyłkę) */
    .edit-bar { position: sticky; top: 0; z-index: 30; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 6px 0; padding: 10px 12px; border-radius: 14px; background: var(--card); border: 2px solid var(--accent); color: var(--text); font-size: 12.5px; box-shadow: 0 4px 16px rgba(0,0,0,0.25); }
    .edit-bar[hidden] { display: none; }
    .edit-bar .eb-t { flex: 1 1 220px; color: var(--text2); } .edit-bar .eb-t b { color: var(--text); }
    .edit-bar button { border: none; border-radius: 10px; padding: 8px 12px; font-weight: 600; font-size: 13px; cursor: pointer; background: var(--seg-bg); color: var(--text); font-family: inherit; }
    .edit-bar button.ok { background: var(--accent); color: #fff; } .edit-bar button[disabled] { opacity: .4; cursor: default; }
    .tile-ctl { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; padding: 6px 8px; margin-bottom: 6px; border-radius: 12px; background: var(--seg-bg); border: 1px dashed var(--accent); color: var(--text); font-size: 12.5px; }
    .tc-h { cursor: grab; touch-action: none; user-select: none; -webkit-user-select: none; font-size: 20px; line-height: 1; padding: 4px 8px; color: var(--accent); }
    .tc-n { flex: 1 1 150px; min-width: 0; font-weight: 600; overflow-wrap: anywhere; }
    .tc-b { display: flex; align-items: center; gap: 6px; margin-left: auto; }
    .tile-ctl button { border: none; background: var(--surface); color: var(--text); border-radius: 8px; min-width: 34px; height: 32px; cursor: pointer; font-size: 14px; font-family: inherit; }
    .tile-ctl button[disabled] { opacity: .35; cursor: default; }
    .tile-ctl .tc-eye { padding: 0 10px; font-size: 12px; font-weight: 600; }
    .tile-ctl select { height: 32px; max-width: 118px; border: none; border-radius: 8px; background: var(--surface); color: var(--text); font-size: 12px; font-weight: 600; font-family: inherit; padding: 0 6px; cursor: pointer; }
    .tc-n small { font-weight: 400; color: var(--muted); }
    .edit-bar .eb-n { margin-top: 4px; color: var(--accent); font-weight: 600; } .edit-bar .eb-n:empty { display: none; }
    .app[data-edit] [data-tile] { position: relative; max-height: 150px; overflow: hidden; outline: 2px dashed var(--accent); outline-offset: 3px; border-radius: 14px; margin-bottom: 8px; }
    .app[data-edit] [data-tile] > :not(.tile-ctl) { pointer-events: none; user-select: none; }
    .app[data-edit] [data-tile-off] { display: block !important; opacity: .6; max-height: none; }
    .app[data-edit] [data-tile-off] > :not(.tile-ctl) { display: none !important; }
    .app[data-edit] [data-tile-off] .tc-n { text-decoration: line-through; }
    .app[data-edit] [data-tile-off] .tc-eye { background: var(--accent); color: #fff; }
    .app[data-edit] [data-tile].tile-drag { opacity: .85; outline-style: solid; box-shadow: 0 8px 28px rgba(0,0,0,0.35); z-index: 5; }
    .section[data-tile^="ems-"].collapsed > .tile-ctl { display: flex !important; }
    [data-tab-content][data-custom] [data-tile]:not([data-first]) { margin-top: 16px !important; }
    [data-tab-content][data-custom] [data-tile][data-first] { margin-top: 6px !important; }
    [data-tab-content="log"][data-custom] [data-tile][data-first] { margin-top: 16px !important; }
    .app:not(.simple) [data-tab-content][data-empty]::after { content: 'Ta zakładka nie ma teraz kafelków. Przenieś tu kafelki z innych zakładek: ✎ Edytuj układ → „⇄ Przenieś…” (Ustawienia → Wygląd → Układ panelu).'; display: block; padding: 28px 12px; text-align: center; color: var(--muted); font-size: 13px; }
    .app:not(.simple):not([data-edit]) [data-tab-content][data-all-hidden]::after { content: 'Wszystkie kafelki tej zakładki są ukryte. Przywrócisz je w: Ustawienia → Wygląd → Układ panelu.'; display: block; padding: 28px 12px; text-align: center; color: var(--muted); font-size: 13px; }
    .section-title { font-size: 12px; font-weight: 600; text-transform: uppercase; color: var(--muted); margin-bottom: 8px; padding-left: 6px; letter-spacing: 1px; }
    
    /* Poprawione style pogody, żeby ładnie się dopasowywały */
    .price-bar { display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin:0 0 10px; }
    .floor-alert { margin:0 0 10px; padding:9px 12px; border-radius:12px; background:rgba(255,159,10,.14); color:var(--orange); font-size:13px; line-height:1.4; }
    .floor-alert.bad { background:rgba(255,69,58,.14); color:var(--red); }
    .status-banner { margin:0 0 10px; display:flex; flex-direction:column; gap:6px; }
    .sb-item { padding:9px 12px; border-radius:12px; font-size:13px; line-height:1.4; background:rgba(10,132,255,.12); color:var(--accent); word-break:break-word; }
    .sb-item.warn { background:rgba(255,159,10,.14); color:var(--orange); }
    .sb-item.bad { background:rgba(255,69,58,.14); color:var(--red); }
    .sb-item b { font-weight:700; }
    .price-pill { background: var(--card); border-radius: 20px; padding: 6px 12px; font-size: 13px; box-shadow: var(--shadow, none); white-space:nowrap; }
    .price-pill b { font-size: 15px; }
    .price-pill.buy b { color: #ff6b6b; } .price-pill.sell b { color: #30d158; } .price-pill.sell.neg b { color:#ff453a; }
    .weather-global { margin-top: 6px; margin-bottom: 12px; width: 100%; overflow: hidden; }
    .weather-scroll { display: flex; gap: 8px; overflow-x: auto; padding: 4px 6px 8px 6px; scrollbar-width: none; width: 100%; box-sizing: border-box; }
    .weather-scroll::-webkit-scrollbar { display: none; }
    .weather-tile { flex: 1 1 0; min-width: 76px; display: flex; flex-direction: column; align-items: center; justify-content: center; background: var(--surface); border-radius: 14px; padding: 7px 4px; border: 1px solid var(--line); text-align: center; }
    .weather-tile .pv-rng { font-size: 9.5px; color: var(--muted); margin-top: -1px; }
    .weather-tile .day { font-size: 10px; font-weight: 700; text-transform: uppercase; color: var(--muted); margin-bottom: 1px; letter-spacing: 0.5px; }
    .weather-tile .wt-row { display: flex; align-items: center; justify-content: center; gap: 3px; }
    .weather-tile .wt-row .icon { margin: 0; font-size: 20px; }
    .weather-tile .wx { width: 30px; height: 30px; margin: 0; }
    .weather-tile .icon { font-size: 26px; margin-bottom: 6px; line-height: 1; }
    /* animowane ikony pogody (SVG, bez zewnętrznych bibliotek) */
    .wx { width: 42px; height: 42px; display: block; margin: 0 auto; overflow: visible; --wx-c1: #cbd5e1; --wx-c2: #94a3b8; --wx-sun: #fbbf24; --wx-sun2: #fde68a; --wx-drop: #60a5fa; }
    :host([data-theme="light"]) .wx { --wx-c1: #b6c2d1; --wx-c2: #7c8da3; --wx-sun: #f59e0b; --wx-sun2: #fcd34d; --wx-drop: #3b82f6; }
    .wx .c1 { fill: var(--wx-c1); } .wx .c2 { fill: var(--wx-c2); }
    .wx .sun { fill: var(--wx-sun); } .wx .sun2 { fill: var(--wx-sun2); }
    .wx .ray { stroke: var(--wx-sun); stroke-width: 2.4; stroke-linecap: round; fill: none; }
    .wx .drop { stroke: var(--wx-drop); stroke-width: 2.4; stroke-linecap: round; fill: none; }
    .wx .flake { fill: #e2e8f0; }
    :host([data-theme="light"]) .wx .flake { fill: #7dd3fc; }
    .wx .bolt { fill: #facc15; }
    .wx .moon { fill: #fde68a; } .wx .star { fill: #fde68a; }
    .wx .fogln { stroke: var(--wx-c2); stroke-width: 3; stroke-linecap: round; fill: none; }
    .wx .wind { stroke: var(--wx-c2); stroke-width: 2.6; stroke-linecap: round; fill: none; stroke-dasharray: 16 8; }
    .wx .a-spin { transform-origin: 24px 24px; animation: wx-spin 18s linear infinite; }
    .wx .a-spin-s { transform-origin: 17px 17px; animation: wx-spin 18s linear infinite; }
    .wx .a-pulse { transform-origin: 24px 24px; animation: wx-pulse 4s ease-in-out infinite; }
    .wx .a-float { animation: wx-float 5s ease-in-out infinite; }
    .wx .a-drift { animation: wx-drift 7s ease-in-out infinite; }
    .wx .a-drift2 { animation: wx-drift 9s ease-in-out infinite reverse; }
    .wx .a-drop { animation: wx-drop 1.3s linear infinite; }
    .wx .a-drop.fast { animation-duration: .85s; }
    .wx .a-snow { animation: wx-snow 3.2s linear infinite; }
    .wx .a-flash { animation: wx-flash 3.6s linear infinite; }
    .wx .a-twinkle { animation: wx-twinkle 2.8s ease-in-out infinite; }
    .wx .a-wind { animation: wx-dash 1.6s linear infinite; }
    @keyframes wx-spin { to { transform: rotate(360deg); } }
    @keyframes wx-pulse { 0%,100% { transform: scale(1); } 50% { transform: scale(1.07); } }
    @keyframes wx-float { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-2px); } }
    @keyframes wx-drift { 0%,100% { transform: translateX(-2px); } 50% { transform: translateX(2px); } }
    @keyframes wx-drop { 0% { transform: translateY(-3px); opacity: 0; } 25% { opacity: 1; } 100% { transform: translateY(9px); opacity: 0; } }
    @keyframes wx-snow { 0% { transform: translate(0,-3px); opacity: 0; } 20% { opacity: 1; } 50% { transform: translate(2px,3px); } 100% { transform: translate(-1px,10px); opacity: 0; } }
    @keyframes wx-flash { 0%,62%,100% { opacity: 0; } 66%,72% { opacity: 1; } 69% { opacity: .25; } }
    @keyframes wx-twinkle { 0%,100% { opacity: .25; } 50% { opacity: 1; } }
    @keyframes wx-dash { to { stroke-dashoffset: -48; } }
    @media (prefers-reduced-motion: reduce) { .wx * { animation: none !important; } }
    .weather-tile .temp-max { font-size: 16px; font-weight: 800; }
    .weather-tile .temp-min { font-size: 10px; color: var(--muted); margin-top: 0; font-weight: 600; }
    .weather-tile .pv { white-space: nowrap; font-size: 11px; color: #fbbf24; font-weight: 800; margin-top: 3px; display: flex; align-items: center; gap: 3px; }

    .chart-card { background: var(--surface); border-radius: 20px; padding: 16px; min-width: 0; overflow: hidden; border: 1px solid var(--surface); backdrop-filter: blur(10px); }
    .chart-card.full { grid-column: 1 / -1; }
    .chart-head { font-size: 14px; font-weight: 700; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: baseline; gap: 8px; flex-wrap: wrap; }
    .chart-head .sub { font-size: 12px; font-weight: 500; color: var(--muted); }
    .chart-card canvas { width: 100%; display: block; height: 260px; }
    #chartLoadCons { height: 300px; }
    #chartForecast7d { height: 260px; }
    #chartHourlyFc, #chartHourlyToday { height: 200px; }
    :host { --hfc-today:#6ee7b7; --hfc-today-t:#a7f3d0; --hfc-up:#fbbf24; --hfc-down:#6ee7b7; }
    :host([data-theme="light"]) { --hfc-today:#059669; --hfc-today-t:#047857; --hfc-up:#b45309; --hfc-down:#047857; }
    .hfc-wrap { margin-top: 6px; padding-right: 12px; }
    .hfc-cap { font-size: 11px; color: var(--muted); margin: 0 0 2px; }
    .hfc-tbl { display: grid; font-variant-numeric: tabular-nums; }
    .hfc-tbl + .hfc-tbl { margin-top: 12px; }
    .hfc-tbl > div { padding: 5px 0; text-align: center; white-space: nowrap; border-top: 1px solid var(--line); min-width: 0; }
    .hfc-tbl > div.l { text-align: left; color: var(--text2); }
    .hfc-tbl > div.h { border-top: 0; color: var(--muted); }
    .hfc-tbl > div.h.now { color: var(--text); font-weight: 700; }
    .hfc-tbl .pk, .hfc-tbl .up { color: var(--hfc-up); }
    .hfc-tbl .td { color: var(--hfc-today-t); }
    .hfc-tbl .dn { color: var(--hfc-down); }
    #chartPvProd24h { height: 280px; }
    .chart-box { position: relative; width: 100%; height: 420px; min-width: 0; overflow: hidden; }
    .chart-box canvas#historyChart { position: absolute; inset: 0; width: 100% !important; height: 100% !important; }
    .chart-head .time-selector { margin-bottom: 0; flex-wrap: wrap; }
    .chart-empty { padding: 30px 10px; color: var(--muted); font-size: 12px; text-align: center; }
    .chart-note { padding: 10px; color: #fbbf24; font-size: 12px; text-align: center; background: rgba(251,191,36,0.1); border-radius: 12px; margin-top: 10px; border: 1px solid rgba(251,191,36,0.2); }
    .chart-footer { margin-top: 8px; padding: 8px 6px 4px; display: flex; gap: 14px; flex-wrap: wrap; font-size: 11px; color: var(--muted); justify-content: center; border-top: 1px solid var(--line); }
    .chart-footer .stat { display: inline-flex; align-items: center; gap: 5px; white-space: nowrap; }
    .chart-footer .stat b { color: var(--text2); font-weight: 700; }
    .chart-footer .dot { width: 8px; height: 8px; border-radius: 2px; display: inline-block; }

    .price-header { font-size: 15px; font-weight: 700; margin-bottom: 12px; }
    .price-note { margin: 8px 0 2px; padding: 8px 10px; border: 1px solid var(--line); border-left: 3px solid var(--warn, #fbbf24); border-radius: 8px; font-size: 12px; line-height: 1.45; color: var(--text2); text-align: left; overflow-wrap: anywhere; }
    .price-note.wait { border-left-color: var(--accent, #60a5fa); }
    .price-note.est { border-left-color: var(--line); }
    .price-est { opacity: .7; font-style: italic; }
    .price-table { width: 100%; border-collapse: collapse; font-size: 13px; text-align: center; }
    .price-table th { border-bottom: 1px solid var(--line); padding: 8px 4px; color: var(--text2); font-weight: 700; }
    .price-table td { border-bottom: 1px solid var(--surface); padding: 8px 4px; }
    .price-table tr:last-child td { border-bottom: none; }
    .price-max { color: #10b981; font-weight: 700; }
    .price-min { color: #f43f5e; font-weight: 700; }
    .price-now-hour { background: var(--surface); }

    .active-badges { display: flex; flex-wrap: nowrap; gap: 6px; padding: 0 4px 2px; margin-bottom: 10px; overflow-x: auto; scrollbar-width: none; }
    .active-badges::-webkit-scrollbar { display: none; }
    .active-badges .badge { flex: 0 0 auto; white-space: nowrap; }
    .active-badges .badge:not(.on) { display: none; }
    .active-badges .badge.on:not(.soon) { order: -1; }
    .active-badges .badge.soon { background: transparent; border-style: dashed; box-shadow: none; }
    .badge-none { font-size: 12px; color: var(--muted); padding: 5px 4px; white-space: nowrap; }
    .active-badges .badge.on:not(.soon)::before { content: ''; display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: currentColor; margin-right: 6px; vertical-align: 1px; animation: bms-dot 2s ease-in-out infinite; }
    @keyframes bms-dot { 0%,100% { opacity: 1; transform: scale(1); } 50% { opacity: .35; transform: scale(.7); } }
    @media (prefers-reduced-motion: reduce) { .active-badges .badge.on:not(.soon)::before { animation: none; } }
    .badge-warn { display: none; padding: 0 4px; margin-bottom: 8px; }
    .badge-warn.on { display: block; }
    .why-box { margin: 6px 0 4px; padding: 12px 16px; border-radius: 16px; background: var(--card); border: 1px solid var(--line); }
    .why-h { display: flex; gap: 10px; align-items: flex-start; font-size: 14px; line-height: 1.45; color: var(--text); }
    .why-i { font-size: 20px; line-height: 1.2; flex: none; }
    .why-d { margin: 8px 0 0 30px; padding: 0; list-style: none; font-size: 12px; color: var(--muted); line-height: 1.5; }
    .why-d li::before { content: "• "; }
    .simple-wrap { margin-top: 6px; }
    .sm-card { background: var(--card); border: 1px solid var(--line); border-radius: 18px; padding: 16px; margin-bottom: 12px; }
    .sm-q { font-size: 15px; font-weight: 600; color: var(--text); margin-bottom: 4px; }
    .sm-h { font-size: 12px; color: var(--muted); line-height: 1.5; margin-bottom: 10px; }
    .sm-seg { display: inline-flex; padding: 3px; background: var(--seg-bg); border-radius: 999px; }
    .sm-seg button { border: none; background: transparent; color: var(--muted); padding: 8px 22px; border-radius: 999px; cursor: pointer; font-size: 14px; font-weight: 600; }
    .sm-seg button.active { background: var(--accent, #0f6e56); color: #fff; }
    .sm-tariff { font-size: 14px; color: var(--text); }
    .sm-auto { display: grid; gap: 4px; font-size: 13px; color: var(--text2); margin: 8px 0 12px; }
    .sm-auto .ok { color: var(--green); } .sm-auto .off { color: var(--muted); }
    .sm-foot { font-size: 11px; color: var(--muted); line-height: 1.5; text-align: center; margin: 4px 0 10px; }
    .tab.sub { display: none !important; }
    .set-hub { display: flex; flex-direction: column; margin: 6px 0; }
    .hub-item { display: flex; align-items: center; gap: 12px; padding: 14px 8px; background: none; border: none; border-bottom: 1px solid var(--tab-line, rgba(128,128,128,.25)); color: var(--text); text-align: left; cursor: pointer; font: inherit; }
    .hub-ic { font-size: 22px; width: 30px; text-align: center; }
    .hub-tx { flex: 1; min-width: 0; } .hub-tx b { display: block; font-size: 15px; } .hub-tx small { color: var(--muted); font-size: 12px; }
    .hub-ar { color: var(--muted); font-size: 22px; }
    .set-search { width: 100%; box-sizing: border-box; margin: 6px 0; padding: 10px 12px; border-radius: 12px; border: 1px solid var(--tab-line, rgba(128,128,128,.3)); background: var(--card-bg, rgba(128,128,128,.12)); color: var(--text); font: inherit; font-size: 14px; }
    .set-found .hub-item { padding: 10px 8px; } .set-found .hub-item small { display: block; }
    .set-flash { outline: 2px solid var(--accent, #0a84ff); outline-offset: 2px; border-radius: 6px; transition: outline-color .6s; }
    .set-back { background: none; border: none; color: var(--accent, #0a84ff); font: inherit; font-size: 14px; padding: 6px 2px; cursor: pointer; }
    .app.simple .tab[data-tab="charts"], .app.simple .tab[data-tab="log"], .app.simple .tab[data-tab="dev"] { display: none !important; }
    .app.simple .weather-global { display: none; }
    .app.simple [data-tab-content="ems"] > :not(#simpleWrap) { display: none !important; }
    .section[data-tile^="ems-"] .section-title.collapsible { cursor: pointer; user-select: none; }
    .section[data-tile^="ems-"] .section-title.collapsible::after { content: ' ▾'; opacity: .5; }
    .section[data-tile^="ems-"].collapsed > :not(.section-title) { display: none !important; }
    .section[data-tile^="ems-"].collapsed > .section-title.collapsible::after { content: ' ▸'; }
    .badge { padding: 5px 10px; border-radius: 16px; background: var(--surface); color: var(--muted); font-size: 12px; font-weight: 600; transition: all 0.3s; border: 1px solid var(--line); }
    .badge.on { background: rgba(16,185,129,0.15); color: #10b981; border-color: #10b981; box-shadow: 0 0 8px rgba(16,185,129,0.3); }
    .badge.danger.on { background: rgba(244,63,94,0.15); color: #f43f5e; border-color: #f43f5e; box-shadow: 0 0 8px rgba(244,63,94,0.4); }

    .row { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; padding: 12px 16px; min-height: 44px; background: var(--surface); border-bottom: 1px solid var(--surface); }
    .row:first-child { border-radius: 16px 16px 0 0; }
    .row:last-child { border-radius: 0 0 16px 16px; border-bottom: none; }
    .row .name { font-size: 14px; font-weight: 500; }
    .row .field-info { flex: 1 1 auto; min-width: 120px; }
    .row .eid-hint { font-size: 10px; color: var(--muted2); margin-top: 2px; font-family: monospace; overflow: hidden; text-overflow: ellipsis; }
    .row .eid-hint.ok { color: #10b981; }
    .row .eid-hint.err { color: #f43f5e; }
    .row .eid-hint.help { font-family: inherit; font-size: 11px; line-height: 1.35; color: var(--muted); white-space: normal; }
    .row .eid-hint.err { font-family: inherit; font-size: 11px; white-space: normal; }
    .row.inactive-row .field-controls { opacity: .4; }
    .row.inactive-row .name::after { content: ' · nieaktywne'; font-size: 11px; font-weight: 400; color: var(--muted2); }
    .row .field-controls { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
    select, input[type="time"], input[type="number"] { background: var(--input-bg); color: var(--text); border: 1px solid var(--line); border-radius: 10px; padding: 8px 12px; font-size: 15px; font-family: inherit; outline: none; transition: border-color 0.2s; }
    input[type="time"]:focus, input[type="number"]:focus { border-color: var(--accent); }
    input[type="time"] { width: 116px; }
    input[type="number"] { width: 80px; text-align: center; }
    input.saved-ok { border-color: #10b981 !important; }
    input.saved-err { border-color: #f43f5e !important; }

    .daily-summary { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-top: 10px; margin-bottom: 14px; }
    .ds-item { background: var(--surface); border-radius: 14px; padding: 12px 8px; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; font-size: 12px; gap: 4px; min-width: 0; border: 1px solid var(--surface); }
    .ds-item b { font-size: 16px; color: var(--text); font-weight: 800; }
    
    .soc-card { background: var(--surface); border-radius: 20px; padding: 20px 16px; margin-bottom: 14px; border: 1px solid var(--surface); }
    .soc-card .soc-value { font-size: clamp(36px, 10vw, 56px); font-weight: 800; letter-spacing: -2px; line-height: 1; }
    .soc-card .soc-sub { font-size: 13px; color: var(--muted); margin-top: 6px; word-break: break-word; }
    .socbar { height: 8px; background: var(--line); border-radius: 99px; overflow: hidden; margin-top: 16px; }
    .socbar > div { height: 100%; background: linear-gradient(90deg, #fbbf24, #22d3ee); border-radius: 99px; transition: width 0.4s; }

    .action-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-bottom: 14px; }
    .btn { display: flex; flex-direction: column; align-items: center; justify-content: center; background: var(--surface); border: 1px solid var(--line); border-radius: 16px; padding: 16px 8px; cursor: pointer; text-align: center; transition: 0.2s; font-family: inherit; color: var(--text); min-width: 0; }
    .btn:hover { background: var(--line); }
    .btn:active { transform: scale(0.95); }
    .btn:disabled { opacity: 0.4; cursor: not-allowed; filter: grayscale(0.7); }
    .btn.active { background: rgba(251,191,36,0.1); border-color: #fbbf24; color: #fbbf24; }
    .btn.blocked { border-color: #f43f5e; background: rgba(244,63,94,0.1); }
    .btn .icon { font-size: 24px; margin-bottom: 8px; }
    .btn .label { font-size: 12px; font-weight: 600; line-height: 1.3; word-break: break-word; }

    .sg-sum { padding: 12px 14px; background: var(--surface); border-radius: 14px; margin-bottom: 10px; }
    .sg-sum-h { font-size: 11px; font-weight: 700; letter-spacing: .4px; text-transform: uppercase; color: var(--muted); }
    .sg-sum-t { font-size: 13px; line-height: 1.6; color: var(--text2); margin-top: 6px; }
    .sg-sum-t b { color: var(--text); }
    .sg-sum-r { font-size: 13px; color: var(--text2); margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--line); }
    .sg-list { display: flex; flex-direction: column; gap: 8px; }
    .sg { display: flex; align-items: flex-start; gap: 12px; padding: 12px 14px; background: var(--surface); border-radius: 14px; border: 1px solid var(--line); cursor: pointer; }
    .sg-skip { cursor: default; }
    .sg input[type="checkbox"] { margin-top: 3px; accent-color: var(--accent); width: 16px; height: 16px; flex: none; }
    .sg-skip input[type="checkbox"], .sg-same input[type="checkbox"] { visibility: hidden; }
    .sg-body { flex: 1; min-width: 0; }
    .sg-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap; }
    .sg-title { font-size: 14px; font-weight: 600; color: var(--text); }
    .sg-skip .sg-title { color: var(--text2); }
    .sg-badges { display: flex; gap: 6px; }
    .sg-gain { background: rgba(16,185,129,0.18); color: #10b981; text-transform: none; font-size: 12px; }
    .sg-gain.sg-req { background: var(--surface); color: var(--muted); font-size: 10px; text-transform: uppercase; }
    .sg-gain-sum { color: #10b981; }
    .set-warn { margin: 0 0 12px; display: flex; flex-direction: column; gap: 8px; }
    .set-warn-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 10px 14px; border-radius: 14px; background: rgba(251,191,36,0.14); border: 1px solid rgba(251,191,36,0.45); font-size: 13px; color: var(--text); }
    .set-warn-row button { flex: none; padding: 7px 14px; border-radius: 10px; border: none; background: #fbbf24; color: #1c1300; font-weight: 700; cursor: pointer; }
    .sg-skipbox { margin-top: 10px; } .sg-skipbox > summary { cursor: pointer; font-size: 12px; color: var(--muted); padding: 6px 2px; }
    .sg-skipbox .sg-list { margin-top: 6px; }
    .sg-badge { font-size: 10px; padding: 3px 8px; border-radius: 6px; font-weight: 700; text-transform: uppercase; white-space: nowrap; }
    .sg-vals { display: flex; gap: 16px; flex-wrap: wrap; font-size: 13px; color: var(--text2); margin-top: 6px; }
    .sg-vals i { color: var(--muted); font-style: normal; }
    .sg-new { color: var(--accent); }
    .sg-why { font-size: 12.5px; line-height: 1.5; color: var(--text2); margin-top: 8px; }
    .sg-why span { display: block; font-size: 10.5px; font-weight: 700; letter-spacing: .4px; text-transform: uppercase; color: var(--muted); margin-bottom: 2px; }
    .sg-rules { margin-top: 14px; font-size: 12.5px; color: var(--text2); }
    .sg-rules summary { cursor: pointer; font-weight: 600; color: var(--muted); }
    .sg-rules ul { margin: 8px 0 0; padding-left: 18px; line-height: 1.55; }
    .sg-rules li { margin-bottom: 6px; }
    .suggest-item { display: flex; align-items: flex-start; gap: 10px; padding: 12px; background: var(--surface); border-radius: 12px; cursor: pointer; border: 1px solid var(--surface); margin-bottom: 6px; }
    .suggest-item.disabled { opacity: 0.5; cursor: not-allowed; }
    .suggest-item input[type="checkbox"] { margin-top: 3px; accent-color: #fbbf24; }
    .suggest-item .suggest-body { flex: 1; min-width: 0; }
    .suggest-item .suggest-label { font-weight: 600; font-size: 14px; }
    .suggest-item .suggest-values { font-size: 13px; color: var(--muted); margin-top: 4px; }
    .suggest-item .suggest-reason { font-size: 11px; color: var(--muted2); margin-top: 4px; }
    .suggest-item .suggest-conf { font-size: 10px; padding: 4px 8px; border-radius: 6px; align-self: flex-start; white-space: nowrap; font-weight: 700; text-transform: uppercase; }

    .time-selector { display: flex; gap: 6px; margin-bottom: 12px; overflow-x: auto; }
    .time-btn { padding: 6px 14px; border-radius: 8px; background: var(--surface); color: var(--muted); border: 1px solid var(--line); cursor: pointer; font-size: 12px; font-weight: 700; transition: 0.2s; }
    .time-btn:hover { background: var(--line); }
    .time-btn.active { background: #fff; color: #000; border-color: var(--accent); }

    /* ======= SANKEY POWERFLOW (Główny widok) ======= */
    .pf-wrapper { display: flex; flex-direction: column; height: 480px; background: var(--pf-bg); border-radius: 24px; overflow: hidden; position: relative; border: 1px solid var(--line); box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
    .pf-canvas-container { flex: 1; position: relative; overflow: hidden; }
    #powerflowCanvas { width: 100%; height: 100%; display: block; }
    .pf-bottom { display: none; /* Ukryte, bo usunęliśmy Uzysk/Profit */ }

    @media (max-width: 700px) {
      .app { padding: 10px; }
      .pf-wrapper { height: 400px; }
      .chart-footer { gap: 10px; font-size: 10px; }
      .price-table { font-size: 11px; }
    }
    @media (max-width: 420px) {
      .daily-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .action-grid { grid-template-columns: 1fr 1fr; }
    }



    .eta-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .eta { background: var(--card); box-shadow: var(--shadow); border-radius: 22px; padding: 14px 16px; min-width: 0; }
    .eta .e-l { font-size: 12px; color: var(--muted); font-weight: 600; text-transform: uppercase; letter-spacing: .4px; }
    .eta .e-v { font-size: clamp(22px, 5.5vw, 30px); font-weight: 700; letter-spacing: -0.5px; margin-top: 4px; line-height: 1.1; }
    .eta .e-s { font-size: 12px; color: var(--muted); margin-top: 4px; }
    @media (max-width: 420px) { .eta-grid { grid-template-columns: 1fr; } }

    .nodes-card { padding: 10px 6px; position: relative; }
    .nf-hit { fill: transparent; cursor: pointer; }
    .node-pop { position: absolute; z-index: 5; width: min(340px, calc(100% - 16px)); box-sizing: border-box; padding: 12px 14px 10px; background: var(--card); border: 1px solid var(--line); border-radius: 14px; box-shadow: 0 10px 30px rgba(0,0,0,0.35); pointer-events: none; }
    .node-pop[hidden] { display: none; }
    .node-pop.pin { pointer-events: auto; }
    .np-head { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; font-size: 13px; color: var(--muted); }
    .np-head b { font-size: 15px; color: var(--text); }
    .np-x { display: none; background: none; border: 0; color: var(--muted); font-size: 18px; line-height: 1; cursor: pointer; padding: 0 2px; }
    .node-pop.pin .np-x { display: inline-block; }
    .np-svg { width: 100%; height: auto; display: block; margin-top: 6px; touch-action: none; }
    .np-area-p, .np-area-n { stroke: none; }
    .np-zero { stroke: var(--line); stroke-width: 1; }
    .np-tick { fill: var(--muted); font-size: 10px; }
    .np-cur { stroke: var(--muted); stroke-width: 1; stroke-dasharray: 3 3; }
    .np-stats { display: flex; justify-content: space-between; gap: 8px; flex-wrap: wrap; font-size: 11px; color: var(--muted); margin-top: 4px; }
    .np-stats b { color: var(--text2); font-weight: 600; }
    .np-det { display: grid; grid-template-columns: 1fr auto; gap: 3px 12px; margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--line); font-size: 12px; color: var(--muted); }
    .np-det b { color: var(--text2); font-weight: 600; text-align: right; }
    .np-msg { padding: 26px 0; text-align: center; font-size: 12px; color: var(--muted); }
    .nf-leg { display: flex; gap: 14px; flex-wrap: wrap; justify-content: center; font-size: 12px; color: var(--muted); padding: 2px 10px 6px; }
    .nf-leg i { display: inline-block; vertical-align: -1px; margin-right: 5px; }
    .nf-k { width: 3px; height: 11px; background: #ff3b30; border-radius: 2px; }
    .nf-t { width: 8px; height: 8px; background: #af52de; border-radius: 2px; transform: rotate(45deg); }
    .nf-chips { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; padding: 4px 10px 6px; }
    .nf-chip { border: 1px solid var(--line); border-radius: 14px; padding: 8px 10px; min-width: 0; }
    .nf-cap { font-size: 12px; color: var(--muted); display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .nf-cap input { width: 90px; }
    .nf-chip small { display: block; font-size: 11px; color: var(--muted); }
    .nf-chip b { font-size: 15px; font-variant-numeric: tabular-nums; }
    @media (max-width: 560px) { .nf-chips { grid-template-columns: repeat(2, 1fr); } }
    .nf-svg { width: 100%; height: auto; max-height: 420px; display: block; }
    .nf-line { fill: none; stroke-linecap: round; stroke-dasharray: 6 8; animation: nfFlow 0.9s linear infinite; }
    .nf-idle { fill: none; stroke: var(--line); stroke-width: 2; stroke-dasharray: 3 7; stroke-linecap: round; }
    @keyframes nfFlow { to { stroke-dashoffset: -14; } }
    .nf-hub { fill: var(--card); stroke: var(--line); stroke-width: 2; }
    .nf-bg { fill: var(--card); stroke: var(--line); stroke-width: 2; }
    .nf-track { stroke: var(--surface); }
    .nf-soc { font-size: 22px; font-weight: 700; fill: var(--text); }
    .nf-v { font-size: 18px; font-weight: 700; fill: var(--text); }
    .nf-s { font-size: 13px; fill: var(--muted); }
    .nf-big .nf-v { font-size: 23px; } .nf-big .nf-s { font-size: 16px; } .nf-big .nf-d { font-size: 15px; } .nf-big .nf-soc { font-size: 28px; }
    .nf-d { font-size: 12px; fill: var(--text2); paint-order: stroke; stroke: var(--card); stroke-width: 4px; stroke-linejoin: round; }
    .nf-dvw { font-size: 13px; font-weight: 700; fill: var(--text); font-family: inherit; font-variant-numeric: tabular-nums; }
    .nf-dvw.off { font-weight: 500; fill: var(--muted); }
    .nf-dvm { font-size: 13px; font-weight: 700; fill: var(--text2); font-family: inherit; }
    .nf-big .nf-dvw { font-size: 16px; }
    .np-run { font-style: normal; font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 8px; background: color-mix(in srgb, var(--green, #34c759) 22%, transparent); color: var(--green, #34c759); vertical-align: 1px; }
    .np-go { display: none; width: 100%; margin-top: 8px; padding: 7px 10px; background: none; border: 1px solid var(--line); border-radius: 10px; color: var(--accent); font: inherit; font-size: 12px; cursor: pointer; }
    .node-pop.pin .np-go { display: block; }
    .pl-row { margin: 14px 0; }
    .pl-h { display: flex; justify-content: space-between; gap: 8px; font-size: 13px; flex-wrap: wrap; }
    .lh-wrap { margin-top: 10px; border-top: 1px solid var(--line); padding-top: 8px; }
    .lh-wrap summary { cursor: pointer; font-size: 13px; font-weight: 600; color: var(--text2); padding: 4px 0; }
    .lh-tbl { width: 100%; border-collapse: collapse; font-size: 12.5px; margin-top: 6px; }
    .lh-tbl th { text-align: left; color: var(--muted); font-weight: 600; font-size: 11px; padding: 4px 6px; }
    .lh-tbl td { padding: 5px 6px; border-top: 1px solid var(--line); }
    .lh-tbl .num { text-align: right; font-variant-numeric: tabular-nums; }
    .lh-ok { color: var(--green); font-weight: 600; } .lh-mid { color: var(--orange); font-weight: 600; } .lh-bad { color: var(--red); font-weight: 600; }
    .lh-dim { color: var(--muted); } .lh-retro { color: var(--muted); font-style: italic; }
    .lh-sum { display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: 12.5px; color: var(--text2); margin: 4px 0; }
    .lh-note { font-size: 11px; color: var(--muted); margin-top: 6px; line-height: 1.4; }
    .pl-bar { height: 12px; background: var(--surface); border-radius: 8px; overflow: hidden; margin-top: 6px; }
    .pl-bar > div { height: 100%; border-radius: 8px; transition: width .4s; }
    .pl-n { font-size: 11px; color: var(--muted); margin-top: 4px; }
    @media (prefers-reduced-motion: reduce) { .nf-line { animation: none; } }

    /* ======= NORDIC ======= */
    .app { padding: 18px; }
    .header { display: flex; align-items: center; justify-content: space-between; text-align: left; gap: 12px; margin-bottom: 16px; }
    .header .title { font-size: clamp(22px, 5vw, 30px); font-weight: 700; letter-spacing: -0.6px; }
    .header .date { margin-top: 2px; }
    .header .title .logo { display: block; height: 40px; width: auto; }
    @media (max-width: 700px) { .header .title .logo { height: 34px; } }
    .hdr-r { display: flex; align-items: center; gap: 8px; flex: none; }
    .bell { position: relative; border: none; background: var(--seg-bg); color: var(--text); width: 40px; height: 36px; border-radius: 999px; cursor: pointer; font-size: 17px; line-height: 1; padding: 0; }
    .bell-n { position: absolute; top: -3px; right: -3px; min-width: 18px; height: 18px; padding: 0 5px; box-sizing: border-box; border-radius: 9px; background: #f43f5e; color: #fff; font-size: 11px; font-weight: 700; line-height: 18px; text-align: center; }
    .bell-n.calm { background: var(--accent); }
    .inb-ov { position: fixed; inset: 0; z-index: 60; background: rgba(0,0,0,0.45); display: flex; align-items: center; justify-content: center; padding: 16px; box-sizing: border-box; }
    .inb-ov[hidden] { display: none; }
    .inb { width: 100%; max-width: 560px; max-height: 86vh; display: flex; flex-direction: column; background-color: #1c1c1e; background-image: linear-gradient(var(--card), var(--card)); -webkit-backdrop-filter: blur(24px) saturate(1.3); backdrop-filter: blur(24px) saturate(1.3); color: var(--text); border-radius: 20px; box-shadow: 0 10px 40px rgba(0,0,0,0.45); }
    :host([data-theme="light"]) .inb { background-color: #f0f0f4; }   /* pełne tło pod półprzezroczystą kartą (style Szkło, Przestrzeń) — okno jest zawsze czytelne */
    .inb-grip { display: none; }
    .inb-h { display: flex; align-items: center; gap: 8px; padding: 10px 16px 6px; }
    .inb-h b { font-size: 17px; flex: 1; }
    .inb-x { border: none; background: var(--surface); color: var(--text); width: 30px; height: 30px; border-radius: 50%; cursor: pointer; font-size: 14px; }
    .inb-body { overflow-y: auto; padding: 4px 16px 16px; }
    .inb-pill { display: inline-block; font-size: 11px; padding: 2px 8px; border-radius: 999px; background: rgba(251,191,36,0.18); color: #fbbf24; margin: 0 16px 6px; }
    .inb-sec { display: flex; align-items: center; justify-content: space-between; margin: 14px 0 6px; font-size: 12px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; color: var(--muted); }
    .inb-sec button { border: none; background: none; color: var(--accent); font-size: 12px; cursor: pointer; padding: 2px 4px; }
    .inb-card { background: var(--surface); border-radius: 14px; padding: 10px 12px; margin-bottom: 8px; border-left: 3px solid transparent; }
    .inb-card.p-change { border-left-color: #10b981; } .inb-card.p-skip { border-left-color: #f43f5e; opacity: .85; }
    .inb-card.n-error { border-left-color: #f43f5e; } .inb-card.n-warn { border-left-color: #fbbf24; } .inb-card.n-ok { border-left-color: #10b981; } .inb-card.n-info { border-left-color: var(--accent); }
    .inb-card.unread .inb-t { font-weight: 700; }
    .inb-r { display: flex; align-items: center; gap: 8px; justify-content: space-between; }
    .inb-t { font-size: 14px; } .inb-time { font-size: 11px; color: var(--muted); flex: none; }
    .inb-tag { font-size: 10.5px; font-weight: 700; padding: 2px 7px; border-radius: 999px; flex: none; }
    .inb-v { margin: 6px 0 2px; font-size: 14px; display: flex; flex-wrap: wrap; gap: 4px 14px; } .inb-v i { color: var(--muted); font-style: normal; }
    .inb-auto { margin: 8px 0 2px; padding: 7px 10px; border-radius: 10px; font-size: 12.5px; line-height: 1.4; background: rgba(255,159,10,.14); color: var(--orange); }
    .inb-auto.wait { background: var(--surface); color: var(--muted); }
    .inb-card details { margin-top: 4px; } .inb-card summary { cursor: pointer; font-size: 12px; color: var(--muted); }
    .inb-why, .inb-msg { font-size: 12.5px; color: var(--text2); margin-top: 4px; white-space: pre-line; }
    .inb-btns { display: flex; gap: 8px; margin-top: 8px; }
    .inb-btns button { flex: 1; padding: 9px; border-radius: 10px; border: 1px solid var(--line); background: var(--surface); color: var(--text); font-size: 14px; cursor: pointer; }
    .inb-btns button.ok { background: rgba(16,185,129,0.2); border-color: #10b981; font-weight: 700; }
    .inb-autotag { font-size: 11px; color: var(--muted); flex: 1 1 auto; min-width: 0; overflow-wrap: anywhere; }
    .inb-act { display: flex; gap: 12px; margin-top: 4px; align-items: center; } .inb-act button { border: none; background: none; color: var(--accent); font-size: 12px; cursor: pointer; padding: 2px 0; }
    .inb-empty { color: var(--muted); font-size: 13px; padding: 10px 2px; }
    .theme-seg { display: inline-flex; padding: 3px; background: var(--seg-bg); border-radius: 999px; flex: none; }
    .theme-seg button { border: none; background: transparent; color: var(--muted); width: 34px; height: 30px; border-radius: 999px; cursor: pointer; font-size: 15px; line-height: 1; padding: 0; }
    .theme-seg button.active { background: var(--seg-active); color: var(--text); box-shadow: 0 1px 4px rgba(0,0,0,0.18); }
    /* wąski telefon: logo i przyciski o kilka pikseli mniejsze, żeby nagłówek mieścił się w jednym wierszu (370 px i mniej, a potem 335 px i mniej); po definicjach .bell i .theme-seg, żeby je nadpisać */
    @media (max-width: 370px) { .header { gap: 8px; } .header .title .logo { height: 30px; } .hdr-r { gap: 6px; } .bell { width: 36px; } .theme-seg button { width: 31px; } }
    @media (max-width: 335px) { .header .title .logo { height: 26px; } .hdr-r { gap: 5px; } .bell { width: 34px; } .theme-seg button { width: 29px; } }
    .tabs { background: var(--seg-bg); border-radius: 14px; padding: 3px; }
    .tab { border-radius: 11px; color: var(--text2); font-weight: 600; }
    /* pasek zakładek na dole: pływająca „wyspa” z pełnym tłem, ikony z podpisami, aktywna zakładka jako pastylka */
    :host { --tab-on: #34d399; --tab-on-fg: #05261a; --tab-off: #c7c7cc; --tab-bg: #2c2c2e; --tab-line: #3a3a3c; --tab-bot: calc(env(safe-area-inset-bottom, 0px) * 0.35 + 6px); }
    :host([data-theme="light"]) { --tab-on: #059669; --tab-on-fg: #fff; --tab-off: #3a3a3c; --tab-bg: #fff; --tab-line: rgba(60,60,67,0.18); }
    .tabs.bottom { position: sticky; bottom: var(--tab-bot); z-index: 30; isolation: isolate; margin: 16px 0 -8px; padding: 5px; background: var(--tab-bg); border: 1px solid var(--tab-line); border-radius: 30px; box-shadow: 0 8px 24px rgba(0,0,0,0.35); overflow: visible; gap: 2px; justify-content: space-around; }
    .tabs.bottom::before { content: ''; position: absolute; left: -14px; right: -14px; top: -28px; bottom: calc(-1 * var(--tab-bot) - 14px); z-index: -1; pointer-events: none; background: linear-gradient(180deg, transparent, var(--bg) 42%); }
    .tabs.bottom .tab { flex: 1 1 0; min-width: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px; padding: 7px 2px 6px; border-radius: 24px; background: transparent; box-shadow: none; color: var(--tab-off); position: relative; transition: background .2s, color .2s; }
    .tabs.bottom .tab .ti { display: flex; position: relative; }
    .tabs.bottom .tab .ti svg { width: 24px; height: 24px; }
    .tabs.bottom .tab .tl { display: none; }
    .tabs.bottom .tab .tls { display: block; font-size: 10px; font-weight: 600; line-height: 1.1; white-space: nowrap; }
    .tabs.bottom .tab.active { background: var(--tab-on); color: var(--tab-on-fg); box-shadow: none; }
    .tabs.bottom .tab.warn .ti::after { content: ''; position: absolute; top: -2px; right: -4px; width: 9px; height: 9px; border-radius: 50%; background: #ff453a; border: 2px solid var(--tab-bg); }
    @media (min-width: 641px) {
      .tabs.bottom { justify-content: center; gap: 4px; width: fit-content; max-width: 100%; margin-left: auto; margin-right: auto; }
      .tabs.bottom .tab { flex: 0 0 auto; flex-direction: row; gap: 8px; padding: 9px 16px; }
      .tabs.bottom .tab .tl { display: inline; font-size: 13px; font-weight: 600; }
      .tabs.bottom .tab .tls { display: none; }
    }
    .tabs:not(.bottom) .tab .tls { display: none; }
    .tabs:not(.bottom) .tab .ti svg { width: 16px; height: 16px; vertical-align: -3px; }
    .tabs:not(.bottom) .tab { display: inline-flex; align-items: center; justify-content: center; gap: 6px; }
    .tabs:not(.bottom) .tab .ti { display: inline-flex; }
    .section-title { letter-spacing: 0.6px; font-weight: 600; }
    .chart-card, .soc-card, .weather-tile, .ds-item, .btn, .pf-wrapper { background: var(--card); border: none; box-shadow: var(--shadow); backdrop-filter: none; }
    .chart-card, .soc-card { border-radius: 26px; }
    .pf-wrapper { border-radius: 26px; }
    .weather-tile { border-radius: 16px; }
    .ds-item, .btn { border-radius: 20px; }
    .btn:hover { background: var(--card); filter: brightness(0.97); }
    .btn.active { background: rgba(255,149,0,0.12); border: 1px solid var(--orange); color: var(--orange); }
    .btn.blocked { background: rgba(255,59,48,0.10); border: 1px solid var(--red); }
    .row { background: var(--card); border-bottom: 1px solid var(--line); padding: 14px 18px; }
    .row:first-child { border-radius: 22px 22px 0 0; }
    .row:last-child { border-radius: 0 0 22px 22px; }
    .row:only-child { border-radius: 22px; }
    .section > .row, .section .row { box-shadow: none; }
    .soc-card .soc-value { font-weight: 700; letter-spacing: -2px; }
    .socbar { height: 10px; background: var(--surface); }
    .socbar > div { background: linear-gradient(90deg, var(--green), #30d5a0); }
    .badge { background: var(--card); border: none; box-shadow: var(--shadow); color: var(--muted); }
    .badge.on { background: rgba(52,199,89,0.14); color: var(--green); box-shadow: none; border: 1px solid var(--green); }
    .badge.danger.on { background: rgba(255,59,48,0.12); color: var(--red); border-color: var(--red); box-shadow: none; }
    .price-max { color: var(--green); } .price-min { color: var(--red); }
    .price-table th, .price-table td { border-color: var(--line); }
    .price-now-hour { background: rgba(10,132,255,0.10); }
    select, input[type="time"], input[type="number"] { background: var(--input-bg); color: var(--text); border: 1px solid var(--line); border-radius: 12px; }
    input.saved-ok { border-color: var(--green) !important; } input.saved-err { border-color: var(--red) !important; }
    .suggest-item { background: var(--surface); border-radius: 16px; }
    .suggest-item input[type="checkbox"] { accent-color: var(--accent); }
    .chart-note { color: var(--orange); background: rgba(255,149,0,0.10); border-color: rgba(255,149,0,0.25); }
    .chart-footer .stat b { color: var(--text); }
    .toggle-switch, .sw { accent-color: var(--green); }
    @media (max-width: 700px) { .chart-box { height: 340px; } .app { padding: 12px; } .header .title { font-size: 22px; } }
  `;

  const ENTITY_FALLBACKS = {
    soc: ['sensor.bms_soc', 'sensor.inverter_battery', 'sensor.inverter_battery_soc'],
    pv_power: ['sensor.bms_pv_power', 'sensor.inverter_pv_power', 'sensor.inverter_dc_power'],
    load_power: ['sensor.bms_load_power', 'sensor.inverter_load_power'],
    battery_power: ['sensor.bms_battery_power', 'sensor.inverter_battery_power'],
    grid_power: ['sensor.bms_grid_power', 'sensor.inverter_grid_power', 'sensor.inverter_total_grid_power'],
    energy_pv_today: ['sensor.bms_energy_pv_today', 'sensor.inverter_today_production'],
    energy_load_today: ['sensor.bms_energy_load_today', 'sensor.inverter_daily_load'],
    energy_grid_import_today: ['sensor.bms_energy_grid_import_today', 'sensor.inverter_today_energy_import'],
    energy_grid_export_today: ['sensor.bms_energy_grid_export_today', 'sensor.inverter_today_energy_export'],
    energy_battery_charge_today: ['sensor.bms_energy_battery_charge_today', 'sensor.inverter_today_battery_charge'],
    energy_battery_discharge_today: ['sensor.bms_energy_battery_discharge_today', 'sensor.inverter_today_battery_discharge'],
  };

  const PV_FORECAST_DAYS = [
    ['sensor.solcast_pv_forecast_forecast_today', 'sensor.solcast_pv_forecast_prognoza_na_dzisiaj'],
    ['sensor.solcast_pv_forecast_forecast_tomorrow', 'sensor.solcast_pv_forecast_prognoza_na_jutro'],
    ['sensor.solcast_pv_forecast_forecast_day_3', 'sensor.solcast_pv_forecast_prognoza_na_dzien_3'],
    ['sensor.solcast_pv_forecast_forecast_day_4', 'sensor.solcast_pv_forecast_prognoza_na_dzien_4'],
    ['sensor.solcast_pv_forecast_forecast_day_5', 'sensor.solcast_pv_forecast_prognoza_na_dzien_5'],
    ['sensor.solcast_pv_forecast_forecast_day_6', 'sensor.solcast_pv_forecast_prognoza_na_dzien_6'],
    ['sensor.solcast_pv_forecast_forecast_day_7', 'sensor.solcast_pv_forecast_prognoza_na_dzien_7'],
  ];

  const dayNightPlugin = {
    id: 'dayNight',
    beforeDraw: (chart) => {
      const { ctx, chartArea: { top, bottom, left, right }, scales: { x } } = chart;
      if (!x.min || !x.max) return;
      ctx.save();
      const dayMs = 24 * 60 * 60 * 1000;
      const start = x.min;
      const end = x.max;

      for (let t = start; t < end; t += dayMs) {
        const d = new Date(t);
        d.setHours(20, 0, 0, 0);
        const nightStart = d.getTime();
        const nightEnd = nightStart + (10 * 60 * 60 * 1000);

        const xStart = Math.max(left, x.getPixelForValue(nightStart));
        const xEnd = Math.min(right, x.getPixelForValue(nightEnd));

        if (xEnd > xStart) {
          ctx.fillStyle = TC('night');
          ctx.fillRect(xStart, top, xEnd - xStart, bottom - top);
        }
      }
      ctx.restore();
    }
  };

  class BmsPanel extends HTMLElement {
    setConfig(config) { this._config = config || {}; }
    static getStubConfig() { return {}; }
    getCardSize() { return 14; }

    constructor() {
      super();
      this._hass = null;
      this._rendered = false;
      this._activeTab = 'main';
      this._flowRaf = null;
      this._lastUserChange = {};
      this._weatherForecast = null;
      this._weatherError = null;
      this._weatherEid = null;
      this._lastWeatherFetch = 0;
      this._lastPriceTableKey = null;
      this._lastWeatherKey = null;
      this._lastPvProdKey = null;
      this._lastLoadConsKey = null;
      this._lastForecast7dKey = null;
      this._lastHourlyFcKey = null;
      this._history24h = null;
      this._lastHistoryFetch = 0;
      
      this._chartJsInstance = null;
      this._historyRange = '1D';
      this._historyData = null;
    }

    set hass(hass) {
      this._hass = hass;
      PREFS.attach(this, hass);
      try {
        const bs = Number(this._rsAttrs().battery_charge_sign);
        if (bs === 1 || bs === -1) INVERT_BATTERY_SIGN = (bs === -1);
      } catch (e) { /* zostaje poprzednia wartość */ }
      if (!this._rendered) {
        if (!this.shadowRoot) this.attachShadow({ mode: 'open' });
        this._rendered = true;   // ustawiane przed budową — wyjątek nie może powielać powłoki przy kolejnych hass
        try {
          this._renderShell();
        } catch (e) {
          console.error('EMS PANEL: błąd budowy interfejsu', e);
          const err = document.createElement('div');
          err.style.cssText = 'padding:16px;color:#f87171;font:14px sans-serif';
          err.textContent = 'EMS: błąd budowy panelu — szczegóły w konsoli przeglądarki (F12).';
          this.shadowRoot.appendChild(err);
          return;
        }
        this._startFlowLoop();
        this._safe(() => this._tipInit());
        this._fetchWeatherForecast();
        setTimeout(() => this._fetchHistory24h(), 1500);
      }
      this._applyTheme();
      this._render();

      const now = Date.now();
      if (now - this._lastWeatherFetch > 15 * 60 * 1000) this._fetchWeatherForecast();
      if (now - this._lastHistoryFetch > 5 * 60 * 1000) this._fetchHistory24h();
    }

    connectedCallback() {
      if (this._rendered && this._tileOn('main-flow')) this._startFlowLoop();
    }

    _dateKey(d) {
      const y = d.getFullYear();
      const m = String(d.getMonth() + 1).padStart(2, '0');
      const day = String(d.getDate()).padStart(2, '0');
      return `${y}-${m}-${day}`;
    }
    _todayKey() { return this._dateKey(new Date()); }
    _tomorrowKey() { const d = new Date(); d.setDate(d.getDate() + 1); return this._dateKey(d); }
    _dayDiff(keyA, keyB) {
      const a = new Date(keyA + 'T12:00:00'), b = new Date(keyB + 'T12:00:00');
      return Math.round((a - b) / 86400000);
    }
    // Wspólny dymek z danymi dla wykresów: czyta atrybut title / data-tip albo dziecko <title> elementu SVG, pokazuje go po najechaniu
    // myszą, a na ekranie dotykowym po dotknięciu (natywne podpowiedzi przeglądarki nie działają na telefonie i pojawiają się z opóźnieniem).
    // Elementy interaktywne (przyciski, pola, linki) zostawiamy w spokoju.
    _tipInit() {
      const root = this.shadowRoot; if (!root || this._tipBound) return;
      this._tipBound = true;
      const st = document.createElement('style');
      st.textContent = '.bms-tip { position:fixed; z-index:99999; max-width:min(280px, 86vw); padding:6px 10px; border-radius:10px; font-size:12px; line-height:1.4; white-space:pre-line; '
        + 'pointer-events:none; background:var(--card, #1c1c1e); color:var(--text, #fff); border:1px solid var(--line, rgba(255,255,255,.18)); box-shadow:0 6px 20px rgba(0,0,0,.35); display:none; }';
      root.appendChild(st);
      const tip = document.createElement('div'); tip.className = 'bms-tip'; tip.setAttribute('role', 'tooltip'); root.appendChild(tip);
      let hideT = null;
      const INTER = 'button, a, input, select, textarea, summary, label, [role="button"], [data-act], [data-dv], [data-tab]';
      const textOf = (el) => {
        if (!el || el.nodeType !== 1) return '';
        let tx = el.getAttribute('data-tip');
        if (!tx && el.hasAttribute('title')) { tx = el.getAttribute('title'); el.setAttribute('data-tip', tx); el.removeAttribute('title'); }
        if (!tx) {
          const tt = Array.from(el.children).find((c) => c.tagName && c.tagName.toLowerCase() === 'title');
          if (tt) { tx = tt.textContent; el.setAttribute('data-tip', tx); tt.remove(); }
        }
        return (tx || '').trim();
      };
      const find = (target, ev) => {
        if (target && target.tagName === 'CANVAS' && Array.isArray(target._tipR) && ev) {          // własne wykresy na canvasie: obszary zapisane przy rysowaniu
          const r = target.getBoundingClientRect(); const px = ev.clientX - r.left, py = ev.clientY - r.top;
          const hit = target._tipR.find((q) => px >= q.x && px <= q.x + q.w && py >= q.y && py <= q.y + q.h);
          return hit ? hit.text : '';
        }
        for (let el = target; el && el !== root && el.nodeType === 1; el = el.parentNode || el.host) {
          if (el.matches && el.matches(INTER)) return null;
          const tx = textOf(el);
          if (tx) return tx;
        }
        return '';
      };
      const place = (x, y) => {
        tip.style.left = '0px'; tip.style.top = '0px';
        const r = tip.getBoundingClientRect(); const vw = window.innerWidth, vh = window.innerHeight;
        let l = x + 14, tp = y + 16;
        if (l + r.width > vw - 6) l = Math.max(6, x - r.width - 14);
        if (tp + r.height > vh - 6) tp = Math.max(6, y - r.height - 14);
        tip.style.left = l + 'px'; tip.style.top = tp + 'px';
      };
      const show = (tx, x, y) => { clearTimeout(hideT); if (tip.textContent !== tx) tip.textContent = tx; tip.style.display = 'block'; place(x, y); };
      const hide = () => { clearTimeout(hideT); tip.style.display = 'none'; };
      const onMove = (e) => {
        if (e.pointerType === 'touch') return;
        const tx = find(e.target, e);
        if (tx) show(tx, e.clientX, e.clientY); else hide();
      };
      root.addEventListener('pointermove', onMove);
      this.addEventListener('pointerleave', hide);
      root.addEventListener('pointerdown', (e) => {
        if (e.pointerType !== 'touch') { hide(); return; }
        const tx = find(e.target, e);
        if (tx) { show(tx, e.clientX, e.clientY); hideT = setTimeout(hide, 4000); } else hide();
      });
      window.addEventListener('scroll', hide, { passive: true, capture: true });
    }
    disconnectedCallback() { this._stopFlowLoop(); }

    _startFlowLoop() {
      this._stopFlowLoop();
      const loop = () => {
        if (this._tileOn('main-flow')) this._drawPowerflow();
        this._flowRaf = requestAnimationFrame(loop);
      };
      this._flowRaf = requestAnimationFrame(loop);
    }
    _stopFlowLoop() {
      if (this._flowRaf) { cancelAnimationFrame(this._flowRaf); this._flowRaf = null; }
    }

    _el(id) { return this.shadowRoot && this.shadowRoot.getElementById(id); }

    _eid(domain, key) {
      const expectedUid = `bms_komp_dec_v7_${key}`;
      if (this._hass.entities) {
        for (const eid in this._hass.entities) {
          const ent = this._hass.entities[eid];
          if (ent && ent.platform === 'bms_komp_dec' && ent.unique_id === expectedUid
              && eid.startsWith(domain + '.')) return eid;
        }
      }
      const base = `${domain}.bms_${key}`;
      if (this._hass.states[base]) return base;
      for (const eid in this._hass.states) {
        if (eid.startsWith(base + '_') && /_\d+$/.test(eid)) {
          const st = this._hass.states[eid];
          if (st && st.state !== 'unavailable') return eid;
        }
      }
      return base;
    }

    _eidStatus(eid) {
      const st = this._hass.states[eid];
      if (!st) return 'missing';
      if (st.state === 'unavailable') return 'unavail';
      return 'ok';
    }

    _findEntity(candidates) {
      for (const eid of candidates) {
        const s = this._hass.states[eid];
        if (s && s.state !== 'unknown' && s.state !== 'unavailable' && s.state !== '') {
          return { eid, state: s.state, value: parseFloat(s.state) };
        }
      }
      return null;
    }

    _num(key, def = 0) {
      const candidates = ENTITY_FALLBACKS[key];
      if (!candidates) return def;
      const found = this._findEntity(candidates);
      if (found && !isNaN(found.value)) return found.value;
      return def;
    }

    _st(eid, def = '') {
      const s = this._hass.states[eid];
      return (s && s.state !== 'unknown' && s.state !== 'unavailable') ? s.state : def;
    }

    _call(domain, service, data) {
      if (!this._hass) return Promise.resolve();
      return this._hass.callService(domain, service, data);
    }

    _showToast(message, isError = false) {
      const toast = document.createElement('div');
      toast.textContent = message;
      toast.style.cssText = `position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:${isError ? '#f43f5e' : '#10b981'};color:${isError ? '#fff' : '#000'};padding:12px 20px;border-radius:20px;font-weight:bold;font-family:sans-serif;font-size:14px;z-index:9999;box-shadow:0 4px 12px rgba(0,0,0,0.5);transition:opacity 0.3s;max-width:90vw;word-break:break-all;`;
      document.body.appendChild(toast);
      setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 300); }, 4000);
    }

    // atrybuty sensora reserve_soc: stąd karta bierze dane liczone przez integrację (rozwiązane encje falownika,
    // znak mocy baterii, okna taryfy) zamiast stałych w kodzie
    _rsAttrs() {
      const rs = this._hass && this._hass.states[this._eid('sensor', 'reserve_soc')];
      return (rs && rs.attributes) || {};
    }
    // encja sterująca falownika (work_mode / charge_current / export_surplus / tou) rozwiązana przez backend
    _ctl(role, legacy) {
      const eid = this._rsAttrs()['ctl_' + role];
      return (eid && this._hass.states[eid]) ? eid : legacy;
    }
    // prefiks encji falownika (np. 'inverter', 'deye') — z backendu; domyślnie jak dotychczas
    _invPrefix() { return String(this._rsAttrs().inverter_prefix || 'inverter'); }
    _inv(domain, tail) { return `${domain}.${this._invPrefix()}_${tail}`; }
    _tariffTxt() {
      const a = this._rsAttrs();
      const peaks = String(a.tariff_peaks || '6-13,15-22');
      const spans = peaks === 'brak' ? [] : peaks.split(',').map(x => x.split('-').map(Number)).filter(x => x.length === 2 && isFinite(x[0]) && isFinite(x[1]));
      const hh = (n) => String(n % 24).padStart(2, '0') + ':00';
      const nraw = a.tariff_night === undefined ? '22-6' : a.tariff_night;   // null = taryfa bez okna nocnego
      const night = nraw ? String(nraw).split('-').map(Number) : [];
      return {
        peaks: spans.length ? spans.map(x => `${x[0]}–${x[1]}`).join(' i ') : 'brak (taryfa jednostrefowa)',
        day: spans.length ? `${spans[0][0]}–${spans[spans.length - 1][1]}` : '',
        night: night.length === 2 && isFinite(night[0]) && isFinite(night[1]) ? `${hh(night[0])}–${hh(night[1])}` : 'brak',
        start: spans.length ? hh(spans[0][0]) : '',
        dynamic: a.tariff_dynamic === true,
      };
    }
    _isPvBlocked() {
      const st = this._hass.states[this._ctl('charge_current', 'number.inverter_battery_max_charging_current')];
      if (!st) return false;
      try { return parseFloat(st.state) <= 0.1; } catch { return false; }
    }
    _isGridChargingOn() {
      const st = this._hass.states[this._ctl('tou', 'select.inverter_time_of_use')];
      if (!st) return false;
      return ['disabled', 'disable', 'off'].includes(String(st.state).trim().toLowerCase());
    }
    _isSellBlockedByImport() {
      const eid = this._eid('binary_sensor', 'sprzedaz_zablokowana_importem');
      return this._st(eid) === 'on';
    }

    // ===== POGODA =====
    _findWeatherEntity() {
      const configured = this._config && this._config.weather_entity;
      if (configured && this._hass.states[configured]) return configured;
      const candidates = ['weather.forecast_dom', 'weather.dom', 'weather.home', 'weather.forecast_home', 'weather.pogoda'];
      for (const eid of candidates) if (this._hass.states[eid]) return eid;
      for (const eid in this._hass.states) if (eid.startsWith('weather.')) return eid;
      return null;
    }

    async _fetchWeatherForecast() {
      this._lastWeatherFetch = Date.now();
      if (!this._hass) return;
      const weatherEid = this._findWeatherEntity();
      if (!weatherEid) {
        this._weatherForecast = null;
        this._weatherError = 'Nie znaleziono encji weather.* w HA';
        this._renderWeather();
        return;
      }
      const extract = (res, eid) => {
        if (!res) return null;
        const data = res.response !== undefined ? res.response : res;
        if (!data || typeof data !== 'object') return null;
        if (data[eid] && Array.isArray(data[eid].forecast)) return data[eid].forecast;
        if (Array.isArray(data.forecast)) return data.forecast;
        if (Array.isArray(data)) return data;
        return null;
      };
      let fc = null, err = null;
      try {
        const res = await this._hass.callService('weather', 'get_forecasts',
          { entity_id: weatherEid, type: 'daily' }, undefined, false, true);
        fc = extract(res, weatherEid);
      } catch (e) { err = e; }
      if (!fc) {
        try {
          const res = await this._hass.callService('weather', 'get_forecast',
            { entity_id: weatherEid, type: 'daily' }, undefined, false, true);
          fc = extract(res, weatherEid);
        } catch (e) { err = err || e; }
      }
      if (!fc) {
        const st = this._hass.states[weatherEid];
        if (st && Array.isArray(st.attributes.forecast) && st.attributes.forecast.length) {
          fc = st.attributes.forecast;
        }
      }
      if (Array.isArray(fc) && fc.length > 0) {
        this._weatherForecast = fc;
        this._weatherError = null;
        this._weatherEid = weatherEid;
      } else {
        this._weatherForecast = null;
        this._weatherError = `Brak prognozy z ${weatherEid}` + (err ? ` (${err.message || err})` : '');
        this._lastWeatherFetch = Date.now() - 14 * 60 * 1000;
      }
      this._renderWeather();
    }

    // Ikony pogody: własne SVG z animacją CSS (bez zewnętrznych bibliotek); nieznany stan -> emoji
    _getWeatherIcon(condition) {
      const c = (condition || '').toLowerCase();
      const cloud = (x, y, cls) => `<g class="${cls || 'c1'}" transform="translate(${x} ${y})"><circle cx="17" cy="29" r="7"/><circle cx="26" cy="23" r="9"/><circle cx="35" cy="29" r="7"/><rect x="17" y="29" width="18" height="7"/></g>`;
      const rays = (cx, cy, r1, r2, cls) => { let o = `<g class="${cls}">`; for (let k = 0; k < 8; k++) { const a = k * Math.PI / 4, ca = Math.cos(a), sa = Math.sin(a); o += `<line class="ray" x1="${(cx + ca * r1).toFixed(1)}" y1="${(cy + sa * r1).toFixed(1)}" x2="${(cx + ca * r2).toFixed(1)}" y2="${(cy + sa * r2).toFixed(1)}"/>`; } return o + '</g>'; };
      const drops = (fast, n) => { const xs = n === 4 ? [17, 24, 31, 38] : [20, 28, 36]; return xs.map((x, k) => `<line class="drop a-drop${fast ? ' fast' : ''}" style="animation-delay:${(k * 0.28).toFixed(2)}s" x1="${x}" y1="38" x2="${x - 2}" y2="43"/>`).join(''); };
      const flakes = [[19, 40, 0], [27, 40, 1], [35, 40, 2]].map(([x, y, k]) => `<circle class="flake a-snow" style="animation-delay:${(k * 0.9).toFixed(1)}s" cx="${x}" cy="${y}" r="1.7"/>`).join('');
      const bolt = '<polygon class="bolt a-flash" points="26,30 19,42 25,42 22,52 34,37 27,37 31,30"/>';
      const svg = (inner) => `<svg class="wx" viewBox="0 0 48 48" aria-hidden="true">${inner}</svg>`;
      if (c.includes('lightning') && c.includes('rain')) return svg(`<g class="a-float">${cloud(0, -6, 'c2')}</g><g transform="translate(0 -4)">${drops(true, 3)}</g>${bolt.replace('class="bolt a-flash"', 'class="bolt a-flash" transform="translate(0 -6)"')}`);
      if (c.includes('lightning')) return svg(`<g class="a-float">${cloud(0, -8, 'c2')}</g><g transform="translate(0 -3)">${bolt}</g>`);
      if (c.includes('pouring')) return svg(`<g class="a-float">${cloud(0, -7, 'c2')}</g><g transform="translate(0 -3)">${drops(true, 4)}</g>`);
      if (c.includes('snowy-rainy')) return svg(`<g class="a-float">${cloud(0, -7, 'c1')}</g><g transform="translate(0 -3)"><line class="drop a-drop" x1="19" y1="38" x2="17" y2="43"/><line class="drop a-drop" style="animation-delay:.4s" x1="27" y1="38" x2="25" y2="43"/><circle class="flake a-snow" cx="35" cy="40" r="1.7"/></g>`);
      if (c.includes('rain')) return svg(`<g class="a-float">${cloud(0, -7, 'c1')}</g><g transform="translate(0 -3)">${drops(false, 3)}</g>`);
      if (c.includes('snow')) return svg(`<g class="a-float">${cloud(0, -7, 'c1')}</g><g transform="translate(0 -3)">${flakes}</g>`);
      if (c.includes('hail')) return svg(`<g class="a-float">${cloud(0, -7, 'c2')}</g><g transform="translate(0 -3)">${flakes}</g>`);
      if (c.includes('fog') || c.includes('mist')) return svg(`<g class="a-drift">${cloud(0, -4, 'c1')}</g><g class="a-drift2"><line class="fogln" x1="12" y1="36" x2="34" y2="36"/></g><g class="a-drift"><line class="fogln" x1="16" y1="42" x2="38" y2="42"/></g>`);
      if (c.includes('wind')) return svg(`<path class="wind a-wind" d="M6 18 H30 a5 5 0 1 0 -5 -5"/><path class="wind a-wind" style="animation-delay:.5s" d="M6 28 H38 a5 5 0 1 1 -5 5"/><path class="wind a-wind" style="animation-delay:1s" d="M6 38 H22"/>`);
      if (c.includes('partly')) return svg(`${rays(17, 17, 10, 14, 'a-spin-s')}<circle class="sun a-pulse" style="transform-origin:17px 17px" cx="17" cy="17" r="7"/><g class="a-drift">${cloud(5, 5, 'c1')}</g>`);
      if (c.includes('cloudy')) return svg(`<g class="a-drift2">${cloud(-6, -6, 'c2')}</g><g class="a-drift">${cloud(5, 2, 'c1')}</g>`);
      if (c.includes('night') || (c.includes('clear') && c.includes('moon'))) return svg(`<path class="moon a-float" d="M30 10a14 14 0 1 0 8 25 11.5 11.5 0 0 1-8-25z"/><circle class="star a-twinkle" cx="37" cy="14" r="1.6"/><circle class="star a-twinkle" style="animation-delay:1s" cx="41" cy="24" r="1.2"/>`);
      if (c.includes('sunny') || c.includes('clear')) return svg(`${rays(24, 24, 13, 18, 'a-spin')}<circle class="sun a-pulse" cx="24" cy="24" r="9"/><circle class="sun2" cx="24" cy="24" r="5" opacity=".55"/>`);
      return '🌡️';
    }

    _renderWeather() {
      const container = this._el('weatherContainer');
      if (!container) return;
      if (this._weatherError) {
        this._lastWeatherKey = null;
        container.innerHTML = `<div style="padding:10px;color:#fbbf24;font-size:12px;">⚠️ ${this._weatherError}</div>`;
        return;
      }
      if (!this._weatherForecast || !this._weatherForecast.length) {
        this._lastWeatherKey = null;
        container.innerHTML = '<div style="padding:10px;color:var(--muted);font-size:12px;">Ładowanie prognozy…</div>';
        return;
      }
      const fc = this._weatherForecast;
      const todayKey = this._todayKey();
      const tmrKey = this._tomorrowKey();
      const pvSig = PV_FORECAST_DAYS.map((_l, i) => { const di = this._pvDayInfo(i); return String(this._pvDayKwh(i)) + (di ? ':' + di.lo + ':' + di.hi + ':' + di.factor + (di.est ? ':est' : '') : ''); }).join('|');
      const cacheKey = todayKey + '#' + JSON.stringify(fc.slice(0, 7)) + '#' + pvSig;
      if (this._lastWeatherKey === cacheKey) return;
      this._lastWeatherKey = cacheKey;
      let html = '';
      for (let i = 0; i < Math.min(fc.length, 7); i++) {
        const dayData = fc[i];
        if (!dayData || !dayData.datetime) continue;
        const dt = new Date(dayData.datetime);
        const dtKey = this._dateKey(dt);
        let label = dt.toLocaleDateString('pl-PL', { weekday: 'short' }).toUpperCase();
        if (dtKey === todayKey) label = 'DZIŚ';
        else if (dtKey === tmrKey) label = 'JUTRO';
        const icon = this._getWeatherIcon(dayData.condition);
        const maxT = (dayData.temperature == null ? '--' : Math.round(dayData.temperature)) + '°';
        const minT = (dayData.templow == null ? '--' : Math.round(dayData.templow)) + '°';
        const pvOffset = this._dayDiff(dtKey, todayKey);
        const pvVal = (pvOffset >= 0 && pvOffset < 7) ? this._pvDayKwh(pvOffset) : null;
        html += `
          <div class="weather-tile">
            <div class="day">${label}</div>
            <div class="wt-row"><div class="icon">${icon}</div><div class="temp-max">${maxT}</div></div>
            <div class="temp-min">min ${minT}</div>
            ${pvVal !== null ? `<div class="pv"${this._pvTip(pvOffset)}>${((this._pvDayInfo(pvOffset) || {}).est === true ? '~' : '') + pvVal.toFixed(1)} kWh</div>${this._pvRange(pvOffset)}` : ''}
          </div>
        `;
      }
      container.innerHTML = html;
    }

    // ===== HISTORIA 24h (PV energy) =====
    async _fetchHistory24h() {
      if (!this._hass) return;
      const now = new Date();
      const dayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      const pvEid = this._eid('sensor', 'energy_pv_today');
      const candidates = [pvEid];
      for (const fb of [this._inv('sensor', 'today_production')]) {
        if (fb !== pvEid && this._hass.states[fb]) candidates.push(fb);
      }
      try {
        const res = await this._hass.callWS({
          type: 'history/history_during_period',
          start_time: dayStart.toISOString(),
          end_time: now.toISOString(),
          entity_ids: candidates,
          minimal_response: false,
          no_attributes: true,
          significant_changes_only: false,
          include_start_time_state: true,
        });
        let chosenEid = pvEid;
        let historyArr = (res && res[pvEid]) || [];
        if (!historyArr.length) {
          for (const c of candidates.slice(1)) {
            const arr = (res && res[c]) || [];
            if (arr.length) { chosenEid = c; historyArr = arr; break; }
          }
        }
        this._history24h = { eid: chosenEid, dayStart, end: now, historyArr };
        this._lastHistoryFetch = Date.now();
        requestAnimationFrame(() => this._renderPvProductionChart());
      } catch (e) {
        console.warn('EMS history fetch error:', e);
        this._lastHistoryFetch = Date.now() - 4 * 60 * 1000;
      }
    }

    _processEnergyHistoryToHourly(historyArr, dayStart) {
      if (!Array.isArray(historyArr)) return null;
      const startMs = dayStart.getTime();
      const samples = [];
      for (const item of historyArr) {
        if (!item) continue;
        let ts = null;
        if (typeof item.last_changed === 'string') ts = new Date(item.last_changed).getTime();
        else if (typeof item.last_updated === 'string') ts = new Date(item.last_updated).getTime();
        else if (typeof item.lc === 'number') ts = item.lc * 1000;
        else if (typeof item.lu === 'number') ts = item.lu * 1000;
        if (ts === null || isNaN(ts)) continue;
        const val = parseFloat(item.state !== undefined ? item.state : item.s);
        if (isNaN(val)) continue;
        samples.push({ ts, val });
      }
      if (!samples.length) return new Array(24).fill(null);
      samples.sort((a, b) => a.ts - b.ts);

      const hourly = new Array(24).fill(null);
      let last = null;
      for (const smp of samples) {
        if (last === null) { last = smp.val; if (smp.ts >= startMs) this._addHour(hourly, smp.ts, startMs, 0); continue; }
        let delta;
        if (smp.val >= last - 0.001) delta = Math.max(0, smp.val - last);
        else delta = Math.max(0, smp.val);
        last = smp.val;
        if (smp.ts < startMs) continue;
        if (delta > 100) continue;
        this._addHour(hourly, smp.ts, startMs, delta);
      }
      return hourly;
    }

    _addHour(hourly, ts, startMs, delta) {
      const idx = Math.floor((ts - startMs) / 3600000);
      if (idx >= 0 && idx < 24) hourly[idx] = (hourly[idx] || 0) + delta;
    }

    _getPvForecastHourly() {
      const pa = this._pvInt();
      if (pa) return Array.isArray(pa.pv_hourly_today) ? pa.pv_hourly_today.map(v => (typeof v === 'number' && isFinite(v) ? v : null)) : null;
      const candidates = [
        'sensor.solcast_pv_forecast_forecast_today',
        'sensor.solcast_pv_forecast_prognoza_na_dzisiaj',
      ];
      for (const eid of candidates) {
        const st = this._hass.states[eid];
        if (!st) continue;
        const attrs = st.attributes || {};
        const arr = attrs.detailedHourly || attrs.detailedForecast || attrs.forecast;
        if (!Array.isArray(arr) || !arr.length) continue;
        const today = this._todayKey();
        const sums = new Array(24).fill(0);
        const counts = new Array(24).fill(0);
        for (const item of arr) {
          const ps = item.period_start || item.datetime;
          if (!ps) continue;
          const dt = new Date(ps);
          if (this._dateKey(dt) !== today) continue;
          const h = dt.getHours();
          if (h < 0 || h > 23) continue;
          const val = item.pv_estimate ?? item.estimate ?? item.power ?? null;
          if (val === null) continue;
          const v = parseFloat(val);
          if (isNaN(v)) continue;
          sums[h] += v;
          counts[h] += 1;
        }
        const hourly = sums.map((sm, h) => counts[h] ? sm / counts[h] : null);
        if (hourly.some(v => v !== null)) return hourly;
      }
      return null;
    }

    // ===== ZUŻYCIE DOMU =====
    _renderLoadConsumptionChart() {
      const canvas = this._el('chartLoadCons');
      if (!canvas) return;
      const st = this._hass.states['sensor.bms_load_forecast'];
      if (!st || !st.attributes || !Array.isArray(st.attributes.days) || st.attributes.days.length === 0) {
        const parent = canvas.parentElement;
        if (parent && !parent.querySelector('.chart-empty')) {
          canvas.style.display = 'none';
          const m = document.createElement('div');
          m.className = 'chart-empty';
          m.textContent = 'Brak danych prognozy zużycia (sensor.bms_load_forecast).';
          parent.insertBefore(m, canvas.nextSibling);
        }
        return;
      }
      canvas.style.display = 'block';
      const emptyMsg = canvas.parentElement && canvas.parentElement.querySelector('.chart-empty');
      if (emptyMsg) emptyMsg.remove();

      const days = st.attributes.days;
      const confidence = st.attributes.confidence_interval || null;
      const mape = st.attributes.mape_14d;
      const historyDays = st.attributes.history_days || 0;
      const profileDays = st.attributes.profiles_days || 0;

      const tuning = st.attributes.tuning || null;
      const ebt = st.attributes.error_by_type || null;
      const key = JSON.stringify({ e: ebt, d: days, c: confidence, m: mape, h: historyDays, p: profileDays, t: tuning });
      if (this._lastLoadConsKey === key) return;
      this._lastLoadConsKey = key;

      const subEl = this._el('loadConsSub');
      if (subEl) {
        const parts = days.map(d => {
          if (d.label === 'Wczoraj' && d.actual !== null) return `Wcz: ${d.actual.toFixed(1)}`;
          if (d.label === 'Dziś' && typeof d.actual === 'number') return `Dziś: ${d.actual.toFixed(1)}`;
          if (d.label === 'Jutro' && d.forecast !== null) return `Jutro: ${d.forecast.toFixed(1)}`;
          return null;
        }).filter(Boolean);
        subEl.textContent = parts.join(' · ') + ' kWh';
      }

      const footer = this._el('loadConsFooter');
      if (footer) {
        const parts = [];
        if (mape !== null && mape !== undefined) {
          const acc = 100 - mape;
          const dotColor = acc >= 85 ? '#10b981' : acc >= 70 ? '#fbbf24' : '#f43f5e';
          parts.push(`<span class="stat"><span class="dot" style="background:${dotColor}"></span>Dokładność: <b>${acc.toFixed(0)}%</b></span>`);
        }
        if (ebt) {
          const f = (o, nm) => {
            if (!o || !o.n || o.n < 3) return '';
            const b = o.bias_pct, warn = Math.abs(b) >= 10;
            const txt = `${nm}: błąd <b>${o.mape.toFixed(0)}%</b>` + (warn ? ` (${b < 0 ? 'zawyżone' : 'zaniżone'} o ${Math.abs(b).toFixed(0)}%)` : '');
            return `<span class="stat"${warn ? ' style="color:#fbbf24"' : ''}>${txt}</span>`;
          };
          parts.push(f(ebt.work, 'Dni robocze') + f(ebt.off, 'Dni wolne'));
        }
        if (historyDays > 0) parts.push(`<span class="stat">Historia: <b>${historyDays} dni</b></span>`);
        if (profileDays >= 3) parts.push(`<span class="stat">Profil godzinowy: <b>${profileDays} dni</b></span>`);
        else if (profileDays > 0) parts.push(`<span class="stat" style="color:#fbbf24">Profil: ${profileDays}/3 dni</span>`);
        footer.innerHTML = parts.join('') || '<span class="stat">Zbieram historię...</span>';
      }

      this._drawLoadConsumptionChart(canvas, days, confidence);
      this._safe(() => this._renderLoadHistTable(st.attributes.history_14d, st.attributes.forecast_bias, tuning));
    }

    _tuneNote(t) {
      if (!t || !t.at) return '';
      const f1 = (v) => String(Number(v).toFixed(1)).replace('.', ',');
      const dt = new Date(t.at + 'T12:00:00'); const when = `${dt.getDate()}.${String(dt.getMonth() + 1).padStart(2, '0')}`;
      if (!t.n) return `<div class="lh-note" id="loadTune">🎯 Samostrojenie: ${t.note || 'zbieram historię'} (sprawdzono ${when}).</div>`;
      const better = t.mae < t.mae_default - 0.005;
      const txt = better
        ? `wariant „${t.variant}” — średni błąd na ostatnich ${t.n} dniach ${f1(t.mae)} kWh zamiast ${f1(t.mae_default)} kWh (trafienia ±20%: ${t.hit}% zamiast ${t.hit_default}%)`
        : `zostaje wariant standardowy — żaden z ${t.tried} sprawdzonych nie był wyraźnie lepszy (błąd ${f1(t.mae_default)} kWh na ostatnich ${t.n} dniach)`;
      return `<div class="lh-note" id="loadTune">🎯 Samostrojenie (${when}): ${txt}. EMS co dobę sprawdza kilka wariantów na Twojej historii i wybiera ten, który najlepiej przewidziałby ostatnie dni.</div>`;
    }

    _renderLoadHistTable(rows, bias, tune) {
      const box = this._el('loadHistTable'); if (!box) return;
      if (!Array.isArray(rows) || !rows.length) { box.innerHTML = '<div class="lh-note">Brak historii prognoz (zbieram dane).</div>'; return; }
      const wd = ['pn', 'wt', 'śr', 'czw', 'pt', 'sob', 'nd'];
      const f1 = (v) => (typeof v === 'number' ? v.toFixed(1).replace('.', ',') : '—');
      let n = 0, sumAbs = 0, sumBias = 0, hit = 0;
      const body = rows.map(r => {
        const sus = ['duplicate', 'partial', 'spike'].includes(r.suspect) ? r.suspect : null;   // podejrzana suma dnia — pomijana w modelu i podsumowaniu
        const hasA = typeof r.actual === 'number' && !sus;
        const fc = typeof r.issued === 'number' ? r.issued : (typeof r.model === 'number' ? r.model : null);
        const retro = typeof r.issued !== 'number' && fc != null;
        let diff = '—', cls = '';
        if (hasA && fc != null && r.actual > 0) {
          const d = fc - r.actual; const pct = d / r.actual * 100;
          diff = `${d > 0 ? '+' : ''}${f1(d)} (${pct > 0 ? '+' : ''}${pct.toFixed(0)}%)`;
          cls = Math.abs(pct) <= 15 ? 'lh-ok' : Math.abs(pct) <= 30 ? 'lh-mid' : 'lh-bad';
          if (!retro) { n++; sumAbs += Math.abs(d); sumBias += d; if (Math.abs(pct) <= 20) hit++; }
        }
        const dt = new Date(r.date + 'T12:00:00');
        const dayTxt = `${dt.getDate()}.${String(dt.getMonth() + 1).padStart(2, '0')} ${wd[r.weekday]}${r.holiday ? ' 🎌' : ''}`;
        if (sus) {
          const why = sus === 'duplicate' ? 'ta sama wartość co dzień wcześniej (licznik falownika nie zdążył się zresetować)' : sus === 'spike' ? 'dużo wyższa niż w sąsiednich dniach (skok licznika lub błędny odczyt)' : 'dużo niższa niż w sąsiednich dniach (niepełne dane z tego dnia)';
          return `<tr class="lh-sus" title="Pominięte w modelu i podsumowaniu: ${why}"><td title="${r.holiday || ''}">${dayTxt}</td><td class="num"><s>${f1(r.actual)}</s> ⚠</td><td class="num lh-dim">—</td><td class="num lh-dim">pominięte</td><td class="num lh-dim">${typeof r.temp === 'number' ? r.temp.toFixed(0) + '°' : ''}</td></tr>`;
        }
        return `<tr><td title="${r.holiday || ''}">${dayTxt}</td><td class="num">${f1(r.actual)}</td><td class="num ${retro ? 'lh-retro' : ''}">${f1(fc)}${retro ? '*' : ''}</td><td class="num ${cls}">${diff}</td><td class="num lh-dim">${typeof r.temp === 'number' ? r.temp.toFixed(0) + '°' : ''}</td></tr>`;
      }).join('');
      const sum = n ? `<div class="lh-sum"><span>Średni błąd: <b>${f1(sumAbs / n)} kWh</b></span><span>Obciążenie: <b>${sumBias / n > 0 ? '+' : ''}${f1(sumBias / n)} kWh</b> ${sumBias / n > 0.5 ? '(model zawyża)' : sumBias / n < -0.5 ? '(model zaniża)' : ''}</span><span>Trafione ±20%: <b>${hit}/${n}</b></span></div>` : '';
      box.innerHTML = `${sum}<table class="lh-tbl"><thead><tr><th>Dzień</th><th class="num">Rzeczywiste</th><th class="num">Prognoza</th><th class="num">Różnica</th><th class="num">Temp.</th></tr></thead><tbody>${body}</tbody></table><div class="lh-note">Prognoza = wydana dzień wcześniej. * = brak zapisanej prognozy z tamtego dnia, pokazano model liczony wstecz (nie wlicza się do podsumowania). 🎌 = święto.${rows.some(x => x.suspect) ? ' ⚠ = podejrzana suma dnia (przepisany wynik poprzedniego dnia albo niepełne dane) — pominięta w modelu i podsumowaniu.' : ''}${typeof bias === 'number' && Math.abs(bias - 1) >= 0.02 ? ` Korekta obciążenia modelu: <b>×${bias.toFixed(2).replace('.', ',')}</b> (z ostatnich 14 dni).` : ''}</div>`;
      box.insertAdjacentHTML('beforeend', this._tuneNote(tune));
    }

    _roundRect(ctx, x, y, w, h, r) {
      if (r > h / 2) r = h / 2;
      if (r > w / 2) r = w / 2;
      ctx.beginPath();
      if (r < 1) {
        ctx.rect(x, y, w, h);
      } else {
        ctx.moveTo(x + r, y);
        ctx.lineTo(x + w - r, y);
        ctx.quadraticCurveTo(x + w, y, x + w, y + r);
        ctx.lineTo(x + w, y + h - r);
        ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
        ctx.lineTo(x + r, y + h);
        ctx.quadraticCurveTo(x, y + h, x, y + h - r);
        ctx.lineTo(x, y + r);
        ctx.quadraticCurveTo(x, y, x + r, y);
        ctx.closePath();
      }
    }

    _drawLoadConsumptionChart(canvas, days, confidence) {
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.clientWidth || 400;
      const h = canvas.clientHeight || 300;
      if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
        canvas.width = Math.round(w * dpr);
        canvas.height = Math.round(h * dpr);
      }
      const ctx = canvas.getContext('2d');
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      const padL = 44, padR = 14, padT = 26, padB = 52;
      const plotW = w - padL - padR;
      const plotH = h - padT - padB;

      const all = [];
      days.forEach(d => {
        if (typeof d.actual === 'number') all.push(d.actual);
        if (typeof d.forecast === 'number') all.push(d.forecast);
        if (typeof d.nowcast === 'number') all.push(d.nowcast);
      });
      if (confidence && typeof confidence.high === 'number') all.push(confidence.high);
      if (!all.length) return;
      let maxV = Math.max(...all) * 1.25;
      if (maxV <= 0) maxV = 1;

      ctx.strokeStyle = TC('grid');
      ctx.lineWidth = 1;
      for (let g = 0; g <= 4; g++) {
        const y = padT + (g / 4) * plotH;
        ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(w - padR, y); ctx.stroke();
      }

      ctx.fillStyle = TC('muted');
      ctx.font = '10px -apple-system, sans-serif';
      ctx.textAlign = 'right';
      ctx.textBaseline = 'middle';
      for (let g = 0; g <= 4; g++) {
        const val = maxV - (g / 4) * maxV;
        const y = padT + (g / 4) * plotH;
        ctx.fillText(val.toFixed(0), padL - 6, y);
      }

      ctx.save();
      ctx.translate(12, padT + plotH / 2);
      ctx.rotate(-Math.PI / 2);
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = TC('muted');
      ctx.font = 'bold 10px -apple-system, sans-serif';
      ctx.fillText('kWh', 0, 0);
      ctx.restore();

      const slotW = plotW / 3;
      const barW = Math.min(slotW * 0.3, 64);
      const gap = 8;
      const baseY = padT + plotH;
      const tipR = canvas._tipR = [];

      days.forEach((d, i) => {
        const cx = padL + (i + 0.5) * slotW;
        {
          const f1 = (v) => (typeof v === 'number' ? v.toFixed(1).replace('.', ',') + ' kWh' : '—');
          const lines = [`${d.label || ''}${d.date ? ' ' + d.date.slice(8, 10) + '.' + d.date.slice(5, 7) : ''}`];
          if (typeof d.actual === 'number') lines.push('Rzeczywiste: ' + f1(d.actual));
          if (typeof d.forecast === 'number') lines.push('Prognoza: ' + f1(d.forecast));
          if (typeof d.nowcast === 'number' && Math.abs(d.nowcast - (d.forecast || 0)) >= 0.05) lines.push('Tempo dnia (szacunek na koniec doby): ' + f1(d.nowcast));
          if (d.label === 'Jutro' && confidence && typeof confidence.low === 'number') lines.push('Zakres: ' + f1(confidence.low) + ' – ' + f1(confidence.high));
          tipR.push({ x: padL + i * slotW, y: padT, w: slotW, h: plotH + padB, text: lines.join('\n') });
        }
        const hasActual = typeof d.actual === 'number';
        const hasForecast = typeof d.forecast === 'number';
        const isTomorrow = d.label === 'Jutro';

        if (isTomorrow && confidence && hasForecast) {
          const lowV = Math.max(0, confidence.low || 0);
          const highV = confidence.high || d.forecast;
          const lowY = baseY - (lowV / maxV) * plotH;
          const highY = baseY - (highV / maxV) * plotH;
          ctx.fillStyle = 'rgba(251,191,36,0.14)';
          this._roundRect(ctx, cx - barW / 2, highY, barW, lowY - highY, 4);
          ctx.fill();
          ctx.strokeStyle = 'rgba(251,191,36,0.35)';
          ctx.lineWidth = 1;
          ctx.stroke();
        }

        if (hasActual && hasForecast) {
          const aCx = cx - barW / 2 - gap / 2;
          const fCx = cx + barW / 2 + gap / 2;
          const aBh = Math.max(3, (d.actual / maxV) * plotH);
          const aGrad = ctx.createLinearGradient(0, baseY - aBh, 0, baseY);
          aGrad.addColorStop(0, COLORS.actualLight);
          aGrad.addColorStop(1, COLORS.actual);
          ctx.fillStyle = aGrad;
          this._roundRect(ctx, aCx - barW / 2, baseY - aBh, barW, aBh, 6);
          ctx.fill();
          ctx.fillStyle = TC('text');
          ctx.font = 'bold 13px -apple-system, sans-serif';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'bottom';
          ctx.fillText(d.actual.toFixed(1), aCx, baseY - aBh - 6);

          const fBh = Math.max(3, (d.forecast / maxV) * plotH);
          const fGrad = ctx.createLinearGradient(0, baseY - fBh, 0, baseY);
          fGrad.addColorStop(0, COLORS.forecast);
          fGrad.addColorStop(1, COLORS.forecastDark);
          ctx.fillStyle = fGrad;
          this._roundRect(ctx, fCx - barW / 2, baseY - fBh, barW, fBh, 6);
          ctx.fill();
          ctx.fillStyle = TC('text');
          ctx.font = 'bold 13px -apple-system, sans-serif';
          ctx.fillText(d.forecast.toFixed(1), fCx, baseY - fBh - 6);
          if (typeof d.nowcast === 'number' && Math.abs(d.nowcast - d.forecast) >= 0.05) {
            const nY = baseY - Math.max(3, (d.nowcast / maxV) * plotH);
            ctx.save();
            ctx.strokeStyle = '#ff9f0a'; ctx.lineWidth = 2; ctx.setLineDash([5, 3]);
            ctx.beginPath(); ctx.moveTo(fCx - barW / 2 - 4, nY); ctx.lineTo(fCx + barW / 2 + 4, nY); ctx.stroke();
            ctx.restore();
            ctx.fillStyle = '#ff9f0a'; ctx.font = 'bold 11px -apple-system, sans-serif';
            ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
            ctx.fillText('≈' + d.nowcast.toFixed(1), fCx + barW / 2 + 8, nY);
            ctx.textAlign = 'center';
          }
        } else if (hasActual) {
          const bh = Math.max(3, (d.actual / maxV) * plotH);
          const grad = ctx.createLinearGradient(0, baseY - bh, 0, baseY);
          grad.addColorStop(0, COLORS.actualLight);
          grad.addColorStop(1, COLORS.actual);
          ctx.fillStyle = grad;
          this._roundRect(ctx, cx - barW / 2, baseY - bh, barW, bh, 6);
          ctx.fill();
          ctx.fillStyle = TC('text');
          ctx.font = 'bold 14px -apple-system, sans-serif';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'bottom';
          ctx.fillText(d.actual.toFixed(1), cx, baseY - bh - 6);
        } else if (hasForecast) {
          const bh = Math.max(3, (d.forecast / maxV) * plotH);
          const grad = ctx.createLinearGradient(0, baseY - bh, 0, baseY);
          grad.addColorStop(0, COLORS.tomorrow);
          grad.addColorStop(1, COLORS.tomorrowDark);
          ctx.fillStyle = grad;
          this._roundRect(ctx, cx - barW / 2, baseY - bh, barW, bh, 6);
          ctx.fill();
          ctx.fillStyle = COLORS.tomorrow;
          ctx.font = 'bold 14px -apple-system, sans-serif';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'bottom';
          ctx.fillText(d.forecast.toFixed(1), cx, baseY - bh - 6);
        }

        const mainLabel = d.label === 'Wczoraj' ? 'WCZORAJ' : d.label === 'Dziś' ? 'DZIŚ' : 'JUTRO';
        ctx.fillStyle = isTomorrow ? COLORS.tomorrow : TC('text2');
        ctx.font = 'bold 12px -apple-system, sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.fillText(mainLabel, cx, baseY + 8);

        const dd = d.date ? new Date(d.date + 'T12:00:00') : null;
        const dateTxt = dd ? dd.toLocaleDateString('pl-PL', { day: 'numeric', month: 'short' }) : '';
        ctx.fillStyle = TC('muted');
        ctx.font = '11px -apple-system, sans-serif';
        ctx.fillText(dateTxt, cx, baseY + 24);

        if (isTomorrow && confidence) {
          const rangeTxt = `${(confidence.low || 0).toFixed(1)}–${(confidence.high || 0).toFixed(1)}`;
          ctx.fillStyle = 'rgba(251,191,36,0.7)';
          ctx.font = '10px -apple-system, sans-serif';
          ctx.fillText(`±${(confidence.sigma || 0).toFixed(1)}  (${rangeTxt})`, cx, baseY + 38);
        }
      });
    }

    // ===== PROGNOZA 7-DNIOWA =====
    _renderForecast7dChart() {
      const canvas = this._el('chartForecast7d');
      if (!canvas) return;
      const st = this._hass.states['sensor.bms_load_forecast'];
      const forecast7d = st && st.attributes && Array.isArray(st.attributes.forecast_7d) ? st.attributes.forecast_7d : null;

      if (!forecast7d || forecast7d.length === 0 || !forecast7d.some(d => typeof d.forecast === 'number')) {
        const parent = canvas.parentElement;
        if (parent && !parent.querySelector('.chart-empty')) {
          canvas.style.display = 'none';
          const m = document.createElement('div');
          m.className = 'chart-empty';
          m.textContent = 'Prognoza 7-dniowa będzie dostępna po zebraniu historii.';
          parent.insertBefore(m, canvas.nextSibling);
        }
        return;
      }
      canvas.style.display = 'block';
      const emptyMsg = canvas.parentElement && canvas.parentElement.querySelector('.chart-empty');
      if (emptyMsg) emptyMsg.remove();

      const key = JSON.stringify(forecast7d);
      if (this._lastForecast7dKey === key) return;
      this._lastForecast7dKey = key;

      this._drawForecast7dChart(canvas, forecast7d);
    }

    _drawForecast7dChart(canvas, forecast7d) {
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.clientWidth || 400;
      const h = canvas.clientHeight || 260;
      if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
        canvas.width = Math.round(w * dpr);
        canvas.height = Math.round(h * dpr);
      }
      const ctx = canvas.getContext('2d');
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      const padL = 44, padR = 14, padT = 24, padB = 44;
      const plotW = w - padL - padR;
      const plotH = h - padT - padB;

      const vals = forecast7d.filter(d => typeof d.forecast === 'number').map(d => d.forecast);
      if (!vals.length) return;
      let maxV = Math.max(...vals) * 1.2;
      if (maxV <= 0) maxV = 1;

      ctx.strokeStyle = TC('grid');
      ctx.lineWidth = 1;
      for (let g = 0; g <= 4; g++) {
        const y = padT + (g / 4) * plotH;
        ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(w - padR, y); ctx.stroke();
      }

      ctx.fillStyle = TC('muted');
      ctx.font = '10px -apple-system, sans-serif';
      ctx.textAlign = 'right';
      ctx.textBaseline = 'middle';
      for (let g = 0; g <= 4; g++) {
        const val = maxV - (g / 4) * maxV;
        const y = padT + (g / 4) * plotH;
        ctx.fillText(val.toFixed(0), padL - 6, y);
      }

      ctx.save();
      ctx.translate(12, padT + plotH / 2);
      ctx.rotate(-Math.PI / 2);
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = TC('muted');
      ctx.font = 'bold 10px -apple-system, sans-serif';
      ctx.fillText('kWh', 0, 0);
      ctx.restore();

      const n = forecast7d.length;
      const slotW = plotW / n;
      const barW = Math.min(slotW * 0.6, 48);
      const baseY = padT + plotH;
      const tomorrow = this._tomorrowKey();
      const tipR = canvas._tipR = [];

      forecast7d.forEach((d, i) => {
        const cx = padL + (i + 0.5) * slotW;
        const dateStr = d.date || '';
        const isTomorrow = dateStr === tomorrow;
        if (dateStr) {
          const wdn = new Date(dateStr + 'T12:00:00').toLocaleDateString('pl-PL', { weekday: 'long' });
          tipR.push({ x: padL + i * slotW, y: padT, w: slotW, h: plotH + padB, text: `${wdn} ${dateStr.slice(8, 10)}.${dateStr.slice(5, 7)}\nPrognoza: ${typeof d.forecast === 'number' ? d.forecast.toFixed(1).replace('.', ',') + ' kWh' : '—'}` });
        }

        if (typeof d.forecast === 'number' && d.forecast > 0) {
          const bh = Math.max(3, (d.forecast / maxV) * plotH);
          const grad = ctx.createLinearGradient(0, baseY - bh, 0, baseY);
          if (isTomorrow) {
            grad.addColorStop(0, COLORS.tomorrow);
            grad.addColorStop(1, COLORS.tomorrowDark);
          } else {
            grad.addColorStop(0, COLORS.forecast);
            grad.addColorStop(1, COLORS.forecastDark);
          }
          ctx.fillStyle = grad;
          this._roundRect(ctx, cx - barW / 2, baseY - bh, barW, bh, 5);
          ctx.fill();
          ctx.fillStyle = isTomorrow ? COLORS.tomorrow : TC('text');
          ctx.font = 'bold 12px -apple-system, sans-serif';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'bottom';
          ctx.fillText(d.forecast.toFixed(1), cx, baseY - bh - 5);
        }

        const dd = dateStr ? new Date(dateStr + 'T12:00:00') : null;
        if (dd) {
          const weekday = dd.toLocaleDateString('pl-PL', { weekday: 'short' }).toUpperCase();
          const dayNum = dd.getDate();
          const month = dd.toLocaleDateString('pl-PL', { month: 'short' });
          ctx.fillStyle = isTomorrow ? COLORS.tomorrow : TC('text2');
          ctx.font = 'bold 12px -apple-system, sans-serif';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'top';
          ctx.fillText(weekday, cx, baseY + 8);
          ctx.fillStyle = TC('muted');
          ctx.font = '10px -apple-system, sans-serif';
          ctx.fillText(`${dayNum} ${month}`, cx, baseY + 24);
        }
      });
    }

    // ===== PROFIL GODZINOWY: DZIŚ (prognoza + linia rzeczywista) i JUTRO (sama prognoza) =====
    _renderHourlyForecastChart() {
      this._safe(() => this._renderHourlyBlock('today'));
      this._safe(() => this._renderHourlyBlock('tomorrow'));
    }

    _renderHourlyBlock(kind) {
      const isToday = kind === 'today';
      const canvas = this._el(isToday ? 'chartHourlyToday' : 'chartHourlyFc');
      if (!canvas) return;
      const st = this._hass.states['sensor.bms_load_forecast'];
      const at = st && st.attributes ? st.attributes : {};
      const num = (v) => (typeof v === 'number' && isFinite(v) && v >= 0 ? v : null);
      const to24 = (arr) => { const o = []; for (let i = 0; i < 24; i++) o.push(num(arr[i])); return o; };
      const fAttr = isToday ? at.hourly_forecast_today : at.hourly_forecast;
      const forecast = Array.isArray(fAttr) && fAttr.length ? to24(fAttr) : null;
      const actual0 = isToday && Array.isArray(at.hourly_today) && at.hourly_today.length ? to24(at.hourly_today) : null;
      const actual = actual0 && actual0.some(v => v !== null) ? actual0 : null;
      const nowHour = isToday && Number.isInteger(at.hourly_today_hour) && at.hourly_today_hour >= 0 && at.hourly_today_hour <= 23 ? at.hourly_today_hour : null;
      const profilesDays = at.profiles_days || 0;
      const historyDays = at.history_days || 0;
      const tbl = this._el(isToday ? 'hourlyTodayTable' : 'hourlyFcTable');
      const leg = this._el(isToday ? 'hfcLegActual' : null);
      const tag = isToday ? 'dziś' : 'jutro';

      // reset pamięci podręcznej (zmiana motywu / zakładki / rozmiaru) — jedna flaga dla obu wykresów
      if (this._lastHourlyFcKey === null || !this._hfcKeys) { this._hfcKeys = {}; this._lastHourlyFcKey = 'ok'; }

      if (!forecast || !forecast.some(v => v !== null && v > 0)) {
        const parent = canvas.parentElement;
        let empty = parent && parent.querySelector('.chart-empty');
        if (!empty && parent) {
          canvas.style.display = 'none';
          empty = document.createElement('div');
          empty.className = 'chart-empty';
          parent.insertBefore(empty, canvas.nextSibling);
        }
        if (tbl) tbl.style.display = 'none';
        if (empty) {
          canvas.style.display = 'none';
          const src = `<code>${this._hass.states[this._inv('sensor', 'load_power')] ? this._inv('sensor', 'load_power') : this._eid('sensor', 'load_power')}</code>`;
          if (profilesDays < 3) {
            empty.innerHTML = `Profil godzinowy: <b>${profilesDays}/3 dni</b> zebranych.<br>
              Wymaga ${src} dostępnego przez 3 pełne dni.<br>
              (Historia dzienna: ${historyDays} dni)`;
          } else {
            empty.innerHTML = `Profil godzinowy: ${profilesDays} dni — brak danych w atrybucie ${isToday ? 'hourly_forecast_today' : 'hourly_forecast'}.<br>
              Sprawdź czy ${src} ma dane.`;
          }
        }
        this._hfcKeys[kind] = null;
        return;
      }
      canvas.style.display = 'block';
      if (tbl) tbl.style.display = '';
      const emptyMsg = canvas.parentElement && canvas.parentElement.querySelector('.chart-empty');
      if (emptyMsg) emptyMsg.remove();

      const w = canvas.clientWidth || 400;
      const key = JSON.stringify([forecast, actual, nowHour, Math.round(w), THEME.mode]);
      if (this._hfcKeys[kind] === key) return;
      this._hfcKeys[kind] = key;

      const sum = (xs) => xs.reduce((a, c) => a + (c || 0), 0);
      const fSum = sum(forecast);
      const subEl = this._el(isToday ? 'hourlyTodaySub' : 'hourlyFcSub');
      if (subEl) {
        if (!isToday) {
          subEl.textContent = `Jutro: ${fSum.toFixed(1)} kWh`;
        } else if (actual) {
          const idx = []; actual.forEach((v, i) => { if (v !== null) idx.push(i); });
          const aSum = idx.reduce((a, i) => a + actual[i], 0);
          const fSame = idx.reduce((a, i) => a + (forecast[i] || 0), 0);     // prognoza dla tych samych godzin
          const lastDone = idx[idx.length - 1];
          const full = nowHour !== null ? idx.length === nowHour : idx.length === lastDone + 1;
          const upto = nowHour !== null ? nowHour : lastDone + 1;
          subEl.textContent = (full ? `Dziś do ${String(upto).padStart(2, '0')}:00` : `Dziś (${idx.length} godz. z pomiarem)`)
            + `: ${aSum.toFixed(1)} kWh (prognoza ${fSame.toFixed(1)}) · cały dzień: prognoza ${fSum.toFixed(1)} kWh`;
        } else {
          subEl.textContent = `Dziś: prognoza ${fSum.toFixed(1)} kWh`;
        }
      }
      if (leg) leg.style.display = actual ? '' : 'none';
      const peakMax = Math.max(...forecast.filter(v => v !== null));
      const peakIdx = forecast.indexOf(peakMax);
      canvas.setAttribute('role', 'img');
      canvas.setAttribute('aria-label', `Prognoza zużycia na ${tag} godzina po godzinie, razem ${fSum.toFixed(1)} kWh, szczyt o ${String(peakIdx).padStart(2, '0')}:00 (${Math.round(peakMax * 1000)} Wh)${actual ? '; linia pokazuje rzeczywiste zużycie dziś' : ''}`);

      this._drawHourlyForecastChart(canvas, forecast, actual, nowHour);
      if (tbl) this._renderHfcTable(tbl, forecast, actual, nowHour, peakMax, w, isToday ? 'Prog.' : 'Jutro');
    }

    // „ładny” krok osi: 1, 2 lub 5 × 10^k
    _niceStep(x) {
      if (!(x > 0) || !isFinite(x)) return 0.1;
      const p = Math.pow(10, Math.floor(Math.log10(x)));
      const f = x / p;
      return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p;
    }

    _drawHourlyForecastChart(canvas, tomorrow, today, nowHour) {      // „tomorrow” = słupki prognozy (dziś lub jutro), „today” = linia rzeczywista albo null
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.clientWidth || 400;
      const h = canvas.clientHeight || 200;
      if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
        canvas.width = Math.round(w * dpr);
        canvas.height = Math.round(h * dpr);
      }
      const ctx = canvas.getContext('2d');
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      const light = THEME.mode === 'light';
      const padL = 46, padR = 12, padB = 22;     // padL/padR takie same jak w tabeli pod wykresem
      // wartości (Wh, jak w tabeli) nad słupkami, jak na wykresie 7-dniowym: poziomo, gdy mieszczą się w kolumnie, inaczej pionowo
      const whOf = (v) => Math.round(v * 100) * 10;
      const LBL_FONT = 'bold 10px -apple-system, sans-serif';
      const lblDigits = Math.max(3, ...tomorrow.filter(v => v !== null).map(v => String(whOf(v)).length));
      ctx.font = LBL_FONT;
      const lblW = ctx.measureText('0'.repeat(lblDigits)).width;
      const lblHoriz = lblW + 3 <= (w - padL - padR) / 24;
      const padT = 18 + (lblHoriz ? 14 : Math.ceil(lblW) + 6);   // miejsce na napisy nad najwyższym słupkiem i na „teraz”
      const plotW = w - padL - padR;
      const plotH = h - padT - padB;
      const baseY = padT + plotH;
      const groupW = plotW / 24;
      const tipR = canvas._tipR = [];
      for (let i = 0; i < 24; i++) {
        const fmt = (v) => (typeof v === 'number' ? String(Math.round(v * 1000)) + ' Wh' : '—');
        const hh = (n) => String(n % 24).padStart(2, '0');
        const lines = [`${hh(i)}:00–${hh(i + 1)}:00`, 'Prognoza: ' + fmt(tomorrow[i])];
        if (today && today[i] !== null && today[i] !== undefined) lines.push('Rzeczywiste: ' + fmt(today[i]));
        tipR.push({ x: padL + i * groupW, y: 0, w: groupW, h: h, text: lines.join('\n') });
      }

      const nums = tomorrow.concat(today || []).filter(v => v !== null);
      if (!nums.length || plotW <= 0 || plotH <= 0) return;
      const rawMax = Math.max(...nums, 0.01);
      const step = this._niceStep(rawMax * 1.06 / 4);
      const nTicks = Math.max(1, Math.ceil(rawMax * 1.02 / step - 1e-9));
      const axisMax = step * nTicks;
      const dec = step >= 1 ? 0 : (step >= 0.1 ? 1 : 2);
      const yOf = (v) => baseY - Math.min(1, v / axisMax) * plotH;

      // bieżąca godzina (tylko gdy jest linia „dziś”)
      if (today && nowHour !== null) {
        ctx.fillStyle = TC('night');
        ctx.fillRect(padL + nowHour * groupW, padT, groupW, plotH);
      }

      ctx.lineWidth = 1;
      ctx.font = '10px -apple-system, sans-serif';
      ctx.textAlign = 'right';
      ctx.textBaseline = 'middle';
      for (let t = 0; t <= nTicks; t++) {
        const y = Math.round(yOf(t * step)) + 0.5;
        ctx.strokeStyle = t === 0 ? TC('line') : TC('grid');
        ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(w - padR, y); ctx.stroke();
        ctx.fillStyle = TC('muted');
        ctx.fillText((t * step).toFixed(dec), padL - 6, y);
      }

      // słupki: prognoza na jutro
      const realMax = Math.max(...tomorrow.filter(v => v !== null));
      const barW = Math.max(3, Math.min(groupW * 0.62, 24));
      for (let i = 0; i < 24; i++) {
        const v = tomorrow[i];
        if (v === null) continue;
        const bh = Math.max(2, baseY - yOf(v));
        const cx = padL + (i + 0.5) * groupW;
        const isPeak = v >= realMax * 0.7;
        const grad = ctx.createLinearGradient(0, baseY - bh, 0, baseY);
        grad.addColorStop(0, isPeak ? COLORS.tomorrow : COLORS.forecast);
        grad.addColorStop(1, isPeak ? COLORS.tomorrowDark : COLORS.forecastDark);
        ctx.fillStyle = grad;
        this._roundRect(ctx, cx - barW / 2, baseY - bh, barW, bh, 3);
        ctx.fill();
      }

      // wartości nad słupkami (pod linią „dziś”, żeby kropki rzeczywistego zużycia zawsze były w pełni widoczne; obwódka w kolorze tła)
      {
        const hl = light ? 'rgba(255,255,255,0.9)' : 'rgba(0,0,0,0.6)';
        ctx.font = LBL_FONT;
        ctx.lineJoin = 'round';
        ctx.lineWidth = 3;
        for (let i = 0; i < 24; i++) {
          const v = tomorrow[i];
          if (v === null) continue;
          const cx = padL + (i + 0.5) * groupW;
          const topY = baseY - Math.max(2, baseY - yOf(v)) - 3;
          const isPeak = v >= realMax * 0.7;
          ctx.fillStyle = isPeak ? (light ? '#b45309' : COLORS.tomorrow) : TC('text');
          ctx.strokeStyle = hl;
          const txt = String(whOf(v));
          if (lblHoriz) {
            ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
            ctx.strokeText(txt, cx, topY); ctx.fillText(txt, cx, topY);
          } else {
            ctx.save();
            ctx.translate(cx, topY); ctx.rotate(-Math.PI / 2);
            ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
            ctx.strokeText(txt, 0, 0); ctx.fillText(txt, 0, 0);
            ctx.restore();
          }
        }
      }

      // linia „dziś” — rzeczywiste zużycie zakończonych godzin; przerwa tam, gdzie brak pomiaru
      if (today) {
        const col = light ? '#059669' : '#6ee7b7';
        const halo = light ? 'rgba(255,255,255,0.85)' : 'rgba(0,0,0,0.55)';
        const pts = today.map((v, i) => (v === null ? null : { x: padL + (i + 0.5) * groupW, y: yOf(v) }));
        const segs = [];
        let cur = [];
        pts.forEach((p) => { if (p) cur.push(p); else { if (cur.length) segs.push(cur); cur = []; } });
        if (cur.length) segs.push(cur);
        ctx.lineJoin = 'round';
        ctx.lineCap = 'round';
        [[halo, 5], [col, 2.5]].forEach(([c, lw]) => {
          ctx.strokeStyle = c;
          ctx.lineWidth = lw;
          segs.forEach((s) => {
            if (s.length < 2) return;
            ctx.beginPath();
            s.forEach((p, k) => (k ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
            ctx.stroke();
          });
        });
        const r = groupW >= 16 ? 3.5 : 2.5;
        pts.forEach((p) => {
          if (!p) return;
          ctx.fillStyle = halo;
          ctx.beginPath(); ctx.arc(p.x, p.y, r + 1.5, 0, Math.PI * 2); ctx.fill();
          ctx.fillStyle = col;
          ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, Math.PI * 2); ctx.fill();
        });
        if (nowHour !== null) {
          ctx.font = '9px -apple-system, sans-serif';
          ctx.textBaseline = 'bottom';
          const tw = ctx.measureText('teraz').width;
          const cxn = Math.min(w - padR - tw / 2, Math.max(padL + tw / 2, padL + (nowHour + 0.5) * groupW));
          ctx.textAlign = 'center';
          ctx.fillStyle = TC('muted');
          ctx.fillText('teraz', cxn, padT - 3);
        }
      }

      // oś godzin: co 1 h na szerokim ekranie, co 2–3 h na wąskim
      const every = groupW >= 20 ? 1 : (groupW >= 13 ? 2 : 3);
      ctx.font = '10px -apple-system, sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      for (let i = 0; i < 24; i += every) {
        const isNow = today && nowHour === i;
        ctx.fillStyle = isNow ? TC('text') : TC('muted');
        ctx.font = (isNow ? 'bold ' : '') + '10px -apple-system, sans-serif';
        ctx.fillText(String(i).padStart(2, '0'), padL + (i + 0.5) * groupW, baseY + 6);
      }
    }

    // Tabela godzin pod wykresem (Wh). Układ zależy od szerokości i najdłuższej wartości, tak by nic się nie ucinało:
    // 24 kolumny (pod słupkami) → 2 bloki po 12 → 3 bloki po 8; czcionka 11 → 10 → 9 px.
    _renderHfcTable(el, tomorrow, today, nowHour, peakMax, w, fLabel) {
      const wh = (v) => Math.round(v * 100) * 10;
      const pad2 = (n) => String(n).padStart(2, '0');
      const sgn = (d) => (d > 0 ? '+' + d : d < 0 ? '\u2212' + Math.abs(d) : '0');
      const jutro = tomorrow.map(v => (v === null ? '–' : String(wh(v))));
      const dzis = today ? today.map(v => (v === null ? '·' : String(wh(v)))) : null;
      const roznica = today ? today.map((v, i) => (v === null || tomorrow[i] === null ? '' : sgn(wh(v) - wh(tomorrow[i])))) : null;
      const maxLen = Math.max(2, ...jutro.map(t => t.length), ...(dzis || []).map(t => t.length), ...(roznica || []).map(t => t.length));
      const labelW = 46, rightPad = 12;
      const layouts = [[24, 11], [12, 11], [12, 10], [12, 9], [8, 10], [8, 9]];
      let lay = layouts[layouts.length - 1];
      for (const L of layouts) {
        if (maxLen * 0.62 * L[1] + 4 <= (w - labelW - rightPad) / L[0]) { lay = L; break; }
      }
      const [per, fs] = lay;
      let html = '<div class="hfc-cap">Zużycie w Wh na godzinę</div>';
      for (let a = 0; a < 24; a += per) {
        const idx = []; for (let i = a; i < a + per; i++) idx.push(i);
        const row = (label, fn, cls) => `<div class="l ${cls || ''}">${label}</div>` + idx.map(fn).join('');
        let rows = row('Godz.', (i) => `<div class="h${today && i === nowHour ? ' now' : ''}">${pad2(i)}</div>`, 'h');
        rows += row(fLabel, (i) => `<div class="${tomorrow[i] !== null && tomorrow[i] >= peakMax * 0.7 ? 'pk' : ''}">${jutro[i]}</div>`);
        if (today && idx.some(i => today[i] !== null)) {      // blok bez żadnych danych z dziś: bez pustych wierszy
          rows += row('Rzecz.', (i) => `<div class="td">${dzis[i]}</div>`);
          rows += row('Różn.', (i) => {
            const t = roznica[i];
            return t === '' ? '<div></div>' : `<div class="${t[0] === '+' ? 'up' : t[0] === '\u2212' ? 'dn' : ''}">${t}</div>`;
          });
        }
        html += `<div class="hfc-tbl" style="grid-template-columns:${labelW}px repeat(${per},minmax(0,1fr));font-size:${fs}px">${rows}</div>`;
      }
      el.innerHTML = html;
    }

    // ===== PRODUKCJA PV DZIŚ =====
    // --- wybór przedziału wykresu produkcji PV: wczoraj / dziś / jutro / data / 7 / 30 dni
    _pvSelGet() {
      if (!this._pvSel) { let v = null; try { v = localStorage.getItem('bms_pv_sel'); } catch (e) { v = null; } this._pvSel = v && /^(today|yesterday|tomorrow|r7|r30|\d{4}-\d{2}-\d{2})$/.test(v) ? v : 'today'; }
      return this._pvSel;
    }
    _pvDayOf(sel) {
      const d = new Date(); d.setHours(12, 0, 0, 0);
      if (sel === 'yesterday') d.setDate(d.getDate() - 1);
      else if (sel === 'tomorrow') d.setDate(d.getDate() + 1);
      else if (/^\d{4}-/.test(sel)) return sel;
      const p = (n) => String(n).padStart(2, '0');
      return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
    }
    _pvSelSet(sel) {
      this._pvSel = sel; this._lastPvProdKey = null;
      try { localStorage.setItem('bms_pv_sel', sel); } catch (e) { /* storage niedostępny */ }
      this._renderPvProductionChart();
    }
    _pvBarSync() {
      const bar = this._el('pvRangeBar'); if (!bar) return;
      const sel = this._pvSelGet();
      if (!bar._bound) {
        bar._bound = true;
        bar.addEventListener('click', (ev) => {
          const b = ev.target && ev.target.closest ? ev.target.closest('[data-pvr]') : null; if (!b) return;
          const k = b.dataset.pvr, cur = this._pvSelGet();
          if (k === '7' || k === '30') return this._pvSelSet('r' + k);
          if (k === 'prev' || k === 'next') {
            const step = k === 'prev' ? -1 : 1;
            if (cur === 'r7' || cur === 'r30') return;   // zakres liczy się zawsze do wczoraj
            const dd = new Date(this._pvDayOf(cur) + 'T12:00:00'); dd.setDate(dd.getDate() + step);
            const p = (n) => String(n).padStart(2, '0');
            const iso = `${dd.getFullYear()}-${p(dd.getMonth() + 1)}-${p(dd.getDate())}`;
            const t = new Date(); t.setHours(12, 0, 0, 0); const lim = new Date(t); lim.setDate(lim.getDate() + 1);
            if (dd > lim) return;
            return this._pvSelSet(iso === this._pvDayOf('today') ? 'today' : iso === this._pvDayOf('yesterday') ? 'yesterday' : iso === this._pvDayOf('tomorrow') ? 'tomorrow' : iso);
          }
          this._pvSelSet(k);
        });
        const di = bar.querySelector('#pvDate');
        if (di) di.addEventListener('change', () => { if (di.value) this._pvSelSet(di.value); });
      }
      const day = this._pvDayOf(sel);
      bar.querySelectorAll('[data-pvr]').forEach((b) => {
        const k = b.dataset.pvr;
        const on = k === sel || (k === '7' && sel === 'r7') || (k === '30' && sel === 'r30');
        b.style.opacity = on ? '1' : '.65'; b.style.outline = on ? '2px solid var(--accent,#60a5fa)' : 'none';
      });
      const di = bar.querySelector('#pvDate'); if (di && di.value !== (sel === 'r7' || sel === 'r30' ? '' : day)) di.value = (sel === 'r7' || sel === 'r30') ? '' : day;
    }
    _renderPvOther(sel) {
      const canvas = this._el('chartPvProd24h'); if (!canvas || !this._hass) return;
      const range = sel === 'r7' || sel === 'r30';
      const key = range ? sel : this._pvDayOf(sel);
      const title = this._el('pvProdTitle');
      if (title) title.textContent = range ? `Produkcja PV — ostatnie ${sel === 'r7' ? 7 : 30} dni, rzeczywista vs prognoza (kWh/dzień)` : `Produkcja PV ${sel === 'yesterday' ? 'wczoraj' : sel === 'tomorrow' ? 'jutro' : key} — rzeczywista vs prognoza (kWh/h)`;
      const cache = this._pvCache || (this._pvCache = {});
      const cached = cache[key];
      const fresh = cached && Date.now() - cached.at < 60000;
      if (!fresh && !(this._pvFetching === key)) {
        this._pvFetching = key;
        const data = range ? { mode: 'range', days: sel === 'r7' ? 7 : 30 } : { mode: 'day', date: key };
        Promise.resolve(this._hass.callWS({ type: 'call_service', domain: 'bms_komp_dec', service: 'pv_chart_get', service_data: data, return_response: true }))
          .then((r) => { cache[key] = { at: Date.now(), res: (r && r.response !== undefined ? r.response : r) || {} }; })
          .catch(() => { cache[key] = { at: Date.now(), res: { error: true } }; })
          .then(() => { this._pvFetching = null; if (this._pvSelGet() === sel) this._renderPvOther(sel); });
      }
      const res = cached ? cached.res : null;
      const sub = this._el('pvProdSub'), parent = canvas.parentElement;
      const oldNote = parent && parent.querySelector('.chart-note'); if (oldNote) oldNote.remove();
      const emp = parent && parent.querySelector('.chart-empty'); if (emp) emp.remove();
      const showMsg = (txt) => { canvas.style.display = 'none'; const m = document.createElement('div'); m.className = 'chart-empty'; m.textContent = txt; parent.appendChild(m); };
      if (!res) { if (sub) sub.textContent = 'ładowanie…'; return; }
      if (res.error) { if (sub) sub.textContent = '—'; return showMsg('Nie udało się wczytać danych.'); }
      const f1 = (v) => (typeof v === 'number' ? v.toFixed(1).replace('.', ',') : '—');
      if (range) {
        const rows = Array.isArray(res.rows) ? res.rows : [];
        if (sub) sub.textContent = `Rzeczywista: ${f1(res.sum_act)} kWh · Prognoza: ${f1(res.sum_fc)} kWh` + (res.err_pct != null ? ` · błąd prognozy ${f1(res.err_pct)}%` : '');
        if (!rows.some((r) => r.pv_act != null || r.pv_fc != null)) return showMsg('Brak zapisanych danych z tego okresu.');
        canvas.style.display = 'block';
        this._drawPvDailyChart(canvas, rows);
        return;
      }
      if (sub) sub.textContent = [res.sum_act != null ? `Rzeczywista: ${f1(res.sum_act)} kWh` : null, res.sum_fc != null ? `Prognoza: ${f1(res.sum_fc)} kWh` : null].filter(Boolean).join(' · ') || '—';
      if (!res.actual && !res.forecast) return showMsg(res.note || 'Brak danych z tego dnia.');
      canvas.style.display = 'block';
      this._drawPvProductionChart(canvas, res.actual || null, res.forecast || null, false);
      if (res.note) { const n = document.createElement('div'); n.className = 'chart-note'; n.textContent = res.note; canvas.parentElement.insertBefore(n, canvas.nextSibling); }
    }
    _drawPvDailyChart(canvas, rows) {
      const dpr = window.devicePixelRatio || 1, w = canvas.clientWidth || 400, h = canvas.clientHeight || 280;
      if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) { canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr); }
      const ctx = canvas.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
      const padL = 40, padR = 10, padT = 14, padB = 30, plotW = w - padL - padR, plotH = h - padT - padB, n = rows.length;
      const vals = []; rows.forEach((r) => { if (typeof r.pv_act === 'number') vals.push(r.pv_act); if (typeof r.pv_fc === 'number') vals.push(r.pv_fc); });
      const maxV = (Math.max(1, ...vals)) * 1.1;
      ctx.strokeStyle = TC('grid'); ctx.lineWidth = 1;
      for (let g = 0; g <= 4; g++) { const y = padT + (g / 4) * plotH; ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(w - padR, y); ctx.stroke(); }
      ctx.fillStyle = TC('muted'); ctx.font = '10px -apple-system, sans-serif'; ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
      for (let g = 0; g <= 4; g++) ctx.fillText((maxV - (g / 4) * maxV).toFixed(0), padL - 4, padT + (g / 4) * plotH);
      const groupW = plotW / n, barW = Math.max(2, Math.min(18, groupW * 0.4)), baseY = padT + plotH;
      const tipR = canvas._tipR = [];
      rows.forEach((r, i) => {
        const cx = padL + (i + 0.5) * groupW;
        const bar = (v, x, c0, c1) => { if (typeof v !== 'number') return; const bh = Math.max(2, (v / maxV) * plotH); const gr = ctx.createLinearGradient(0, baseY - bh, 0, baseY); gr.addColorStop(0, c0); gr.addColorStop(1, c1); ctx.fillStyle = gr; this._roundRect(ctx, x, baseY - bh, barW, bh, 2); ctx.fill(); };
        bar(r.pv_act, cx - barW - 1, COLORS.pv, '#d97706'); bar(r.pv_fc, cx + 1, 'rgba(96,165,250,0.75)', 'rgba(37,99,235,0.75)');
        const fmt = (v) => (typeof v === 'number' ? v.toFixed(1).replace('.', ',') + ' kWh' : '—');
        tipR.push({ x: padL + i * groupW, y: 0, w: groupW, h: h, text: [r.date, 'Wykonanie: ' + fmt(r.pv_act), 'Prognoza: ' + fmt(r.pv_fc)].join('\n') });
      });
      ctx.fillStyle = TC('muted'); ctx.font = '10px -apple-system, sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'top';
      const step = Math.max(1, Math.ceil(n / (w < 380 ? 5 : 8)));
      rows.forEach((r, i) => { if (i % step === 0) ctx.fillText(r.date.slice(8, 10) + '.' + r.date.slice(5, 7), padL + (i + 0.5) * groupW, baseY + 6); });
      ctx.font = '11px -apple-system, sans-serif'; ctx.textAlign = 'left'; ctx.textBaseline = 'middle'; const lY = h - 7;
      ctx.fillStyle = COLORS.pv; ctx.fillRect(padL, lY - 5, 10, 10); ctx.fillStyle = TC('text2'); ctx.fillText('rzeczywista', padL + 14, lY);
      ctx.fillStyle = 'rgba(96,165,250,0.75)'; ctx.fillRect(padL + 100, lY - 5, 10, 10); ctx.fillStyle = TC('text2'); ctx.fillText('prognoza', padL + 114, lY);
    }

    _renderPvProductionChart() {
      const canvas = this._el('chartPvProd24h');
      if (canvas) {
        this._pvBarSync();
        const sel = this._pvSelGet();
        if (sel !== 'today') { this._renderPvOther(sel); return; }
        const tt = this._el('pvProdTitle'); if (tt) tt.textContent = 'Produkcja PV dziś — rzeczywista vs prognoza (kWh/h)';
        canvas.style.display = '';
      }
      if (!canvas || !this._history24h) return;
      const { dayStart, historyArr } = this._history24h;
      const actual = this._processEnergyHistoryToHourly(historyArr || [], dayStart);
      const forecast = this._getPvForecastHourly();

      const actualSum = (actual || []).filter(v => v !== null).reduce((a, c) => a + c, 0);
      const forecastSum = (forecast || []).filter(v => v !== null).reduce((a, c) => a + c, 0);
      const actualHasAny = actual && actual.some(v => v !== null && v > 0);

      const subEl = this._el('pvProdSub');
      if (subEl) {
        const parts = [];
        if (actual) parts.push(`Rzeczywista: ${actualSum.toFixed(1)} kWh`);
        if (forecast) parts.push(`Prognoza: ${forecastSum.toFixed(1)} kWh`);
        subEl.textContent = parts.join(' · ') || '—';
      }

      const parent = canvas.parentElement;
      let existingNote = parent && parent.querySelector('.chart-note');
      if (existingNote) existingNote.remove();

      if (!actualHasAny && forecastSum > 0.1 && parent) {
        const sourceEid = this._inv('sensor', 'today_production');
        const srcSt = this._hass.states[sourceEid];
        const srcVal = srcSt ? parseFloat(srcSt.state) : NaN;
        const ourSt = this._hass.states[this._eid('sensor', 'energy_pv_today')];
        const ourVal = ourSt ? parseFloat(ourSt.state) : NaN;
        let noteText = '';
        if (!isNaN(srcVal) && srcVal > 0.1) {
          noteText = `⚠️ Źródło (${sourceEid}) ma ${srcVal.toFixed(2)} kWh, ale historia pusta. `
                   + `Sprawdź <code>recorder:</code> w configuration.yaml i czy encja jest rejestrowana.`;
        } else if (!isNaN(ourVal) && ourVal > 0.1) {
          noteText = `⚠️ Sensor EMS ma ${ourVal.toFixed(2)} kWh, ale historia pusta. `
                   + `Prawdopodobnie recorder jeszcze nie zapisał próbek — poczekaj kilka minut.`;
        } else {
          noteText = `Brak rzeczywistej produkcji dziś (może być 0 kWh jeśli PV nie pracowało).`;
        }
        if (noteText) {
          const note = document.createElement('div');
          note.className = 'chart-note';
          note.innerHTML = noteText;
          canvas.parentElement.insertBefore(note, canvas.nextSibling);
        }
      }

      const key = JSON.stringify({ a: actual, f: forecast });
      if (this._lastPvProdKey === key) return;
      this._lastPvProdKey = key;

      if (!actualHasAny && !forecast) {
        if (parent && !parent.querySelector('.chart-empty')) {
          canvas.style.display = 'none';
          const m = document.createElement('div');
          m.className = 'chart-empty';
          m.textContent = 'Brak danych — historia lub prognoza PV niedostępna.';
          parent.appendChild(m);
        }
        return;
      }
      canvas.style.display = 'block';
      const emptyMsg = canvas.parentElement && canvas.parentElement.querySelector('.chart-empty');
      if (emptyMsg) emptyMsg.remove();

      this._drawPvProductionChart(canvas, actual, forecast);
    }

    _drawPvProductionChart(canvas, actual, forecast, isToday = true) {
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.clientWidth || 400;
      const h = canvas.clientHeight || 280;
      if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
        canvas.width = Math.round(w * dpr);
        canvas.height = Math.round(h * dpr);
      }
      const ctx = canvas.getContext('2d');
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      const padL = 40, padR = 10, padT = 14, padB = 30;
      const plotW = w - padL - padR;
      const plotH = h - padT - padB;

      const all = [];
      for (let i = 0; i < 24; i++) {
        if (actual && actual[i] !== null) all.push(actual[i]);
        if (forecast && forecast[i] !== null) all.push(forecast[i]);
      }
      if (!all.length) return;
      let maxV = Math.max(...all);
      if (maxV <= 0) maxV = 1;
      maxV = maxV * 1.1;

      ctx.strokeStyle = TC('grid');
      ctx.lineWidth = 1;
      for (let g = 0; g <= 4; g++) {
        const y = padT + (g / 4) * plotH;
        ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(w - padR, y); ctx.stroke();
      }
      ctx.fillStyle = TC('muted');
      ctx.font = '10px -apple-system, sans-serif';
      ctx.textAlign = 'right';
      ctx.textBaseline = 'middle';
      for (let g = 0; g <= 4; g++) {
        const val = maxV - (g / 4) * maxV;
        const y = padT + (g / 4) * plotH;
        ctx.fillText(val.toFixed(1), padL - 4, y);
      }

      const groupW = plotW / 24;
      const tipR = canvas._tipR = [];
      for (let i = 0; i < 24; i++) {
        const fmt = (v) => (typeof v === 'number' ? v.toFixed(2).replace('.', ',') + ' kWh' : '—');
        const hh = (n) => String(n % 24).padStart(2, '0');
        const lines = [`${hh(i)}:00–${hh(i + 1)}:00`, 'Wykonanie: ' + fmt(actual ? actual[i] : null), 'Prognoza: ' + fmt(forecast ? forecast[i] : null)];
        tipR.push({ x: padL + i * groupW, y: 0, w: groupW, h: h, text: lines.join('\n') });
      }
      const barW = Math.max(4, groupW * 0.4);
      const nowH = new Date().getHours();
      const baseY = padT + plotH;
      // etykiety wartości: na szerokim ekranie wszystkie niezerowe, na wąskim tylko wyższe słupki
      const pvLabel = (v) => typeof v === 'number' && v >= 0.1 && (groupW >= 24 || v >= maxV * 0.4);

      for (let i = 0; i < 24; i++) {
        const cx = padL + (i + 0.5) * groupW;
        if (actual && actual[i] !== null) {
          const aH = Math.max(2, (actual[i] / maxV) * plotH);
          const x = cx - barW - 1;
          const grad = ctx.createLinearGradient(0, baseY - aH, 0, baseY);
          if (isToday && i === nowH) {
            grad.addColorStop(0, COLORS.tomorrow);
            grad.addColorStop(1, COLORS.tomorrowDark);
          } else {
            grad.addColorStop(0, COLORS.pv);
            grad.addColorStop(1, '#d97706');
          }
          ctx.fillStyle = grad;
          this._roundRect(ctx, x, baseY - aH, barW, aH, 3);
          ctx.fill();
          if (pvLabel(actual[i])) {
            ctx.fillStyle = COLORS.pv; ctx.font = 'bold 9px -apple-system, sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
            ctx.fillText(actual[i].toFixed(1), x + barW / 2, baseY - aH - 2);
          }
        }
        if (forecast && forecast[i] !== null && forecast[i] > 0.01) {
          const fH = Math.max(2, (forecast[i] / maxV) * plotH);
          const x = cx + 1;
          const grad = ctx.createLinearGradient(0, baseY - fH, 0, baseY);
          grad.addColorStop(0, 'rgba(96,165,250,0.75)');
          grad.addColorStop(1, 'rgba(37,99,235,0.75)');
          ctx.fillStyle = grad;
          this._roundRect(ctx, x, baseY - fH, barW, fH, 3);
          ctx.fill();
          if (pvLabel(forecast[i])) {
            ctx.fillStyle = '#93c5fd'; ctx.font = 'bold 9px -apple-system, sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
            ctx.fillText(forecast[i].toFixed(1), x + barW / 2, baseY - fH - 2);
          }
        }
      }

      ctx.fillStyle = TC('muted');
      ctx.font = '10px -apple-system, sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      const labelStep = w < 380 ? 6 : 3;
      for (let i = 0; i < 24; i += labelStep) {
        const cx = padL + (i + 0.5) * groupW;
        ctx.fillText(String(i).padStart(2, '0'), cx, padT + plotH + 6);
      }

      ctx.font = '11px -apple-system, sans-serif';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'middle';
      const lY = h - 7;
      ctx.fillStyle = COLORS.pv;
      ctx.fillRect(padL, lY - 5, 10, 10);
      ctx.fillStyle = TC('text2');
      ctx.fillText('rzeczywista', padL + 14, lY);
      ctx.fillStyle = 'rgba(96,165,250,0.75)';
      ctx.fillRect(padL + 100, lY - 5, 10, 10);
      ctx.fillStyle = TC('text2');
      ctx.fillText('prognoza', padL + 114, lY);
    }

    // ===== TABELA CEN =====
    _findPriceEntities() {
      const todayCandidates = ['sensor.rce_pse_cena', 'sensor.rce_pse_cena_dzisiaj', 'sensor.rce_pse_prices_today', 'sensor.rce_prices_today', 'sensor.cena_pradu_dzisiaj', 'sensor.energy_price_today'];
      const tomorrowCandidates = ['sensor.rce_pse_cena_jutro', 'sensor.rce_pse_prices_tomorrow', 'sensor.rce_prices_tomorrow', 'sensor.cena_pradu_jutro', 'sensor.energy_price_tomorrow'];
      let today = null, tomorrow = null;
      for (const eid of todayCandidates) if (this._hass.states[eid]) { today = eid; break; }
      for (const eid of tomorrowCandidates) if (this._hass.states[eid]) { tomorrow = eid; break; }
      if (!today) {
        for (const eid in this._hass.states) {
          if (/rce.*cena|prices?_today|cena.*pradu/i.test(eid) && !/jutro|tomorrow/i.test(eid)) { today = eid; break; }
        }
      }
      if (!tomorrow) {
        for (const eid in this._hass.states) {
          if (/rce.*cena.*jutro|prices?_tomorrow|cena.*jutro/i.test(eid)) { tomorrow = eid; break; }
        }
      }
      return { today, tomorrow };
    }

    _getPriceArray(sensor) {
      if (!sensor || !sensor.attributes) return [];
      for (const name of ['prices', 'raw_today', 'prices_today', 'today', 'forecast']) {
        if (Array.isArray(sensor.attributes[name])) return sensor.attributes[name];
      }
      return [];
    }

    // tabela 2 × 12 godzin (dziś / jutro); wartości w zł/kWh, null = brak ceny; est = kolumna „jutro” to szacunek (podgląd, nie ceny z rynku)
    _priceTableHtml(today, tomorrow, title, src, cheapIsGood = false, est = false) {
      const vals = (a) => (a || []).filter(v => v !== null);
      const mm = (a) => { const v = vals(a); return v.length ? [Math.max(...v), Math.min(...v)] : [null, null]; };
      const [maxD, minD] = mm(today), [maxJ, minJ] = mm(tomorrow);
      const fmt = (val, max, min, isEst = false) => {
        if (val === null || val === undefined) return '--';
        const str = (isEst ? '~' : '') + val.toFixed(2);
        // sprzedaż: najwyższa cena = zielona (dobrze); zakup (cheapIsGood): najniższa = zielona, najwyższa = czerwona
        if (isEst) return `<span class="price-est">${str}</span>`;
        if (val === max) return `<span class="${cheapIsGood ? 'price-min' : 'price-max'}">${str}</span>`;
        if (val === min) return `<span class="${cheapIsGood ? 'price-max' : 'price-min'}">${str}</span>`;
        return str;
      };
      const at = (a, i) => (a && i < a.length) ? a[i] : null;
      const nowHour = new Date().getHours();
      let html = title ? `<div class="price-header" style="margin-top:8px;">${this._esc(title)}${src ? ` <span style="opacity:.6;font-size:11px;">(${this._esc(src)})</span>` : ''}</div>` : '';
      html += `<table class="price-table">
        <tr><th>Godz.</th><th>Dziś</th><th>${est ? 'Jutro szac.' : 'Jutro'}</th><th width="10"></th>
            <th>Godz.</th><th>Dziś</th><th>${est ? 'Jutro szac.' : 'Jutro'}</th></tr>`;
      for (let i = 0; i < 12; i++) {
        const h1 = `${String(i).padStart(2, '0')}-${String(i + 1).padStart(2, '0')}`;
        const h2 = `${String(i + 12).padStart(2, '0')}-${String((i + 13) % 24).padStart(2, '0')}`;
        const rc1 = i === nowHour ? ' class="price-now-hour"' : '';
        const rc2 = (i + 12) === nowHour ? ' class="price-now-hour"' : '';
        html += `<tr>
          <td${rc1}><b>${h1}</b></td><td${rc1}>${fmt(at(today, i), maxD, minD)}</td><td${rc1}>${fmt(at(tomorrow, i), maxJ, minJ, est)}</td>
          <td></td>
          <td${rc2}><b>${h2}</b></td><td${rc2}>${fmt(at(today, i + 12), maxD, minD)}</td><td${rc2}>${fmt(at(tomorrow, i + 12), maxJ, minJ, est)}</td>
        </tr>`;
      }
      return html + `</table>`;
    }

    // najlepsze okno dla urządzenia: pasek cen zakupu od teraz do końca jutra, najtańszy / najdroższy ciągły blok 1–4 h
    // i ostrzeżenie o ujemnych cenach jutro (sprzedaż / zakup)
    _priceFinderHtml(bT, bJ, sJ, reactionOn) {
      const nowH = new Date().getHours();
      const seq = [];
      (bT || []).forEach((v, h) => { if (h >= nowH) seq.push({ d: 0, h, v }); });
      if (bJ) bJ.forEach((v, h) => seq.push({ d: 1, h, v }));
      const known = seq.filter(x => x.v !== null);
      const dur = [1, 2, 3, 4].includes(this._pfDur) ? this._pfDur : 2;
      const fmt = (v) => v.toFixed(2).replace('.', ',');
      const lab = (x) => (x.d ? 'jutro' : 'dziś') + ' ' + String(x.h).padStart(2, '0') + ':00';
      const blk = (cheapest) => {
        let best = null;
        for (let i = 0; i + dur <= seq.length; i++) {
          const w = seq.slice(i, i + dur);
          if (w.some(x => x.v === null)) continue;
          const avg = w.reduce((a, x) => a + x.v, 0) / dur;
          if (best === null || (cheapest ? avg < best.avg : avg > best.avg)) best = { i, avg };
        }
        return best;
      };
      let html = '';
      // ostrzeżenia o ujemnych cenach jutro
      const spans = (arr) => { const hs = []; (arr || []).forEach((v, h) => { if (v !== null && v < 0) hs.push(h); });
        const out = []; for (let i = 0; i < hs.length;) { let j = i; while (j + 1 < hs.length && hs[j + 1] === hs[j] + 1) j++; out.push(String(hs[i]).padStart(2, '0') + '–' + String(hs[j] + 1).padStart(2, '0')); i = j + 1; } return out.join(', '); };
      const negS = spans(sJ), negB = spans(bJ);
      if (negS) html += `<div class="price-note" id="priceNegSell">📉 <b>Jutro ujemna cena sprzedaży</b> w godzinach ${this._esc(negS)}: za eksport do sieci byś dopłacał. ${reactionOn ? 'Reakcja na niskie/ujemne ceny jest włączona — EMS wstrzyma sprzedaż z baterii.' : 'Włącz „Reakcję na niskie/ujemne ceny RCE” (Ustawienia), żeby EMS wstrzymał wtedy sprzedaż z baterii.'} W tych godzinach nie opłaca się ładować z sieci.</div>`;
      if (negB) html += `<div class="price-note" id="priceNegBuy">💸 <b>Jutro ujemna cena zakupu</b> w godzinach ${this._esc(negB)}: sprzedawca dopłaca do poboru. Najlepszy czas na pralkę, zmywarkę, bojler albo ładowanie auta.</div>`;
      if (known.length < 4) return html;
      const vals = known.map(x => x.v), mn = Math.min(...vals), mx = Math.max(...vals), span = mx - mn || 1;
      const lo = blk(true), hi = blk(false);
      const bars = seq.map((x) => {
        if (x.v === null) return '<div style="flex:1;min-width:0;height:100%;"></div>';
        const t = (x.v - mn) / span, hue = Math.round(120 - 120 * t);
        const hgt = 14 + Math.round(t * 34);
        const inBlk = (b) => b && seq.indexOf(x) >= b.i && seq.indexOf(x) < b.i + dur;
        const ring = inBlk(lo) ? 'outline:2px solid var(--green);' : (inBlk(hi) ? 'outline:2px solid var(--red);' : '');
        return `<div title="${this._esc(lab(x))} — ${fmt(x.v)} zł/kWh" style="flex:1;min-width:0;height:100%;display:flex;align-items:flex-end;"><div style="width:100%;height:${hgt}px;background:hsl(${hue},65%,48%);border-radius:2px;${ring}"></div></div>`;
      }).join('');
      const line = (b, ico, name) => {
        if (!b) return '';
        const a = seq[b.i], z = seq[b.i + dur - 1];
        const endH = (z.h + 1) % 24;
        const when = a.d === z.d || endH === 0 ? `${lab(a)}–${String(endH).padStart(2, '0')}:00` : `${lab(a)} – ${lab(z)}`;
        return `<div style="font-size:12px;margin-top:4px;">${ico} ${name}: <b>${this._esc(when)}</b>, średnio ${fmt(b.avg)} zł/kWh</div>`;
      };
      const avgAll = vals.reduce((a, v) => a + v, 0) / vals.length;
      const save = lo ? `<div style="font-size:11px;opacity:.7;margin-top:2px;">≈ ${fmt(avgAll - lo.avg)} zł taniej za każdą kWh niż średnio w tym okresie (${fmt(avgAll)} zł/kWh).</div>` : '';
      const btns = [1, 2, 3, 4].map(n => `<button class="btn${n === dur ? ' active' : ''}" data-pf-dur="${n}" style="padding:5px 12px;font-size:12px;">${n} h</button>`).join('');
      html += `<div class="price-header" style="margin-top:10px;">⏱ Najlepsze okno dla urządzenia <span style="opacity:.6;font-size:11px;">(od teraz${bJ ? ' do końca jutra' : ''})</span></div>
        <div style="display:flex;gap:6px;margin:6px 0;align-items:center;font-size:12px;">Pracuje przez: ${btns}</div>
        <div id="priceFinderBars" style="display:flex;gap:1px;height:52px;align-items:flex-end;">${bars}</div>
        <div style="display:flex;justify-content:space-between;font-size:10px;opacity:.6;"><span>${this._esc(lab(seq[0]))}</span><span>${this._esc(lab(seq[seq.length - 1]))}</span></div>
        ${line(lo, '🟢', 'Najtaniej')}${line(hi, '🔴', 'Najdrożej')}${save}`;
      return html;
    }

    _renderPriceTable() {
      const container = this._el('priceTableContainer');
      const header = this._el('priceTableHeader');
      if (!container || !header) return;

      // 0.8.0+: dokładnie te ceny, których używa planer (sprzedaż i — przy taryfie dynamicznej — zakup), w zł/kWh
      const a = this._rsAttrs();
      const num = (v) => (typeof v === 'number' && isFinite(v)) ? v : null;
      const arr24 = (x) => (Array.isArray(x) && x.some(v => num(v) !== null)) ? Array.from({ length: 24 }, (_, i) => num(x[i])) : null;
      const sT = arr24(a.prices_sell_today), sJ = arr24(a.prices_sell_tomorrow);
      if (sT || sJ) {
        const bT = arr24(a.prices_buy_today), bJ = arr24(a.prices_buy_tomorrow);
        // podgląd: gdy prawdziwych cen zakupu na jutro jeszcze nie ma, pokazujemy szacunek z historii (planer go nie używa)
        const bE = (!bJ && bT) ? arr24(a.prices_buy_tomorrow_est) : null;
        const bEN = bE && typeof a.price_buy_tomorrow_est_note === 'string' ? a.price_buy_tomorrow_est_note : '';
        const cur = num(Number(a.price_sell));
        header.textContent = `Ceny sprzedaży > Teraz: ${cur === null ? '--' : cur.toFixed(2)} PLN/kWh`;
        const bNote = (bT || bJ) && !bJ && typeof a.price_buy_tomorrow_note === 'string' ? a.price_buy_tomorrow_note : '';
        const bNoteWait = a.price_buy_tomorrow_state === 'waiting';
        const feed = this._hass.states[this._eid('sensor', 'buy_rce')], fa = (feed && feed.attributes) || null;
        const feedOn = !!(fa && fa.enabled);
        const key = JSON.stringify([sT, sJ, bT, bJ, bE, bEN, a.price_sell_source, a.price_buy_source, bNote, bNoteWait, new Date().getHours(),
          feedOn, fa && fa.fit, fa && fa.note, fa && fa.tomorrow_available, fa && fa.is_buy_source, this._pfDur || 2, (this._hass.states[this._eid('switch', 'negative_price_reaction')] || {}).state]);
        if (this._lastPriceTableKey === key) return;
        this._lastPriceTableKey = key;
        let html = this._priceTableHtml(sT, sJ, '', '');
        if (bT || bJ) html += this._priceTableHtml(bT, bJ || bE, 'Ceny zakupu (taryfa dynamiczna)', a.price_buy_source || a.price_buy_entity || '', true, !!bE);
        if (bEN) html += `<div class="price-note est" id="priceBuyEstNote">📈 ${this._esc(bEN)}</div>`;
        {
          const reactOn = (this._hass.states[this._eid('switch', 'negative_price_reaction')] || {}).state === 'on';
          html += this._priceFinderHtml(bT, bJ, sJ, reactOn);
          if (!container._pfBound) {
            container._pfBound = true;
            container.addEventListener('click', (ev) => {
              const b = ev.target && ev.target.closest ? ev.target.closest('[data-pf-dur]') : null;
              if (!b) return;
              this._pfDur = Number(b.dataset.pfDur); this._lastPriceTableKey = null; this._renderPriceTable();
            });
          }
        }
        if (feedOn) {
          const f = fa.fit;
          const txt = f
            ? `Własne ceny z PSE (RCE): dopasowanie do Twojej taryfy ${this._esc(String(f.quality))} (średni błąd ${Number(f.rmse).toFixed(3)} zł/kWh, ${this._esc(String(f.days))} dób). `
              + (fa.is_buy_source ? (fa.tomorrow_available ? 'Cena zakupu bierze się z tego sensora — jutro jest już znane.' : 'Cen na jutro PSE jeszcze nie opublikowało (zwykle po ~13:00).')
                : 'Żeby planer ich używał, wskaż jako „encję ceny zakupu” sensor.bms_buy_rce (po kilku dobach zbierania możesz wyłączyć dotychczasowe źródło).')
            : this._esc(String(fa.note || 'Własne ceny z PSE: czekam na dane.'));
          html += `<div class="price-note" id="priceFeedNote">🌐 ${txt}</div>`;
        }
        if (bNote) html += `<div class="price-note${bNoteWait ? ' wait' : ''}" id="priceBuyNote">${bNoteWait ? '⏳' : 'ℹ️'} <b>Jutro:</b> ${this._esc(bNote)}</div>`;
        container.innerHTML = html;
        return;
      }

      const { today, tomorrow } = this._findPriceEntities();
      if (!today) {
        container.innerHTML = '<div style="padding:8px;color:#fbbf24;font-size:12px;">⚠️ Nie znaleziono encji cen prądu (np. sensor.rce_pse_cena).</div>';
        header.textContent = 'Ceny sprzedaży: brak danych';
        return;
      }

      const todaySensor = this._hass.states[today];
      const tomorrowSensor = tomorrow ? this._hass.states[tomorrow] : null;
      header.innerHTML = `Ceny sprzedaży > Teraz: <span style="color:var(--text);">${todaySensor.state}</span> PLN/kWh`;

      const pricesToday = this._getPriceArray(todaySensor);
      const pricesTomorrow = this._getPriceArray(tomorrowSensor);

      if (pricesToday.length === 0) {
        container.innerHTML = `<div style="padding:8px;color:#fbbf24;font-size:12px;">⚠️ Encja ${today} nie ma atrybutu prices/raw_today.</div>`;
        return;
      }

      const cacheKey = `${today}|${tomorrow}|${todaySensor.state}|${pricesToday.length}|${pricesTomorrow.length}`;
      if (this._lastPriceTableKey === cacheKey) return;
      this._lastPriceTableKey = cacheKey;

      const step = pricesToday.length >= 48 ? Math.floor(pricesToday.length / 24) : 1;
      const getPrice = (arr, idx) => {
        if (!arr || idx >= arr.length) return null;
        const item = arr[idx];
        if (item == null) return null;
        if (typeof item === 'number') return item;
        return item.rce_pln ?? item.price ?? item.value ?? item.cena ?? null;
      };

      let maxD = -Infinity, minD = Infinity, maxJ = -Infinity, minJ = Infinity;
      for (let i = 0; i < 24; i++) {
        const idx = i * step;
        const d = getPrice(pricesToday, idx);
        const j = getPrice(pricesTomorrow, idx);
        if (d !== null) { if (d > maxD) maxD = d; if (d < minD) minD = d; }
        if (j !== null) { if (j > maxJ) maxJ = j; if (j < minJ) minJ = j; }
      }

      const fmt = (val, max, min) => {
        if (val === null) return '--';
        const str = val.toFixed(2);
        if (val === max) return `<span class="price-max">${str}</span>`;
        if (val === min) return `<span class="price-min">${str}</span>`;
        return str;
      };

      const nowHour = new Date().getHours();
      let html = `<table class="price-table">
        <tr><th>Godz.</th><th>Dziś</th><th>Jutro</th><th width="10"></th>
            <th>Godz.</th><th>Dziś</th><th>Jutro</th></tr>`;
      for (let i = 0; i < 12; i++) {
        const idx1 = i * step;
        const idx2 = (i + 12) * step;
        const d1 = getPrice(pricesToday, idx1);
        const j1 = getPrice(pricesTomorrow, idx1);
        const d2 = getPrice(pricesToday, idx2);
        const j2 = getPrice(pricesTomorrow, idx2);
        const h1 = `${String(i).padStart(2, '0')}-${String(i + 1).padStart(2, '0')}`;
        const h2 = `${String(i + 12).padStart(2, '0')}-${String((i + 13) % 24).padStart(2, '0')}`;
        const rowClass1 = i === nowHour ? ' class="price-now-hour"' : '';
        const rowClass2 = (i + 12) === nowHour ? ' class="price-now-hour"' : '';
        html += `<tr>
          <td${rowClass1}><b>${h1}</b></td>
          <td${rowClass1}>${fmt(d1, maxD, minD)}</td>
          <td${rowClass1}>${fmt(j1, maxJ, minJ)}</td>
          <td></td>
          <td${rowClass2}><b>${h2}</b></td>
          <td${rowClass2}>${fmt(d2, maxD, minD)}</td>
          <td${rowClass2}>${fmt(j2, maxJ, minJ)}</td>
        </tr>`;
      }
      html += `</table>`;
      container.innerHTML = html;
    }

    _chartReady() {
      try {
        if (!window.Chart || !window.Chart._adapters || !window.Chart._adapters._date) return false;
        new window.Chart._adapters._date({}).formats();   // rzuca, gdy adapter dat jeszcze nie nadpisał klasy bazowej
        return true;
      } catch (e) { return false; }
    }

    _safe(fn) {
      try { fn(); } catch (e) { console.warn('EMS PANEL render error:', e); }
    }

    // ===== ZAAWANSOWANY WYKRES HISTORII =====
    async _fetchHistoryData(range) {
      if (!this._hass) return;
      
      if (!this._chartReady()) {
        this._chartWaitTries = (this._chartWaitTries || 0) + 1;
        if (this._chartWaitTries < 40) setTimeout(() => this._fetchHistoryData(range), 500);
        else console.warn('EMS: Chart.js / adapter dat nie załadowany (brak dostępu do CDN?)');
        return;
      }

      const now = new Date();
      let start = new Date();
      if (range === '1D') start.setDate(now.getDate() - 1);
      else if (range === '7D') start.setDate(now.getDate() - 7);
      else if (range === '30D') start.setDate(now.getDate() - 30);
      else if (range === '90D') start.setDate(now.getDate() - 90);

      const invOr = (tail, fb) => { const e = this._inv('sensor', tail); return this._hass.states[e] ? e : fb; };
      const pvEid = invOr('pv_power', 'sensor.bms_pv_power');
      const loadEid = invOr('load_power', 'sensor.bms_load_power');
      const socEid = invOr('battery', 'sensor.bms_soc');
      const gridEid = invOr('grid_power', 'sensor.bms_grid_power');
      const priceEid = this._rsAttrs().price_sell_entity || 'sensor.rce_pse_cena';   // skonfigurowana cena sprzedaży (RCE, Pstryk…)

      const entities = [pvEid, loadEid, socEid, gridEid, priceEid].filter(e => this._hass.states[e]);

      try {
        const res = await this._hass.callWS({
          type: 'history/history_during_period',
          start_time: start.toISOString(),
          end_time: now.toISOString(),
          entity_ids: entities,
          minimal_response: true,
          no_attributes: true,
          significant_changes_only: false,
          include_start_time_state: true,
        });

        const extractPoints = (arr, isNumeric = true) => {
          if (!arr) return [];
          return arr.map(item => {
            // minimal_response zwraca czas jako 'lu' (epoch s); 'lc' jest tylko gdy różni się od 'lu'.
            let ts = NaN;
            if (typeof item.lc === 'number') ts = item.lc * 1000;
            else if (typeof item.lu === 'number') ts = item.lu * 1000;
            else ts = new Date(item.last_changed || item.last_updated).getTime();
            let val = item.s !== undefined ? item.s : item.state;
            if (isNumeric) {
              val = parseFloat(val);
              if (isNaN(val)) return null;
            }
            return { x: ts, y: val };
          }).filter(p => p !== null && !isNaN(p.x));
        };

        const aggregate = (points, type = 'avg', intervalMs = 3600000) => {
          if (!points.length) return [];
          const buckets = {};
          points.forEach(p => {
            const bucket = Math.floor(p.x / intervalMs) * intervalMs;
            if (!buckets[bucket]) buckets[bucket] = [];
            if (type === 'max') {
              if (!buckets[bucket].length || p.y > buckets[bucket][0]) buckets[bucket] = [p.y];
            } else {
              buckets[bucket].push(p.y);
            }
          });
          
          let result = [];
          for (const [ts, vals] of Object.entries(buckets)) {
            const val = type === 'max' ? vals[0] : vals.reduce((a,b)=>a+b,0) / vals.length;
            result.push({ x: parseInt(ts), y: val });
          }
          return result.sort((a,b) => a.x - b.x);
        };

        let aggMs = 3600000;
        if (range === '1D') aggMs = 15 * 60000;
        else if (range === '7D') aggMs = 3600000;
        else if (range === '30D') aggMs = 6 * 3600000;
        else if (range === '90D') aggMs = 24 * 3600000;

        const pv = aggregate(extractPoints(res[pvEid]), 'avg', aggMs).map(p => ({ x: p.x, y: p.y / 1000 }));
        const load = aggregate(extractPoints(res[loadEid]), 'avg', aggMs).map(p => ({ x: p.x, y: p.y / 1000 }));
        const soc = aggregate(extractPoints(res[socEid]), 'avg', aggMs);
        const price = aggregate(extractPoints(res[priceEid]), 'avg', aggMs);
        
        const gridRaw = aggregate(extractPoints(res[gridEid]), 'avg', aggMs).map(p => ({ x: p.x, y: p.y / 1000 }));
        const sell = gridRaw.map(p => ({ x: p.x, y: p.y < 0 ? Math.abs(p.y) : 0 }));

        this._historyData = { pv, load, soc, price, sell };
        this._renderHistoryChart();

      } catch (e) {
        console.warn('EMS history data fetch error:', e);
      }
    }

    _renderHistoryChart() {
      if (!this._chartReady() || !this._historyData) return;
      const canvas = this._el('historyChart');
      if (!canvas) return;

      if (this._chartJsInstance) {
        this._chartJsInstance.destroy();
      }

      const data = this._historyData;
      
      const hasAnyData = (data.pv?.length || 0) + (data.load?.length || 0) + 
                        (data.soc?.length || 0) + (data.price?.length || 0) > 0;
      if (!hasAnyData) {
        const parent = canvas.parentElement;
        if (parent && !parent.querySelector('.chart-empty')) {
          canvas.style.display = 'none';
          const m = document.createElement('div');
          m.className = 'chart-empty';
          m.textContent = 'Brak danych historycznych w wybranym zakresie. Sprawdź czy encje są rejestrowane w recorder.';
          parent.appendChild(m);
        }
        return;
      }
      canvas.style.display = 'block';
      const emptyMsg = canvas.parentElement && canvas.parentElement.querySelector('.chart-empty');
      if (emptyMsg) emptyMsg.remove();

      const maxPrice = Math.max(...(data.price || []).map(p => p.y), 0.01);
      const priceNormalized = (data.price || []).map(p => ({ x: p.x, y: (p.y / maxPrice) * 80 }));
      this._chartMaxPrice = maxPrice;

      this._chartJsInstance = new window.Chart(canvas.getContext('2d'), {
        type: 'line',
        data: {
          datasets: [
            {
              type: 'bar',
              label: 'CENA SPRZEDAŻY',
              data: priceNormalized,
              backgroundColor: 'rgba(59, 130, 246, 0.35)',
              borderColor: 'rgba(59, 130, 246, 0.7)',
              borderWidth: 0,
              yAxisID: 'yPercent',
              barPercentage: 0.95,
              categoryPercentage: 0.95,
              order: 10,
            },
            {
              type: 'line',
              label: 'PRODUKCJA PV (kW)',
              data: data.pv || [],
              borderColor: '#EAB308',
              backgroundColor: 'rgba(234, 179, 8, 0.1)',
              borderWidth: 2,
              pointRadius: 0,
              pointHoverRadius: 4,
              fill: true,
              yAxisID: 'yPower',
              tension: 0.3,
              order: 3,
            },
            {
              type: 'line',
              label: 'ZUŻYCIE DOMU (kW)',
              data: data.load || [],
              borderColor: '#ec4899',
              backgroundColor: 'transparent',
              borderWidth: 2,
              pointRadius: 0,
              pointHoverRadius: 4,
              fill: false,
              yAxisID: 'yPower',
              tension: 0.3,
              order: 4,
            },
            {
              type: 'line',
              label: 'SPRZEDAŻ DO SIECI (kW)',
              data: data.sell || [],
              borderColor: '#ef4444',
              backgroundColor: 'transparent',
              borderWidth: 1.5,
              pointRadius: 0,
              pointHoverRadius: 4,
              fill: false,
              yAxisID: 'yPower',
              tension: 0.3,
              order: 5,
            },
            {
              type: 'line',
              label: 'POZIOM MAGAZYNU (SOC %)',
              data: data.soc || [],
              borderColor: '#84cc16',
              backgroundColor: 'transparent',
              borderWidth: 2.5,
              pointRadius: 0,
              pointHoverRadius: 4,
              fill: false,
              yAxisID: 'yPercent',
              tension: 0.3,
              order: 1,
            },
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          plugins: {
            legend: { display: false },
            tooltip: {
              backgroundColor: TC('tip'),
              titleColor: TC('text'),
              bodyColor: TC('text2'),
              borderColor: TC('line'),
              borderWidth: 1,
              padding: 12,
              callbacks: {
                label: (context) => {
                  const label = context.dataset.label || '';
                  const val = context.parsed.y;
                  if (label === 'CENA SPRZEDAŻY') {
                    let realVal = (val / 80) * this._chartMaxPrice;
                    if (Math.abs(realVal) > 20) realVal /= 1000;      // encja w PLN/MWh (jak w planerze)
                    return `CENA SPRZEDAŻY: ${realVal.toFixed(3)} PLN/kWh`;
                  }
                  if (label.includes('SOC')) {
                    return `SOC: ${val.toFixed(0)}%`;
                  }
                  return `${label}: ${val.toFixed(2)} kW`;
                }
              }
            }
          },
          scales: {
            x: {
              type: 'time',
              time: {
                tooltipFormat: 'dd.MM.yyyy HH:mm',
                displayFormats: { minute: 'HH:mm', hour: 'HH:mm', day: 'dd.MM' }
              },
              grid: { display: false },
              ticks: { color: TC('muted'), maxRotation: 0, font: { size: 10 } }
            },
            yPower: {
              type: 'linear',
              position: 'left',
              grid: { color: TC('grid') },
              ticks: { 
                color: '#22d3ee', 
                callback: (v) => v + ' kW',
                font: { size: 10 }
              },
              title: { display: true, text: 'Moc (kW)', color: '#22d3ee', font: { size: 10 } }
            },
            yPercent: {
              type: 'linear',
              position: 'right',
              min: 0,
              max: 100,
              grid: { display: false },
              ticks: { 
                color: '#84cc16', 
                callback: (v) => v + '%',
                font: { size: 10 }
              },
              title: { display: true, text: 'SOC / Cena (% max)', color: '#84cc16', font: { size: 10 } }
            }
          }
        },
        plugins: [dayNightPlugin]
      });
    }

    // ===== ZAKŁADKA: ZYSK I DZIENNIK DECYZJI =====
    _esc(v) {
      return String(v === null || v === undefined ? '' : v)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    _money(v) {
      const n = parseFloat(v);
      if (isNaN(n)) return '—';
      return (n > 0 ? '+' : '') + n.toFixed(2).replace('.', ',') + ' zł';
    }

    // Wykres bilansu dziennego (wersja A): słupki z kwotą, daty pod spodem, linia „narastająco”.
    // Układ w HTML (stały rozmiar tekstu na telefonie i monitorze), linia w SVG rozciąganym na cały obszar.
    _balanceSvg(days, note) {
      const pts = (Array.isArray(days) ? days : []).map(d => ({ date: String((d && d.date) || ''), v: parseFloat(d && d.net) }))
        .filter(d => d.date && isFinite(d.v));
      if (!pts.length) return '';
      let run = 0;
      pts.forEach(p => { run += p.v; p.cum = run; });
      const n = pts.length;
      const lo = Math.min(0, ...pts.map(p => Math.min(p.v, p.cum))), hi = Math.max(0, ...pts.map(p => Math.max(p.v, p.cum)));
      const span = (hi - lo) || 1, pad = span * 0.14, y0 = lo - (lo < 0 ? pad : 0), y1 = hi + (hi > 0 ? pad : 0);
      const Y = v => (y1 - v) / ((y1 - y0) || 1) * 100;                  // % od góry obszaru wykresu
      const X = i => (i + 0.5) / n * 100;                                  // % od lewej
      const zl = v => (v < 0 ? '−' : v > 0 ? '+' : '') + Math.abs(v).toFixed(2).replace('.', ',');
      const ex = pts.reduce((a, p, i) => ({ mx: p.v > pts[a.mx].v ? i : a.mx, mn: p.v < pts[a.mn].v ? i : a.mn }), { mx: 0, mn: 0 });
      const showVal = i => n <= 10 || i === ex.mx || i === ex.mn || i === n - 1;
      const every = Math.max(1, Math.ceil(n / 10));
      const bwPct = Math.min(60, 100 / n * 0.6);
      const ticks = [y0, 0, y1].filter((v, i, a) => a.findIndex(w => Math.abs(w - v) < span * 0.15) === i);
      const lab = 'position:absolute;transform:translateX(-50%);font-size:11px;color:var(--muted);white-space:nowrap;line-height:1;';
      const grid = ticks.map(v => `<div style="position:absolute;left:0;right:0;top:${Y(v)}%;border-top:1px solid var(--muted);opacity:${Math.abs(v) < 1e-9 ? 0.55 : 0.18};"></div>`).join('');
      const yl = ticks.map(v => `<div style="position:absolute;right:6px;top:${Y(v)}%;transform:translateY(-50%);font-size:11px;color:var(--muted);white-space:nowrap;">${zl(v)}</div>`).join('');
      const bars = pts.map((p, i) => {
        const yv = Y(p.v), yz = Y(0), top = Math.min(yv, yz), h = Math.max(0.8, Math.abs(yz - yv));
        const col = p.v >= 0 ? '#34d399' : '#f87171';
        const tip = `${this._esc(p.date)}: ${this._money(p.v)} · narastająco ${this._money(p.cum)}`;
        const val = showVal(i) ? (p.v >= 0
          ? `<div style="${lab}left:${X(i)}%;top:calc(${top}% - 15px);">${zl(p.v)}</div>`
          : `<div style="${lab}left:${X(i)}%;top:calc(${top + h}% + 4px);">${zl(p.v)}</div>`) : '';
        return `<div title="${tip}" style="position:absolute;left:${X(i)}%;width:min(${bwPct}%, 28px);transform:translateX(-50%);top:${top}%;height:${h}%;background:${col};border-radius:${p.v >= 0 ? '3px 3px 0 0' : '0 0 3px 3px'};"></div>${val}`;
      }).join('');
      const line = n > 1 ? `<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="position:absolute;inset:0;width:100%;height:100%;overflow:visible;pointer-events:none;">
          <polyline points="${pts.map((p, i) => `${X(i).toFixed(2)},${Y(p.cum).toFixed(2)}`).join(' ')}" fill="none" stroke="#60a5fa" stroke-width="2" stroke-dasharray="5 4" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/></svg>` : '';
      const dates = pts.map((p, i) => {
        if (!(i % every === 0 || i === n - 1)) return '';
        const dt = p.date.length >= 10 ? `${p.date.slice(8, 10)}.${p.date.slice(5, 7)}` : p.date;
        return `<div style="${lab}left:${X(i)}%;top:4px;">${this._esc(dt)}</div>`;
      }).join('');
      const sq = c => `<span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:${c};margin-right:4px;vertical-align:-1px;"></span>`;
      return `<div style="display:flex;gap:14px;flex-wrap:wrap;font-size:11px;color:var(--muted);margin-top:12px;">
          <span>${sq('#34d399')}dzień na plus</span><span>${sq('#f87171')}dzień na minus</span>
          <span><span style="display:inline-block;width:14px;border-top:2px dashed #60a5fa;margin-right:4px;vertical-align:3px;"></span>narastająco: <b>${this._money(run)}</b></span></div>
        <div class="bms-bal" role="img" aria-label="Bilans dzienny w zł, ${n} dni, narastająco ${this._money(run)}" style="display:flex;margin-top:8px;">
          <div style="position:relative;width:52px;flex:none;height:150px;margin-top:16px;">${yl}</div>
          <div style="flex:1;min-width:0;">
            <div style="position:relative;height:150px;margin-top:16px;">${grid}${bars}${line}</div>
            <div style="position:relative;height:20px;margin-top:4px;">${dates}</div>
          </div>
        </div>
        ${note ? `<div style="font-size:11px;color:var(--muted);margin-top:2px;">${note}</div>` : ''}`;
    }

    _renderLogTab() {
      const body = this._el('logTabBody');
      if (!body || !this._hass) return;
      const root = this.shadowRoot;
      const act = root && root.activeElement;
      if (act && act.tagName === 'INPUT' && act.closest && act.closest('[data-tile^="log-"]')) return;
      if (this._layEdit && root.querySelector('[data-tile^="log-"]')) return;   // w trakcie edycji układu nie przebudowujemy kafelków pod rękami

      const st = (domain, key) => this._hass.states[this._eid(domain, key)];
      const logSt = st('sensor', 'decision_log');
      const pToday = st('sensor', 'profit_today');
      const pMonth = st('sensor', 'profit_month');
      const pTotal = st('sensor', 'profit_total');
      const reserve = st('sensor', 'reserve_soc');
      const entries = (logSt && logSt.attributes && logSt.attributes.entries) || [];
      const hist = (pToday && pToday.attributes && pToday.attributes.history) || [];

      const FEATURES = [
        ['negative_price_reaction', 'Reakcja na niskie/ujemne ceny RCE'],
        ['price_feed', 'Własne ceny z PSE (RCE) → cena zakupu dopasowana do taryfy'],
        ['full_charge', 'Pełne ładowanie baterii co kilka dni (kalibracja SOC, wyrównanie ogniw)'],
        ['profit_check', 'Sprawdzaj opłacalność sprzedaży'],
        ['dynamic_reserve', 'Dynamiczna rezerwa SOC'],
        ['auto_apply', 'Automatycznie stosuj propozycje'],
        ['readback_verify', 'Weryfikuj komendy (odczyt zwrotny)'],
        ['recurring_schedule', 'Harmonogram cykliczny (codziennie)'],
        ['holidays_as_sunday', 'Święta jak niedziela'],
      ];
      const DAYS = [['dzien_pn', 'Pn'], ['dzien_wt', 'Wt'], ['dzien_sr', 'Śr'], ['dzien_cz', 'Cz'], ['dzien_pt', 'Pt'], ['dzien_so', 'So'], ['dzien_nd', 'Nd']];
      const NUMS = [
        ['low_price_threshold', 'Próg niskiej ceny RCE (PLN/kWh)', 0.01],
        ['full_charge_days', 'Pełne ładowanie baterii: co ile dni', 1],
        ['min_sell_margin', 'Min. marża sprzedaży (PLN/kWh)', 0.01],
        ['cycle_efficiency', 'Sprawność cyklu baterii (%)', 1],
        ['reserve_floor_soc', 'Rezerwa SOC — minimum (%)', 1],
        ['auto_apply_max_shift_h', 'Auto-stosowanie: maks. przesunięcie (h, 0 = bez limitu)', 1],
      ];

      // opisy: co robi funkcja i kiedy ją włączać (pod nazwą przełącznika / pola)
      const DESC = {
        negative_price_reaction: 'Gdy cena sprzedaży RCE spada poniżej progu (lub jest ujemna), EMS nie sprzedaje z baterii i ogranicza oddawanie do sieci, żebyś nie dopłacał do eksportu. Próg ustawiasz niżej.',
        price_feed: 'EMS pobiera ceny RCE z PSE i przelicza je na cenę zakupu dopasowaną do Twojej taryfy dynamicznej (sensor „bms_buy_rce”), także na jutro, bez integracji sprzedawcy. Uczy się z Twoich zapisanych cen; ocena dopasowania jest pod tabelą cen.',
        full_charge: 'Co kilka dni (pole niżej) ładuje baterię do 100%, żeby BMS skalibrował SOC i wyrównał ogniwa. Dojście do ~98% z PV zalicza cykl; jeśli się nie uda, planer dobije z sieci w najtańszych godzinach nocy.',
        profit_check: 'Przed sprzedażą z baterii sprawdza, czy po sprawności cyklu, zużyciu baterii i minimalnej marży to się opłaca. Jeśli nie, sprzedaż jest pomijana.',
        dynamic_reserve: 'Rezerwa SOC liczona z prognozy zużycia i PV: tyle, ile dom potrzebuje, zanim PV znów pokryje zużycie. Wyłączona = tylko stały próg „Rezerwa SOC — minimum”.',
        auto_apply: 'EMS sam wpisuje do falownika okna ładowania i sprzedaży z planu (gdy plan jest stabilny ≥ 30 min, nie częściej niż co godzinę). Wyłączone: propozycje czekają na Twoje „Zastosuj”.',
        readback_verify: 'Po każdej komendzie odczytuje wartość z falownika i porównuje ją z wysłaną; przy rozbieżności ponawia i ostrzega.',
        recurring_schedule: 'Codziennie powtarza zapisany harmonogram startów w dniach wybranych niżej.',
        holidays_as_sunday: 'W święta ustawowe harmonogram działa jak w niedzielę (wg ustawień dla niedzieli).',
      };
      const NDESC = {
        low_price_threshold: 'Poniżej tej ceny RCE (zł/kWh) uznajemy cenę za niską i, przy włączonej reakcji, wstrzymujemy sprzedaż z baterii.',
        full_charge_days: 'Co ile dni wymusić pełne ładowanie do 100% (działa po włączeniu „Pełne ładowanie baterii”).',
        min_sell_margin: 'Najmniejszy zysk na 1 kWh (zł), przy którym planer w ogóle sprzedaje z baterii. Wyższa wartość = rzadsze, pewniejsze sprzedaże.',
        cycle_efficiency: 'Ile energii wraca z baterii po naładowaniu (typowo 88–95%). Planer używa jej do liczenia opłacalności; zbyt wysoka wartość (np. 100%) sprawia, że opłacają się nawet drobne zmiany.',
        reserve_floor_soc: 'Najniższy poziom naładowania, poniżej którego plan nie schodzi (poza progiem odcięcia falownika). Wyższa wartość = bezpieczniej, ale mniej energii do sprzedaży.',
        auto_apply_max_shift_h: 'O ile godzin auto-stosowanie może przesunąć istniejące okno naraz (0 = bez limitu). Chroni przed dużymi skokami.',
      };
      const swState = (k) => { const s = st('switch', k); return s ? s.state : 'unavailable'; };
      const numState = (k) => { const s = st('number', k); return s ? s.state : ''; };
      const key = JSON.stringify([
        logSt && logSt.last_updated, entries.length, pToday && pToday.state, pMonth && pMonth.state,
        pTotal && pTotal.state, reserve && reserve.state,
        FEATURES.map(f => swState(f[0])), DAYS.map(d => swState(d[0])), NUMS.map(n => numState(n[0])),
        (st('sensor', 'monthly_report') || {}).last_updated, (st('sensor', 'battery_health') || {}).last_updated,
      ]);
      if (key === this._lastLogKey) return;
      this._lastLogKey = key;

      const tile = (label, value, sub) => `
        <div style="flex:1 1 130px;background:var(--surface);border-radius:14px;padding:12px 14px;min-width:120px;">
          <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;">${label}</div>
          <div style="font-size:20px;font-weight:700;margin-top:4px;">${value}</div>
          ${sub ? `<div style="font-size:11px;color:var(--muted);margin-top:2px;">${sub}</div>` : ''}
        </div>`;
      const colorOf = (v) => { const n = parseFloat(v); return isNaN(n) ? '#e5e5ea' : (n >= 0 ? '#34d399' : '#f87171'); };
      const moneyTile = (label, s, sub) => tile(label, `<span style="color:${colorOf(s && s.state)}">${this._money(s && s.state)}</span>`, sub);

      const ra = (reserve && reserve.attributes) || {};
      const pa = (pToday && pToday.attributes) || {};
      const tiles = `
        <div style="display:flex;gap:10px;flex-wrap:wrap;">
          ${moneyTile('Dziś', pToday, `eksport ${pa.export_kwh ?? 0} kWh · import ${pa.import_kwh ?? 0} kWh`)}
          ${moneyTile('Ten miesiąc', pMonth, '')}
          ${moneyTile('Łącznie', pTotal, '')}
          ${tile('Rezerwa SOC', reserve && reserve.state !== 'unknown' ? `${reserve.state}%` : '—',
            ra.storm ? '⛈ tryb burzowy — cała energia zostaje w baterii' : (ra.enabled ? `aktywna · potrzeba ${ra.need_kwh ?? '?'} kWh do ${ra.until_hour ?? '?'}:00` : 'wyłączona (podgląd)'))}
        </div>`;

      const bars = hist.length ? this._balanceSvg(hist, `Bilans dzienny (eksport × RCE − import × cena zakupu), ostatnie ${hist.length} dni`) :
        `<div class="chart-empty">Bilans zacznie się liczyć od teraz — dane pojawią się po kilku minutach.</div>`;

      const toggle = (eid, label, state, desc) => {
        const on = state === 'on';
        const dis = state === 'unavailable' || state === 'unknown';
        return `<button class="btn${on ? ' active' : ''}" data-switch="${this._esc(eid)}" ${dis ? 'disabled' : ''}
          style="padding:10px 12px;flex-direction:row;gap:8px;justify-content:flex-start;text-align:left;">
          <span>${on ? '✅' : '⬜'}</span><span class="label" style="font-size:12px;">${this._esc(label)}</span></button>`;
      };
      const featureBtns = FEATURES.map(f => toggle(this._eid('switch', f[0]), f[1], swState(f[0]))).join('')
        + `<details class="fx-help" style="grid-column:1/-1;flex-basis:100%;margin-top:4px;"><summary style="cursor:pointer;font-size:12px;color:var(--muted);">ℹ️ Co robi każda funkcja</summary>`
        + FEATURES.map(f => `<div class="fx-desc" data-fx="${this._esc(f[0])}" style="font-size:11.5px;color:var(--muted);line-height:1.45;padding:5px 0;border-bottom:1px solid var(--line);"><b style="color:var(--text);">${this._esc(f[1])}</b><br>${this._esc(DESC[f[0]] || '')}</div>`).join('')
        + `</details>`;
      const dayBtns = DAYS.map(d => {
        const on = swState(d[0]) === 'on';
        return `<button class="btn${on ? ' active' : ''}" data-switch="${this._esc(this._eid('switch', d[0]))}"
          style="padding:8px 0;min-width:44px;flex:1;"><span class="label">${d[1]}</span></button>`;
      }).join('');
      const numInputs = NUMS.map(n => `
        <label style="display:flex;justify-content:space-between;align-items:center;gap:10px;font-size:12px;color:#c7c7cc;padding:4px 0;">
          <span>${this._esc(n[1])}<small class="fx-ndesc" style="display:block;font-size:11px;color:var(--muted);line-height:1.4;margin-top:2px;max-width:420px;">${this._esc(NDESC[n[0]] || '')}</small></span>
          <input type="number" step="${n[2]}" data-number="${this._esc(this._eid('number', n[0]))}" value="${this._esc(numState(n[0]))}"
            style="width:90px;background:var(--input-bg);color:var(--text);border:1px solid var(--line);border-radius:8px;padding:6px 8px;">
        </label>`).join('');

      const LEVEL = { ok: '#34d399', warn: '#fbbf24', error: '#f87171', info: TC('muted') };
      const KIND = { schedule: 'harmonogram', guard: 'zabezpieczenie', price: 'cena', profit: 'opłacalność',
        reserve: 'rezerwa', command: 'komenda', verify: 'weryfikacja', auto: 'auto', system: 'system', plan: 'plan', notify: 'powiadomienie' };
      const rows = entries.length ? entries.map(e => {
        const d = new Date(e.ts);
        const when = isNaN(d) ? this._esc(e.ts) : d.toLocaleString('pl-PL', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' });
        return `<div style="display:flex;gap:8px;padding:6px 0;border-bottom:1px solid var(--line);font-size:12px;">
          <span style="width:6px;border-radius:3px;background:${LEVEL[e.level] || LEVEL.info};flex:none;"></span>
          <span style="color:var(--muted);white-space:nowrap;flex:none;">${when}</span>
          <span style="color:#a1a1aa;flex:none;min-width:78px;">${this._esc(KIND[e.kind] || e.kind)}</span>
          <span style="word-break:break-word;">${this._esc(e.msg)}</span></div>`;
      }).join('') : `<div class="chart-empty">Dziennik jest pusty.</div>`;

      // ---- co EMS zrobił dziś: ważne zdarzenia z dzisiejszej doby (komendy, zabezpieczenia, zmiany automatu, rozliczenie sprzedaży)
      const todayKey = new Date().toLocaleDateString('sv-SE');
      const IMPORTANT = new Set(['command', 'guard', 'auto', 'profit']);
      const todays = entries.filter(e => {
        const d = new Date(e.ts); if (isNaN(d) || d.toLocaleDateString('sv-SE') !== todayKey) return false;
        return IMPORTANT.has(e.kind) || e.level === 'warn' || e.level === 'error';
      }).sort((a, b) => String(b.ts).localeCompare(String(a.ts)));
      const cnt = (f) => todays.filter(f).length;
      const chip = (n, label, color) => n ? `<span style="font-size:11px;padding:3px 9px;border-radius:999px;background:${color}22;color:${color};font-weight:700;">${n} ${label}</span>` : '';
      const todayRows = todays.slice(0, 12).map(e => {
        const d = new Date(e.ts);
        return `<div style="display:flex;gap:8px;padding:6px 0;border-bottom:1px solid var(--line);font-size:12px;">
          <span style="width:6px;border-radius:3px;background:${LEVEL[e.level] || LEVEL.info};flex:none;"></span>
          <span style="color:var(--muted);white-space:nowrap;flex:none;">${d.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' })}</span>
          <span style="word-break:break-word;">${this._esc(e.msg)}</span></div>`;
      }).join('');
      const todayBox = todays.length
        ? `<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:6px;">${chip(cnt(e => e.kind === 'command'), 'komend', '#10b981')}${chip(cnt(e => e.kind === 'guard'), 'blokad / zabezpieczeń', '#f59e0b')}${chip(cnt(e => e.kind === 'auto'), 'zmian automatu', '#60a5fa')}${chip(cnt(e => e.level === 'warn' || e.level === 'error'), 'ostrzeżeń', '#f87171')}</div>${todayRows}${todays.length > 12 ? `<div style="font-size:11px;color:var(--muted);padding-top:6px;">…i ${todays.length - 12} więcej — pełna lista w dzienniku niżej.</div>` : ''}`
        : `<div class="chart-empty">Dziś EMS nie wykonał jeszcze żadnych komend ani zmian.</div>`;

      // kafelki Zysku i logu powstają od nowa — usuń stare kopie, także te przeniesione na inne zakładki (nowe trafią tam w _applyLayout)
      root.querySelectorAll('[data-tile^="log-"]').forEach((n) => { if (!body.contains(n)) n.remove(); });
      body.innerHTML = `
        <div class="section" data-tile="log-bilans" style="margin-top:6px;">
          <div class="section-title">💰 Bilans w PLN</div>
          <div class="chart-card full" style="padding:14px 16px;">${tiles}${bars}</div>
        </div>
        <div class="section" data-tile="log-today" id="logToday">
          <div class="section-title">🗓️ Co EMS zrobił dziś</div>
          <div class="chart-card full" style="padding:10px 16px;">${todayBox}</div>
        </div>
        <div class="section" data-tile="log-savings">
          <div class="section-title">💡 Oszczędności</div>
          <div class="chart-card full" style="padding:14px 16px;"><div id="exSavBox"><div class="chart-empty">Ładowanie…</div></div></div>
        </div>
        <div class="section" data-tile="log-sim">
          <div class="section-title">📆 Symulacja roczna i zwrot z inwestycji</div>
          <div class="chart-card full" style="padding:14px 16px;"><div id="exSimBox"><div class="chart-empty">Ładowanie…</div></div></div>
        </div>
        <div class="section" data-tile="log-accuracy">
          <div class="section-title">🎯 Trafność prognoz</div>
          <div class="chart-card full" style="padding:14px 16px;"><div id="exAccBox"><div class="chart-empty">Ładowanie…</div></div></div>
        </div>
        <div class="section" data-tile="log-report">
          <div class="section-title">📅 Raport miesięczny</div>
          <div class="chart-card full" style="padding:14px 16px;"><div id="exReportBox"><div class="chart-empty">Ładowanie…</div></div></div>
        </div>
        <div class="section" data-tile="log-health">
          <div class="section-title">🔋 Zdrowie i sprawność baterii</div>
          <div class="chart-card full" style="padding:14px 16px;"><div id="exHealthBox"><div class="chart-empty">Ładowanie…</div></div></div>
        </div>
        <div class="section" data-tile="log-auto">
          <div class="section-title">⚙️ Funkcje automatyczne</div>
          <div class="chart-card full" style="padding:14px 16px;">
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:8px;">${featureBtns}</div>
            <div style="font-size:11px;color:var(--muted);margin:12px 0 6px;">Dni, w których działają starty harmonogramu:</div>
            <div style="display:flex;gap:6px;">${dayBtns}</div>
            <div style="margin-top:12px;">${numInputs}</div>
            <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;">
              <button class="btn" data-service="auto_apply_now" style="padding:10px 14px;flex-direction:row;gap:8px;"><span>🤖</span><span class="label">Zastosuj propozycję teraz</span></button>
              <button class="btn" data-service="undo_auto_apply" style="padding:10px 14px;flex-direction:row;gap:8px;"><span>↩️</span><span class="label">Cofnij ostatnie auto-zmiany</span></button>
            </div>
            <div id="logToast" style="font-size:12px;color:var(--muted);margin-top:8px;min-height:16px;"></div>
          </div>
        </div>
        <div class="section" data-tile="log-journal">
          <div class="section-title">📋 Dziennik decyzji (ostatnie ${entries.length})</div>
          <div class="chart-card full" style="padding:8px 16px;max-height:520px;overflow-y:auto;">${rows}</div>
        </div>`;
      this._applyLayout();   // kafelki Zysku i logu powstają od nowa przy każdym rysowaniu — przywróć kolejność i ukrycia
      this._safe(() => this._exEnsure());
    }

    // ===== SHELL =====
    // ---------- motyw ----------
    _resolveTheme() {
      let saved = null;
      try { saved = localStorage.getItem(THEME_KEY); } catch (e) { /* storage niedostępny */ }
      if (saved === 'light' || saved === 'dark') return saved;
      if (this._hass && this._hass.themes && typeof this._hass.themes.darkMode === 'boolean') {
        return this._hass.themes.darkMode ? 'dark' : 'light';
      }
      try { return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'; } catch (e) { return 'dark'; }
    }
    _setTheme(mode, persist) {
      if (mode !== 'light' && mode !== 'dark') return;
      if (persist) { try { localStorage.setItem(THEME_KEY, mode); } catch (e) { /* ignoruj */ } PREFS.touch(); }
      this._applyTheme(mode);
    }
    _resolveSkin() {
      let v = null;
      try { v = localStorage.getItem(SKIN_KEY); } catch (e) { /* storage niedostępny */ }
      return Object.prototype.hasOwnProperty.call(SKINS, v) ? v : 'classic';
    }
    _setSkin(skin, persist = true) {
      if (!Object.prototype.hasOwnProperty.call(SKINS, skin)) return;
      if (persist) { try { localStorage.setItem(SKIN_KEY, skin); } catch (e) { /* ignoruj */ } PREFS.touch(); }
      this._applySkin(skin);
    }
    _applySkin(force) {
      const skin = force || this._resolveSkin();
      const prev = this.getAttribute('data-skin') || 'classic';
      if (skin === 'classic') this.removeAttribute('data-skin'); else this.setAttribute('data-skin', skin);
      if (prev !== skin) { this._lastFlowKey = null; this._lastM3Key = null; if (this._rendered) this._safe(() => this._drawPowerflow()); }
    }
    // ---------- układ panelu: kolejność, ukrywanie i przenoszenie kafelków między zakładkami ----------
    // Zapis: localStorage (cache) + dane użytkownika HA (PREFS) — układ podąża za kontem.
    // Model: order[zakładka] = kafelki leżące na tej zakładce, w tej kolejności. Kafelek wpisany pod CUDZĄ zakładką został tam przeniesiony
    // (ląduje na końcu); kafelek niewpisany nigdzie leży u siebie, w domyślnym miejscu — nowe kafelki z aktualizacji dochodzą więc na końcu
    // własnej zakładki. Kafelka „Pogoda” (zakładka „*”) nie da się przenieść.
    _layoutGroups() { return LAYOUT_TABS; }
    _layHomeOf(id) { return LAYOUT_HOME[id]; }
    _layLabel(id) { return LAYOUT_LABEL[id] || id; }
    _layTabLabel(tab) { return (LAYOUT_TABS.find((x) => x.tab === tab) || {}).label || tab; }
    // zakładka, na której kafelek leży teraz (po przeniesieniach); liczona w _applyLayout
    _layTabOf(id) { return (this._lay && this._lay.place[id]) || LAYOUT_HOME[id]; }
    // zakładka X „potrzebuje” rysowania kafelków zakładki home, gdy jest aktywna sama X albo leży na niej choć jeden kafelek z home
    _tabNeeds(home) { const a = this._activeTab; if (a === home) return true; const s = this._lay && this._lay.on[a]; return !!(s && s.has(home)); }
    _tileOn(id) { return this._layTabOf(id) === this._activeTab; }
    _laySimple() { try { return !!this._hass && this._simpleOn(); } catch (e) { return false; } }
    _layoutPlace(order) {
      const place = {};
      LAYOUT_TABS.forEach((g) => {
        const a = order && order[g.tab]; if (g.fixed || !Array.isArray(a)) return;
        a.forEach((id) => { const h = LAYOUT_HOME[id]; if (h && h !== '*' && h !== g.tab && !place[id]) place[id] = g.tab; });
      });
      return place;
    }
    _layoutLoad() {
      const out = { order: {}, hidden: [], place: {} };
      let j = null; try { j = JSON.parse(localStorage.getItem(LAYOUT_KEY) || 'null'); } catch (e) { j = null; }
      if (!j || typeof j !== 'object') return out;
      if (Array.isArray(j.hidden)) out.hidden = [...new Set(j.hidden.filter((id) => LAYOUT_HOME[id]))];
      if (j.order && typeof j.order === 'object') {
        out.place = this._layoutPlace(j.order);
        LAYOUT_TABS.forEach((g) => {
          const a = j.order[g.tab]; if (g.fixed || !Array.isArray(a)) return;
          const seen = new Set();
          out.order[g.tab] = a.filter((id) => LAYOUT_HOME[id] && (out.place[id] || LAYOUT_HOME[id]) === g.tab && !seen.has(id) && seen.add(id));
        });
      }
      return out;
    }
    // układ obowiązujący na ekranie: w trybie prostym przeniesienia są ignorowane (zakładki Plan / Log / Urządzenia nie istnieją)
    _layoutEff() { const L = this._layoutLoad(); if (this._laySimple()) L.place = {}; return L; }
    _layoutSave(L) {
      const place = this._layoutPlace(L.order);
      LAYOUT_TABS.forEach((g) => {
        const a = L.order[g.tab]; if (!Array.isArray(a)) return;
        // lista równa domyślnej niczego nie zmienia — nie zapisujemy jej (domyślna = własne kafelki zakładki, które nie wyjechały gdzie indziej)
        if (g.fixed || a.join() === g.tiles.map((t) => t[0]).filter((id) => !place[id]).join()) delete L.order[g.tab];
      });
      try {
        const empty = !L.hidden.length && !Object.keys(L.order).length;
        if (empty) localStorage.removeItem(LAYOUT_KEY); else localStorage.setItem(LAYOUT_KEY, JSON.stringify({ v: 2, order: L.order, hidden: L.hidden }));
      } catch (e) { /* storage niedostępny */ }
      PREFS.touch();
    }
    // pełna kolejność kafelków zakładki: zapisana, a niewpisane (własne, nieprzeniesione) dochodzą na końcu w domyślnym porządku
    _layoutOrder(g, L) {
      const place = (L && L.place) || {}, here = (id) => (place[id] || LAYOUT_HOME[id]) === g.tab, seen = new Set(), res = [];
      ((L && L.order && L.order[g.tab]) || []).forEach((id) => { if (here(id) && !seen.has(id)) { seen.add(id); res.push(id); } });
      g.tiles.forEach(([id]) => { if (here(id) && !seen.has(id)) { seen.add(id); res.push(id); } });
      return res;
    }
    _layoutState() {
      const L = this._layoutLoad(), orders = {};
      LAYOUT_TABS.forEach((g) => { orders[g.tab] = this._layoutOrder(g, L); });
      return { orders, place: L.place, hidden: new Set(L.hidden), custom: L.hidden.length > 0 || Object.keys(L.order).length > 0 };
    }
    _layoutMove(tab, id, dir) {
      const g = LAYOUT_TABS.find((x) => x.tab === tab); if (!g || g.fixed) return false;
      const L = this._layoutLoad(), ord = this._layoutOrder(g, L), i = ord.indexOf(id), j = i + (dir < 0 ? -1 : 1);
      if (i < 0 || j < 0 || j >= ord.length) return false;
      [ord[i], ord[j]] = [ord[j], ord[i]];
      L.order[g.tab] = ord; this._layoutSave(L); this._applyLayout(); return true;
    }
    // przeniesienie kafelka na inną zakładkę — ląduje na jej końcu
    _layoutMoveTo(id, tab) {
      const to = LAYOUT_TABS.find((x) => x.tab === tab && !x.fixed), home = LAYOUT_HOME[id];
      if (!to || !home || home === '*') return false;
      const L = this._layoutLoad(), from = LAYOUT_TABS.find((x) => x.tab === (L.place[id] || home));
      if (!from || from.tab === to.tab) return false;
      L.order[from.tab] = this._layoutOrder(from, L).filter((x) => x !== id);
      L.order[to.tab] = this._layoutOrder(to, L).filter((x) => x !== id).concat(id);
      this._layoutSave(L); this._applyLayout(); this._layRefreshTab();
      return true;
    }
    _layoutSetOrder(tab, ids) {
      const g = LAYOUT_TABS.find((x) => x.tab === tab); if (!g || g.fixed) return false;
      const L = this._layoutLoad(), cur = this._layoutOrder(g, L), ord = [];
      ids.forEach((id) => { if (cur.includes(id) && !ord.includes(id)) ord.push(id); }); cur.forEach((id) => { if (!ord.includes(id)) ord.push(id); });
      L.order[g.tab] = ord; this._layoutSave(L); this._applyLayout(); return true;
    }
    _layoutToggle(id) {
      if (!LAYOUT_HOME[id]) return false;
      const L = this._layoutLoad(), h = new Set(L.hidden);
      if (h.has(id)) h.delete(id); else h.add(id);
      L.hidden = [...h]; this._layoutSave(L); this._applyLayout(); return true;
    }
    // kafelek wraca na swoją zakładkę: jeśli ta ma własną listę kolejności, wstawiamy go na jego domyślne miejsce (a nie na koniec)
    _layBackHome(L, id) {
      const h = LAYOUT_HOME[id], g = LAYOUT_TABS.find((x) => x.tab === h), list = L.order[h];
      if (!g || !Array.isArray(list) || list.includes(id)) return;
      const def = g.tiles.map((t) => t[0]); let at = 0;
      for (let i = def.indexOf(id) - 1; i >= 0; i--) { const k = list.indexOf(def[i]); if (k >= 0) { at = k + 1; break; } }
      list.splice(at, 0, id);
    }
    _layoutReset(tab) {
      const L = this._layoutLoad();
      if (!tab) { L.order = {}; L.hidden = []; } else {
        const g = LAYOUT_TABS.find((x) => x.tab === tab); if (!g) return false;
        // własne kafelki zakładki wracają na nią, a obce, które tu leżą, wracają do swoich zakładek; wszystkie przestają być ukryte
        const mine = new Set(g.tiles.map((t) => t[0])), foreign = this._layoutOrder(g, L).filter((id) => !mine.has(id)), all = new Set([...mine, ...foreign]);
        delete L.order[tab];
        Object.keys(L.order).forEach((k) => { L.order[k] = L.order[k].filter((id) => !mine.has(id)); });
        foreign.forEach((id) => this._layBackHome(L, id));
        L.hidden = L.hidden.filter((id) => !all.has(id));
      }
      this._layoutSave(L); this._applyLayout(); this._layRefreshTab();
      return true;
    }
    // Rozmieszcza kafelki w DOM według układu; zwraca true, gdy któryś kafelek zmienił zakładkę (wtedy trzeba go narysować na nowym miejscu)
    _applyLayout() {
      const root = this.shadowRoot; if (!root) return false;
      const L = this._layoutEff(), hid = new Set(L.hidden), place = {}, on = {};
      let unhid = false, moved = false;
      LAYOUT_TABS.forEach((g) => { if (g.fixed) return; this._layoutOrder(g, L).forEach((id) => { place[id] = g.tab; (on[g.tab] || (on[g.tab] = new Set())).add(LAYOUT_HOME[id]); }); });
      this._lay = { place, on };
      LAYOUT_TABS.forEach((g) => {
        if (g.fixed) {
          g.tiles.forEach(([id]) => { const el = root.querySelector(`[data-tile="${id}"]`); if (el) { if (!hid.has(id) && el.hasAttribute('data-tile-off')) unhid = true; el.toggleAttribute('data-tile-off', hid.has(id)); } });
          return;
        }
        const tc = root.querySelector(`[data-tab-content="${g.tab}"]`); if (!tc) return;
        const cont = g.tab === 'log' ? tc.querySelector('#logTabBody') : tc;
        const ord = this._layoutOrder(g, L), def = g.tiles.map((t) => t[0]);
        const want = ord.map((id) => root.querySelector(`[data-tile="${id}"]`)).filter(Boolean);
        if (cont) {
          const cur = [...cont.children].filter((n) => n.dataset && n.dataset.tile);
          if (want.length !== cur.length || !want.every((n, i) => n === cur[i])) {
            // kafelki trafiają za ostatni kafelek zakładki (a gdy jej puste — na koniec kontenera); przeniesiony z innej zakładki ląduje więc na końcu
            const ref = cur.length ? cur[cur.length - 1].nextSibling : null;
            want.forEach((n) => { if (n.parentNode !== cont) moved = true; cont.insertBefore(n, ref); });
          }
        }
        const isDef = ord.join() === def.join() && !ord.some((id) => hid.has(id));
        want.forEach((n) => { const off = hid.has(n.dataset.tile); if (!off && n.hasAttribute('data-tile-off')) unhid = true; n.toggleAttribute('data-tile-off', off); n.removeAttribute('data-first'); });
        const vis = want.filter((n) => !hid.has(n.dataset.tile));
        tc.toggleAttribute('data-custom', !isDef);
        if (!isDef && vis[0]) vis[0].setAttribute('data-first', '');
        tc.toggleAttribute('data-all-hidden', ord.length > 0 && ord.every((id) => hid.has(id)));
        tc.toggleAttribute('data-empty', ord.length === 0);
      });
      if (this._layEdit) this._layEditInject();
      // pokazany ponownie lub przeniesiony kafelek mógł być rysowany, gdy był niewidoczny (szerokość 0) — wymuś ponowne rysowanie
      if (unhid || moved) { this._lastFlowKey = this._lastM3Key = this._lastLogKey = null; this._lastLoadConsKey = this._lastForecast7dKey = this._lastHourlyFcKey = this._lastPvProdKey = this._lastPriceTableKey = this._lastWeatherKey = null; }
      return moved;
    }
    // po zmianie układu: narysuj to, co trafiło na aktywną zakładkę (to samo, co przy wejściu na nią)
    _layRefreshTab() {
      if (this._tabNeeds('log')) { this._lastLogKey = null; this._safe(() => this._renderLogTab()); }
      if (this._tileOn('main-flow')) { if (!this._flowRaf) this._startFlowLoop(); } else this._stopFlowLoop();
      if (this._tabNeeds('ems') || this._tabNeeds('charts')) this._safe(() => this._exEnsure());
      if (this._tabNeeds('charts')) this._chartsEnter();
      this._render();
    }
    // wejście na zakładkę (kliknięcie w pasek): rysujemy to, czego potrzebują kafelki, które na niej leżą (własne i przeniesione)
    _tabEnter(tab) {
      if (this._layEdit) this._layEditBar();
      if (this._tabNeeds('log')) { this._lastLogKey = null; this._safe(() => this._renderLogTab()); }
      if (this._tileOn('main-flow')) this._startFlowLoop(); else this._stopFlowLoop();
      if (tab === 'diag') this._safe(() => this._dgOpen());
      else if (this._dg) this._dgDestroyChart();
      if (tab === 'ems' || tab === 'diag' || tab === 'charts' || this._tabNeeds('ems') || this._tabNeeds('charts')) this._safe(() => this._exEnsure());
      if (tab === 'dev') this._safe(() => this._devEnsure());
      if (this._tabNeeds('charts')) this._chartsEnter();
    }
    _chartsEnter() {
      this._lastLoadConsKey = null; this._lastForecast7dKey = null; this._lastHourlyFcKey = null; this._lastPvProdKey = null; this._lastPriceTableKey = null;
      if (!this._history24h) this._fetchHistory24h();
      if (!this._historyData) this._fetchHistoryData(this._historyRange);
      setTimeout(() => {
        this._renderLoadConsumptionChart(); this._renderForecast7dChart(); this._renderHourlyForecastChart();
        this._renderPvProductionChart(); this._renderPriceTable(); this._renderHistoryChart();
      }, 100);
    }
    // nowe ustawienia z konta (inne urządzenie): zastosuj motyw, styl i układ
    _prefsApplied() {
      this._applyTheme();
      if (!this._rendered) return;
      if (!this._layEdit) { this._applyLayout(); this._layRefreshTab(); }
      if (this._lookOpen) this._lookRender();
      if (this._activeTab === 'diag' && this._dgRenderSection) this._safe(() => this._dgRenderSection());
    }
    _prefsPull(force) { PREFS.pull(!!force); }
    // tekst o miejscu zapisu wyglądu (okno 🎨 i Ustawienia)
    _prefsNote() {
      return PREFS.active() ? 'Styl, motyw i układ zapisują się na Twoim koncie Home Assistant — widzisz je tak samo na każdym urządzeniu, a pozostali użytkownicy mają własny wygląd.'
        : 'Styl, motyw i układ zapisują się w tej przeglądarce (nie udało się połączyć z kontem Home Assistant — wygląd nie przejdzie na inne urządzenia).';
    }
    // ---------- okno „Wygląd” (🎨): styl, motyw, układ — dla każdego użytkownika, bez hasła ----------
    _lookRender() {
      const root = this.shadowRoot; if (!root) return;
      let ov = root.getElementById('lookOv');
      if (!ov) {
        ov = document.createElement('div'); ov.id = 'lookOv'; ov.className = 'inb-ov'; ov.hidden = true;
        ov.innerHTML = '<div class="inb" role="dialog" aria-modal="true" aria-label="Wygląd panelu"></div>';
        ov.addEventListener('click', (ev) => {
          if (ev.target === ov) { this._lookClose(); return; }
          const b = ev.target.closest ? ev.target.closest('[data-look]') : null; if (b) this._lookClick(b);
        });
        ov.addEventListener('keydown', (ev) => {
          if (ev.key === 'Escape') { ev.stopPropagation(); this._lookClose(); return; }
          if (ev.key !== 'Tab') return;
          const f = [...ov.querySelectorAll('button:not([disabled])')]; if (!f.length) return;
          const a = root.activeElement, i = f.indexOf(a);
          if (ev.shiftKey && i <= 0) { ev.preventDefault(); f[f.length - 1].focus(); } else if (!ev.shiftKey && i === f.length - 1) { ev.preventDefault(); f[0].focus(); }
        });
        root.appendChild(ov);
      }
      ov.hidden = !this._lookOpen;
      const btn = this._el('lookBtn'); if (btn) btn.setAttribute('aria-expanded', this._lookOpen ? 'true' : 'false');
      if (!this._lookOpen) return;
      const cur = this._resolveSkin(), th = this._resolveTheme(), st = this._layoutState();
      const skins = Object.keys(SKINS).map((k) => `<button type="button" class="look-sk ${cur === k ? 'on' : ''}" data-look="skin" data-skin="${k}" aria-pressed="${cur === k}"><b>${bmsEsc(SKINS[k])}</b><span>${bmsEsc(LOOK_SKIN_SUB[k] || '')}</span></button>`).join('');
      const hadFocus = ov.contains(root.activeElement) ? root.activeElement : null, fk = hadFocus && (hadFocus.dataset.look + '|' + (hadFocus.dataset.skin || hadFocus.dataset.m || ''));
      ov.firstChild.innerHTML = `<div class="inb-grip"></div><div class="inb-h"><b>🎨 Wygląd panelu</b><button type="button" class="inb-x" data-look="close" aria-label="Zamknij">✕</button></div>
        <div class="inb-body">
          <div class="inb-sec"><span>Styl</span></div><div class="look-skins">${skins}</div>
          <div class="inb-sec"><span>Motyw</span></div>
          <div class="look-row"><button type="button" data-look="theme" data-m="light" class="${th === 'light' ? 'on' : ''}" aria-pressed="${th === 'light'}">☀️ Jasny</button><button type="button" data-look="theme" data-m="dark" class="${th === 'dark' ? 'on' : ''}" aria-pressed="${th === 'dark'}">🌙 Ciemny</button></div>
          <div class="inb-sec"><span>Układ panelu</span></div>
          <div class="look-note">Przestawiaj, ukrywaj i przenoś na inne zakładki kafelki wykresów, planów i ustawień bezpośrednio na panelu. Ukrycie kafelka niczego nie wyłącza w EMS — alerty zawsze zostają.${st.custom ? ' Masz własny układ.' : ''}</div>
          <div class="inb-btns"><button type="button" class="ok" data-look="edit">✎ Edytuj układ na panelu</button><button type="button" data-look="reset-all" ${st.custom ? '' : 'disabled'}>↺ Przywróć domyślny</button></div>
          <div class="look-note" style="margin-top:10px;">${bmsEsc(this._prefsNote())}</div>
        </div>`;
      const f = fk && [...ov.querySelectorAll('[data-look]')].find((b) => (b.dataset.look + '|' + (b.dataset.skin || b.dataset.m || '')) === fk && !b.disabled);
      const target = f || ov.querySelector('.inb-x'); if (target && !hadFocus || f) target.focus();
    }
    _lookOpenSet(open) {
      this._lookOpen = !!open; this._lookRender();
      if (!open) { const b = this._el('lookBtn'); if (b && b.focus) b.focus(); }
    }
    _lookClose() { this._lookOpenSet(false); }
    _lookClick(b) {
      const a = b.dataset.look;
      if (a === 'close') this._lookClose();
      else if (a === 'skin') { this._setSkin(b.dataset.skin); this._lookRender(); }
      else if (a === 'theme') { this._setTheme(b.dataset.m, true); this._lookRender(); }
      else if (a === 'edit') { this._lookOpen = false; this._lookRender(); this._layEditOn(); }
      else if (a === 'reset-all') { this._layoutReset(); this._lookRender(); }
    }
    // ---------- tryb edycji układu na panelu ----------
    _layEditBar() {
      const bar = this._el('editBar'); if (!bar) return;
      bar.hidden = !this._layEdit; if (!this._layEdit) { bar.innerHTML = ''; return; }
      const g = LAYOUT_TABS.find((x) => x.tab === this._activeTab && !x.fixed);
      const mvHint = this._laySimple() ? '' : ' „⇄ Przenieś…” przenosi kafelek na koniec innej zakładki.';
      bar.innerHTML = `<div class="eb-t"><b>✎ Edycja układu.</b> Przeciągnij ⠿ albo użyj ↑ ↓.${mvHint} „Ukryj” chowa kafelek — zostaje szary pasek z „Pokaż”. ${g ? `Zakładka: <b>${bmsEsc(g.label)}</b>.` : 'Ta zakładka nie ma kafelków — wybierz inną na dolnym pasku.'}<div class="eb-n" id="ebNote" aria-live="polite">${bmsEsc(this._layNote || '')}</div></div>
        <button type="button" data-lay="reset-tab" ${g ? '' : 'disabled'}>↺ Ta zakładka</button><button type="button" class="ok" data-lay="done">Gotowe</button>`;
    }
    _layEditOn() {
      const app = this.shadowRoot && this.shadowRoot.querySelector('.app'); if (!app) return;
      this._layEdit = true; app.setAttribute('data-edit', '');
      if (!LAYOUT_TABS.some((g) => g.tab === this._activeTab && !g.fixed)) { const m = this.shadowRoot.querySelector('.tab[data-tab="main"]'); if (m) m.click(); }
      this._applyLayout(); this._layEditBar();
      const ok = this.shadowRoot.querySelector('#editBar [data-lay="done"]'); if (ok && ok.focus) ok.focus();
    }
    _layEditOff() {
      const app = this.shadowRoot && this.shadowRoot.querySelector('.app'); if (!app) return;
      this._layEdit = false; app.removeAttribute('data-edit'); this._layNote = '';
      this.shadowRoot.querySelectorAll('.tile-ctl').forEach((n) => n.remove());
      this._layEditBar(); this._applyLayout();
      if (this._tabNeeds('log')) { this._lastLogKey = null; this._safe(() => this._renderLogTab()); }   // w trakcie edycji dziennik nie był odświeżany
    }
    _layEditInject() {
      const root = this.shadowRoot; if (!root) return;
      const L = this._layoutEff(), hid = new Set(L.hidden), simple = this._laySimple();
      LAYOUT_TABS.forEach((g) => {
        const ord = this._layoutOrder(g, L);
        ord.forEach((id) => {
          const tile = root.querySelector(`[data-tile="${id}"]`); if (!tile) return;
          let ctl = tile.querySelector(':scope > .tile-ctl');
          if (!ctl) { ctl = document.createElement('div'); ctl.className = 'tile-ctl'; tile.insertBefore(ctl, tile.firstChild); }
          ctl.dataset.ctlFor = id;
          const nm = bmsEsc(LAYOUT_LABEL[id] || id), i = ord.indexOf(id), off = hid.has(id), home = LAYOUT_HOME[id];
          const homeLbl = (LAYOUT_TABS.find((x) => x.tab === home) || {}).label || home;
          const from = !g.fixed && home !== g.tab ? ` <small>(z: ${bmsEsc(homeLbl)})</small>` : '';
          const mv = g.fixed ? '' : `<button type="button" data-lay="up" aria-label="Przesuń wyżej: ${nm}" title="Wyżej" ${i <= 0 ? 'disabled' : ''}>↑</button><button type="button" data-lay="down" aria-label="Przesuń niżej: ${nm}" title="Niżej" ${i >= ord.length - 1 ? 'disabled' : ''}>↓</button>`;
          const mt = g.fixed || simple ? '' : `<select data-lay="move" aria-label="Przenieś na zakładkę: ${nm}" title="Przenieś na inną zakładkę (na jej koniec)"><option value="">⇄ Przenieś…</option>${LAYOUT_TABS.filter((x) => !x.fixed && x.tab !== g.tab).map((x) => `<option value="${x.tab}">${bmsEsc(x.label)}${x.tab === home ? ' (domyślna)' : ''}</option>`).join('')}</select>`;
          const html = `${g.fixed ? '' : '<span class="tc-h" role="img" aria-label="Przeciągnij, aby przestawić" title="Przeciągnij">⠿</span>'}<span class="tc-n">${nm}${from}</span><span class="tc-b">${mv}${mt}<button type="button" class="tc-eye" data-lay="eye" aria-label="${off ? 'Pokaż' : 'Ukryj'}: ${nm}">${off ? '👁 Pokaż' : '✕ Ukryj'}</button></span>`;
          if (ctl.dataset.h !== html) { ctl.innerHTML = html; ctl.dataset.h = html; }   // bez zbędnego przerysowania (otwarta lista wyboru, fokus)
        });
      });
    }
    _layWire(wrap) {
      wrap.addEventListener('click', (ev) => {
        const b = ev.target && ev.target.closest ? ev.target.closest('[data-lay]') : null; if (!b || !this._layEdit) return;
        const a = b.dataset.lay, ctl = b.closest('.tile-ctl'), id = ctl && ctl.dataset.ctlFor;
        if (a === 'move') return;   // lista wyboru obsługiwana w „change”
        if (a === 'done') { this._layEditOff(); return; }
        if (a === 'reset-tab') { this._layoutReset(this._activeTab); return; }
        if (!id) return;
        if (a === 'up' || a === 'down') this._layoutMove(this._layTabOf(id), id, a === 'up' ? -1 : 1);
        else if (a === 'eye') this._layoutToggle(id);
        // kontrolki są rysowane od nowa — oddaj fokus temu samemu przyciskowi i zostaw kafelek w zasięgu wzroku
        const tile = this.shadowRoot.querySelector(`[data-tile="${id}"]`);
        if (tile) {
          const nb = tile.querySelector(`:scope > .tile-ctl [data-lay="${a}"]:not([disabled])`) || tile.querySelector(':scope > .tile-ctl [data-lay="eye"]');
          if (nb && nb.focus) nb.focus({ preventScroll: true });
          if (a !== 'eye') this._layReveal(tile);
        }
      });
      wrap.addEventListener('change', (ev) => {
        const sel = ev.target && ev.target.closest ? ev.target.closest('select[data-lay="move"]') : null; if (!sel || !this._layEdit) return;
        const ctl = sel.closest('.tile-ctl'), id = ctl && ctl.dataset.ctlFor, to = sel.value; if (!id || !to) return;
        const lbl = (t) => (LAYOUT_TABS.find((x) => x.tab === t) || {}).label || t;
        if (this._layoutMoveTo(id, to)) {
          this._layNote = `Przeniesiono „${LAYOUT_LABEL[id]}” na zakładkę ${lbl(to)} — jest na jej końcu.`;
          const n = this.shadowRoot.getElementById('ebNote'); if (n) n.textContent = this._layNote;
        } else sel.value = '';
      });
      wrap.addEventListener('pointerdown', (ev) => {
        const h = ev.target && ev.target.closest ? ev.target.closest('.tc-h') : null;
        if (h && this._layEdit) this._layDragStart(ev, h);
      });
      this.shadowRoot.addEventListener('toggle', (ev) => { const d = ev.target; if (d && d.matches && d.matches('details[data-ps]')) { try { localStorage.setItem('bms_ps_open', d.open ? '1' : '0'); } catch (e) { /* ignorujemy */ } } }, true);
      this.shadowRoot.addEventListener('keydown', (ev) => { if (ev.key === 'Escape' && this._layEdit && !this._lookOpen) this._layEditOff(); });
    }
    // Pokaż kafelek w widocznej części ekranu: pod paskiem edycji i nad dolnym marginesem.
    // Liczone ręcznie, bo scrollIntoView + scroll-margin bywa ignorowane (shadow DOM, starsze przeglądarki).
    _layReveal(tile) {
      if (!tile || !tile.getBoundingClientRect) return;
      const bar = this.shadowRoot.getElementById('editBar');
      const top = (bar && !bar.hidden ? bar.getBoundingClientRect().bottom : 0) + 8;
      const bottom = (window.innerHeight || 800) - 90;
      const r = tile.getBoundingClientRect();
      let d = 0;
      if (r.top < top) d = r.top - top;
      else if (r.bottom > bottom) d = Math.min(r.bottom - bottom, r.top - top);
      if (d) { const sp = this._scrollParent(tile); sp.scrollTop += d; }
    }
    _scrollParent(el) {
      let n = el;
      while (n) {
        n = n.parentNode || n.host;
        if (n && n.nodeType === 1) { const o = getComputedStyle(n).overflowY; if ((o === 'auto' || o === 'scroll') && n.scrollHeight > n.clientHeight + 1) return n; }
      }
      return document.scrollingElement || document.documentElement;
    }
    _layDragStart(ev, handle) {
      if (ev.button !== undefined && ev.button !== 0) return;
      const ctl = handle.closest('.tile-ctl'), tile = ctl && ctl.parentElement, cont = tile && tile.parentElement;
      if (!tile || !tile.dataset.tile || !cont) return;
      ev.preventDefault();
      try { handle.setPointerCapture(ev.pointerId); } catch (e) { /* brak przechwytu — działamy na zdarzeniach uchwytu */ }
      tile.classList.add('tile-drag');
      const sibs = () => [...cont.children].filter((n) => n.dataset && n.dataset.tile);
      const sp = this._scrollParent(tile);
      let y = ev.clientY, timer = null;
      const swap = () => {
        const s = sibs(), i = s.indexOf(tile), prev = s[i - 1], next = s[i + 1];
        // przestawiamy sąsiadów, a nie przeciągany kafelek — jego węzeł (z uchwytem) zostaje w DOM, więc przechwycenie wskaźnika nie jest zrywane
        if (prev) { const r = prev.getBoundingClientRect(); if (y < r.top + r.height / 2) { cont.insertBefore(prev, tile.nextSibling); return; } }
        if (next) { const r = next.getBoundingClientRect(); if (y > r.top + r.height / 2) cont.insertBefore(next, tile); }
      };
      const edge = () => { const vh = window.innerHeight || 800; if (y < 80) sp.scrollTop -= 14; else if (y > vh - 90) sp.scrollTop += 14; };
      const move = (e) => { y = e.clientY; swap(); };
      const done = () => {
        handle.removeEventListener('pointermove', move); handle.removeEventListener('pointerup', done); handle.removeEventListener('pointercancel', done);
        clearInterval(timer); tile.classList.remove('tile-drag');
        try { handle.releasePointerCapture(ev.pointerId); } catch (e) { /* ignoruj */ }
        this._layoutSetOrder(this._layTabOf(tile.dataset.tile), sibs().map((n) => n.dataset.tile));
      };
      handle.addEventListener('pointermove', move); handle.addEventListener('pointerup', done); handle.addEventListener('pointercancel', done);
      timer = setInterval(() => { edge(); swap(); }, 40);
    }
    _applyTheme(force) {
      const mode = force || this._resolveTheme();
      const changed = THEME.mode !== mode || this.getAttribute('data-theme') !== mode;
      THEME.mode = mode;
      this.setAttribute('data-theme', mode);
      this._applySkin();
      if (this.shadowRoot) {
        this.shadowRoot.querySelectorAll('[data-theme-set]').forEach(b => b.classList.toggle('active', b.dataset.themeSet === mode));
      }
      if (!changed || !this._rendered) return;
      // wykresy trzymają kolory w instancjach / cache — wymuś ponowne rysowanie
      this._lastLoadConsKey = this._lastForecast7dKey = this._lastHourlyFcKey = this._lastPvProdKey = null;
      this._lastPriceTableKey = this._lastWeatherKey = this._lastLogKey = this._lastFlowKey = null;
      this._safe(() => {
        if (this._chartJsInstance) { this._chartJsInstance.destroy(); this._chartJsInstance = null; }
        this._render();
        if (this._tabNeeds('charts')) {
          this._renderLoadConsumptionChart(); this._renderForecast7dChart();
          this._renderHourlyForecastChart(); this._renderPvProductionChart(); this._renderPriceTable();
          if (this._historyData) this._renderHistoryChart();
        }
        if (this._tabNeeds('log')) this._renderLogTab();
      });
    }

    _renderShell() {
      const style = document.createElement('style');
      style.textContent = STYLES + SKIN_M3 + SKIN_COMMON + SKIN_GLASS + SKIN_MATRIX + SKIN_SPACE + SKIN_COMFORT + SKIN_HERO;
      this.shadowRoot.appendChild(style);

      const wrap = document.createElement('div');
      wrap.className = 'app';
      wrap.innerHTML = `
        <div class="header">
          <div>
            <div class="title" role="img" aria-label="Komp-Dec – Centrum Energii" title="Komp-Dec – Centrum Energii"><svg class="logo" viewBox="0 0 300 64" aria-hidden="true"><g transform="translate(0 2) scale(.6)"><path d="M50 10 L84 30 V70 L50 90 L16 70 V30 Z" fill="#0F6E56"/><path d="M36 36 V64 M36 36 L58 36 M36 50 L54 50 M36 64 L58 64" fill="none" stroke="#9FE1CB" stroke-width="7" stroke-linecap="round"/><path d="M70 40 L62 52 H68 L65 62 L76 49 H70 Z" fill="#EF9F27"/></g><text x="70" y="42" font-size="32" font-weight="500" fill="var(--text)">Komp-Dec</text></svg></div>
            <div class="date" id="date"></div>
          </div>
          <div class="hdr-r">
          <button type="button" class="bell" id="lookBtn" aria-label="Wygląd panelu" aria-haspopup="dialog" title="Wygląd panelu: styl, motyw, układ kafelków">🎨</button>
          <button type="button" class="bell" id="bell" aria-label="Powiadomienia i propozycje" title="Powiadomienia i propozycje">🔔<span class="bell-n" id="bellN" hidden></span></button>
          <div class="theme-seg" role="group" aria-label="Motyw">
            <button type="button" data-theme-set="light" title="Jasny" aria-label="Motyw jasny">☀️</button>
            <button type="button" data-theme-set="dark" title="Ciemny" aria-label="Motyw ciemny">🌙</button>
          </div>
          </div>
        </div>
        <div class="edit-bar" id="editBar" role="region" aria-label="Edycja układu panelu" hidden></div>
        <nav class="tabs bottom" id="tabsNav">
          <button class="tab active" data-tab="main" title="Główny" aria-label="Główny"><span class="ti">${TAB_SVG.main}</span><span class="tl">Główny</span><span class="tls">Główny</span></button>
          <button class="tab" data-tab="charts" title="Plan i wykresy" aria-label="Plan i wykresy"><span class="ti">${TAB_SVG.charts}</span><span class="tl">Plan</span><span class="tls">Plan</span></button>
          <button class="tab" data-tab="log" title="Zysk i log" aria-label="Zysk i log"><span class="ti">${TAB_SVG.log}</span><span class="tl">Zysk i log</span><span class="tls">Zysk</span></button>
          <button class="tab" data-tab="settings" id="tabSettings" title="Ustawienia" aria-label="Ustawienia"><span class="ti">${TAB_SVG.diag}</span><span class="tl">Ustawienia</span><span class="tls">Ustaw.</span></button>
          <button class="tab sub" data-tab="ems" title="Ustawienia EMS (sprzedaż, ładowanie, harmonogram)" aria-label="EMS"><span class="ti">${TAB_SVG.ems}</span><span class="tl">EMS</span><span class="tls">EMS</span></button>
          <button class="tab sub" data-tab="dev" id="tabDev" title="Urządzenia" aria-label="Urządzenia"><span class="ti">${TAB_SVG.dev}</span><span class="tl">Urządzenia</span><span class="tls">Urządz.</span></button>
          <button class="tab sub" data-tab="diag" id="tabDiag" style="display:none;" title="Ustawienia panelu i diagnostyka" aria-label="Ustawienia"><span class="ti">${TAB_SVG.diag}</span><span class="tl">Ustawienia</span><span class="tls">Ustaw.</span></button>
        </nav>

        <div class="price-bar" id="priceBar" style="display:none;"></div>
        <div class="floor-alert" id="floorAlert" style="display:none;"></div>
        <div class="status-banner" id="statusBanner" style="display:none;"></div>

        <!-- Pogoda na samej górze -->
        <div class="weather-global" data-tile="weather">
          <div class="section-title">Pogoda i prognoza PV (7 dni)</div>
          <div class="weather-scroll" id="weatherContainer"></div>
        </div>

        <div class="tab-content" data-tab-content="main">
          <div class="why-box" id="whyBox" style="display:none;" aria-live="polite"></div>
          <!-- Aktywne funkcje przeniesione pod pogodę -->
          <div class="section" data-tile="main-active" style="margin-top:6px;">
            <div class="section-title">Aktywne funkcje</div>
            <div class="active-badges">
              <div class="badge" id="badge-sprzedaz-1">Sprzedaż (1)</div>
              <div class="badge" id="badge-sprzedaz-2">Sprzedaż (2)</div>
              <div class="badge" id="badge-laduj-1">Ładowanie (1)</div>
              <div class="badge" id="badge-laduj-2">Ładowanie (2)</div>
              <div class="badge" id="badge-force-charge">Wymuś ładowanie</div>
              <div class="badge" id="badge-blokada-pv">Blokada PV</div>
              <div class="badge" id="badge-ladowanie-siec">Ładowanie z sieci</div>
              <div class="badge-none" id="badge-none">Żadna funkcja nie jest teraz włączona</div>
            </div>
            <div class="badge-warn" id="warn-sprzedaz-zablokowana"><div class="badge danger on" id="badge-sprzedaz-zablokowana">⛔ Sprzedaż zablokowana (import)</div></div>
            <div class="badge-warn" id="warn-grid-batt"><div class="badge danger on" id="badge-grid-batt"></div></div>
            <div id="autonomyBox" data-role="autonomy" style="display:none;margin-top:8px;font-size:13px;"></div>
          </div>

          <!-- Przepływ mocy (węzły) -->
          <div class="section" data-tile="main-flow" style="margin-top:6px;">
            <div class="chart-card full nodes-card"><div id="nodesBox"></div><div id="nodePop" class="node-pop" hidden></div></div>
          </div>
          <div class="section" data-tile="main-plan">
            <div class="section-title">Plan dnia</div>
            <div id="exMainBox"></div>
            <div class="chart-card full" style="padding:6px 20px 12px;"><div id="planBox"></div></div>
          </div>
        </div>

        <div class="tab-content" data-tab-content="charts" style="display:none;">
          <div class="section" data-tile="ch-plan24" style="margin-top:6px;">
            <div class="section-title">📈 Plan na najbliższe 24 h</div>
            <div class="chart-card full" style="padding:14px 16px;"><div id="exPlanBox"><div class="chart-empty">Ładowanie planu…</div></div></div>
          </div>
          <div class="section" data-tile="ch-hourly">
            <div class="section-title">🗓 Plan godzina po godzinie</div>
            <div class="chart-card full" style="padding:14px 16px;"><div id="exTblBox"><div class="chart-empty">Ładowanie…</div></div></div>
          </div>
          <div class="section" data-tile="ch-override">
            <div class="section-title">🧭 Ręczne nadpisanie planu</div>
            <div class="chart-card full" style="padding:14px 16px;"><div id="exOvrBox"><div class="chart-empty">Ładowanie…</div></div></div>
          </div>
          <div class="section" data-tile="ch-history7">
            <div class="section-title">🔋 Historia poziomu baterii (7 dni)</div>
            <div class="chart-card full" style="padding:14px 16px;"><div id="exHistBox"><div class="chart-empty">Ładowanie…</div></div></div>
          </div>

          
          <div class="section" data-tile="ch-energy" style="margin-top:6px;">
            <div class="section-title">Historia energii i cen</div>
            <div class="chart-card full">
              <div class="chart-head">
                <span>📈 Przebieg mocy, SOC i cen</span>
                <div class="time-selector">
                  <button class="time-btn active" data-range="1D">1D</button>
                  <button class="time-btn" data-range="7D">7D</button>
                  <button class="time-btn" data-range="30D">30D</button>
                  <button class="time-btn" data-range="90D">90D</button>
                </div>
              </div>
              <div class="chart-box"><canvas id="historyChart"></canvas></div>
              <div class="chart-footer" style="justify-content:flex-start; gap:12px; font-size:11px; padding-top:12px;">
                <span class="stat"><span class="dot" style="background:${COLORS.histPrice};"></span>CENA RCE (BRUTTO)</span>
                <span class="stat"><span class="dot" style="background:${COLORS.histPv};"></span>PRODUKCJA PV</span>
                <span class="stat"><span class="dot" style="background:${COLORS.histLoad};"></span>ZUŻYCIE DOMU</span>
                <span class="stat"><span class="dot" style="background:${COLORS.histSoc};"></span>POZIOM MAGAZYNU (SOC)</span>
                <span class="stat"><span class="dot" style="background:${COLORS.histSell};"></span>SPRZEDAŻ DO SIECI</span>
                <span class="stat"><span class="dot" style="background:#444; border:1px solid #666;"></span>DZIEŃ / NOC</span>
              </div>
            </div>
          </div>

          <div class="section" data-tile="ch-loadcons">
            <div class="section-title">Zużycie domu — wczoraj / dziś / jutro</div>
            <div class="chart-card full">
              <div class="chart-head"><span>🏠 Porównanie</span><span class="sub" id="loadConsSub">—</span></div>
              <canvas id="chartLoadCons"></canvas>
              <div class="chart-footer" style="border-top:0;margin-top:2px;padding-top:2px;"><span class="stat"><i class="dot" style="background:#34d399"></i>rzeczywiste</span><span class="stat"><i class="dot" style="background:#60a5fa"></i>prognoza wydana dzień wcześniej</span><span class="stat"><i class="dot" style="background:#ff9f0a"></i>tempo dnia (szacunek na koniec doby)</span><span class="stat"><i class="dot" style="background:#fbbf24"></i>jutro — prognoza i zakres</span></div>
              <div class="chart-footer" id="loadConsFooter"></div>
              <details class="lh-wrap"><summary>Ostatnie 14 dni: rzeczywiste vs prognoza</summary><div id="loadHistTable"></div></details>
            </div>
          </div>
          <div class="section" data-tile="ch-fc7d">
            <div class="section-title">Prognoza 7-dniowa zużycia domu</div>
            <div class="chart-card full">
              <div class="chart-head"><span>📅 Najbliższe 7 dni</span><span class="sub">kWh / dzień</span></div>
              <canvas id="chartForecast7d"></canvas>
              <div class="chart-footer" style="border-top:0;margin-top:2px;padding-top:2px;"><span class="stat"><i class="dot" style="background:#60a5fa"></i>prognoza dnia</span><span class="stat"><i class="dot" style="background:#fbbf24"></i>dziś / jutro</span></div>
            </div>
          </div>
          <div class="section" data-tile="ch-hourly-today">
            <div class="section-title">Profil godzinowy dziś</div>
            <div class="chart-card full">
              <div class="chart-head"><span>⏰ Prognoza godzinowa — dziś</span><span class="sub" id="hourlyTodaySub">—</span></div>
              <canvas id="chartHourlyToday"></canvas>
              <div class="chart-footer" style="border-top:0;margin-top:2px;padding-top:2px;"><span class="stat"><i class="dot" style="background:#60a5fa"></i>prognoza na dziś (kWh na godzinę)</span><span class="stat"><i class="dot" style="background:#fbbf24"></i>szczyt (≥ 70% maksimum)</span><span class="stat" id="hfcLegActual"><i class="dot" style="width:14px;height:3px;border-radius:2px;background:var(--hfc-today)"></i>rzeczywiste zużycie</span></div>
              <div id="hourlyTodayTable" class="hfc-wrap" role="group" aria-label="Tabela godzin dziś: prognoza i zużycie w Wh"></div>
            </div>
          </div>
          <div class="section" data-tile="ch-hourly-tomorrow">
            <div class="section-title">Profil godzinowy jutra</div>
            <div class="chart-card full">
              <div class="chart-head"><span>⏰ Prognoza godzinowa — jutro</span><span class="sub" id="hourlyFcSub">—</span></div>
              <canvas id="chartHourlyFc"></canvas>
              <div class="chart-footer" style="border-top:0;margin-top:2px;padding-top:2px;"><span class="stat"><i class="dot" style="background:#60a5fa"></i>jutro — prognoza (kWh na godzinę)</span><span class="stat"><i class="dot" style="background:#fbbf24"></i>szczyt (≥ 70% maksimum)</span></div>
              <div id="hourlyFcTable" class="hfc-wrap" role="group" aria-label="Tabela godzin jutro: prognoza w Wh"></div>
            </div>
          </div>
          <div class="section" data-tile="ch-pvprod">
            <div class="section-title" id="pvProdTitle">Produkcja PV dziś — rzeczywista vs prognoza (kWh/h)</div>
            <div class="chart-card full">
              <div class="chart-head"><span>☀️ Produkcja PV</span><span class="sub" id="pvProdSub">—</span></div>
              <div id="pvRangeBar" style="display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:2px 0 8px;">
                <button class="btn" data-pvr="prev" style="padding:5px 10px;" aria-label="Wcześniej">‹</button>
                <button class="btn" data-pvr="yesterday" style="padding:5px 10px;">Wczoraj</button>
                <button class="btn" data-pvr="today" style="padding:5px 10px;">Dziś</button>
                <button class="btn" data-pvr="tomorrow" style="padding:5px 10px;">Jutro</button>
                <button class="btn" data-pvr="7" style="padding:5px 10px;">7 dni</button>
                <button class="btn" data-pvr="30" style="padding:5px 10px;">30 dni</button>
                <input type="date" id="pvDate" aria-label="Wybierz dzień" style="padding:4px 6px;border-radius:8px;border:1px solid var(--border,#444);background:var(--surface,#222);color:inherit;" />
                <button class="btn" data-pvr="next" style="padding:5px 10px;" aria-label="Później">›</button>
              </div>
              <canvas id="chartPvProd24h"></canvas>
            </div>
          </div>
          <div class="section" data-tile="ch-prices">
            <div class="section-title">Ceny sprzedaży prądu — dziś vs jutro</div>
            <div class="chart-card full" style="padding:14px 16px;">
              <div id="priceTableHeader" class="price-header">Ceny sprzedaży > Teraz: -- PLN/kWh</div>
              <div id="priceTableContainer"></div>
            </div>
          </div>
        </div>

        <div class="tab-content" data-tab-content="log" style="display:none;">
          <div id="logTabBody"><div class="chart-empty">Ładowanie…</div></div>
        </div>

        <div class="tab-content" data-tab-content="settings" style="display:none;">
          <input type="search" class="set-search" id="setSearch" placeholder="🔍 Szukaj opcji, np. marża, rezerwa, ładowanie…" aria-label="Szukaj w ustawieniach" autocomplete="off">
          <div class="set-found" id="setFound" hidden></div>
          <div class="set-hub" id="setHub" role="list">
            <button type="button" class="hub-item" data-hub="ems" role="listitem"><span class="hub-ic">⚡</span><span class="hub-tx"><b>EMS: sprzedaż i ładowanie</b><small>profile, harmonogram, sprzedaż, ładowanie z sieci, ochrona przyłącza</small></span><span class="hub-ar">›</span></button>
            <button type="button" class="hub-item" data-hub="dev" id="hubDev" role="listitem"><span class="hub-ic">🔌</span><span class="hub-tx"><b>Urządzenia</b><small>bojler, EV, pompa ciepła, flota</small></span><span class="hub-ar">›</span></button>
            <button type="button" class="hub-item" data-hub="look" role="listitem"><span class="hub-ic">🎨</span><span class="hub-tx"><b>Wygląd panelu</b><small>styl karty, motyw, układ kafelków</small></span><span class="hub-ar">›</span></button>
            <button type="button" class="hub-item" data-hub="diag" id="hubDiag" role="listitem" style="display:none;"><span class="hub-ic">🛠</span><span class="hub-tx"><b>Serwis i diagnostyka</b><small>tylko administrator</small></span><span class="hub-ar">›</span></button>
          </div>
        </div>
        <div class="tab-content" data-tab-content="diag" style="display:none;"><button type="button" class="set-back" data-hub-back>‹ Ustawienia</button><div id="diagRoot"></div></div>
        <div class="tab-content" data-tab-content="dev" style="display:none;"><button type="button" class="set-back" data-hub-back>‹ Ustawienia</button><div id="devRoot"></div></div>

        <div class="tab-content" data-tab-content="ems" style="display:none;">
          <button type="button" class="set-back" data-hub-back>‹ Ustawienia</button>
          <div class="simple-wrap" id="simpleWrap" style="display:none;"></div>
          <div class="section" data-tile="ems-profiles">
            <div class="section-title">🎛 Profile pracy</div>
            <div class="chart-card full" style="padding:14px 16px;"><div id="exProfBox"><div class="chart-empty">Ładowanie…</div></div></div>
          </div>
          <div class="section" data-tile="ems-backup">
            <div class="section-title">💾 Kopia ustawień</div>
            <div class="chart-card full" style="padding:14px 16px;"><div id="exBackupBox"></div></div>
          </div>
          <div class="section" data-tile="ems-schedule">
            <div class="section-title">🤖 Inteligentny harmonogram</div>
            <div class="chart-card full" style="padding:14px 16px;">
              <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:10px;">
                <div style="font-size:12px;color:var(--muted);flex:1;min-width:180px;">
                  Analizuje prognozy PV, zużycia domu, cen G12w i RCE. <span id="suggLastAt"></span>
                </div>
                <button class="btn" id="btn-suggest" style="padding:10px 16px;flex-direction:row;gap:8px;">
                  <span style="font-size:16px;">✨</span><span class="label">Zaproponuj</span>
                </button>
              </div>
              <div id="suggestResults" style="font-size:13px;"></div>
            </div>
          </div>

          <div class="section" data-tile="ems-sell">
            <div class="section-title">🔋 Przełączniki sprzedaży</div>
            <div class="action-grid">
              <button class="btn" id="btn-sprzedaz-1"><div class="icon">🔋</div><div class="label">Sprzedaż (1)<br><span id="txt-sprzedaz-1">wyłączono</span></div></button>
              <button class="btn" id="btn-sprzedaz-2"><div class="icon">🔋</div><div class="label">Sprzedaż (2)<br><span id="txt-sprzedaz-2">wyłączono</span></div></button>
              <button class="btn" id="btn-script-9700"><div class="icon">⚡</div><div class="label">Sprzedaż Automatyczna</div></button>
              <button class="btn" id="btn-script-6000"><div class="icon">💵</div><div class="label">Sprzedaż 6000W</div></button>
            </div>
            <div class="row"><div class="field-info"><div class="name">Start sprzedaży 1</div><div class="eid-hint" id="eid-bateria_sprzedaz_start"></div></div>
              <div class="field-controls"><input type="time" data-time-key="bateria_sprzedaz_start"></div></div>
            <div class="row"><div class="field-info"><div class="name">Stop sprzedaży 1</div><div class="eid-hint" id="eid-bateria_sprzedaz_stop"></div></div>
              <div class="field-controls"><input type="time" data-time-key="bateria_sprzedaz_stop"></div></div>
            <div class="row"><div class="field-info"><div class="name">Start sprzedaży 2</div><div class="eid-hint" id="eid-bateria_sprzedaz_start_2"></div></div>
              <div class="field-controls"><input type="time" data-time-key="bateria_sprzedaz_start_2"></div></div>
            <div class="row"><div class="field-info"><div class="name">Stop sprzedaży 2</div><div class="eid-hint" id="eid-bateria_sprzedaz_stop_2"></div></div>
              <div class="field-controls"><input type="time" data-time-key="bateria_sprzedaz_stop_2"></div></div>
            <div class="row">
              <div class="field-info">
                <div class="name">Blokada sprzedaży — próg importu</div>
                <div class="eid-hint" id="eid-grid_import_sell_block_w"></div>
              </div>
              <div class="field-controls">
                <input type="number" min="0" max="50000" step="100" data-num-key="grid_import_sell_block_w">
                <span style="color:var(--muted);">W</span>
              </div>
            </div>
            <div class="row">
              <div class="field-info">
                <div class="name">Blokada sprzedaży — import z sieci dziś</div>
                <div class="eid-hint" id="eid-grid_import_sell_block_kwh"></div>
              </div>
              <div class="field-controls">
                <input type="number" min="0" max="100" step="0.1" data-num-key="grid_import_sell_block_kwh">
                <span style="color:var(--muted);">kWh</span>
              </div>
            </div>
            <div class="row">
              <div class="field-info">
                <div class="name">Ostrożność prognozy PV w planie</div>
                <div class="eid-hint" id="eid-pv_plan_pessimism_pct"></div>
              </div>
              <div class="field-controls">
                <input type="number" min="0" max="100" step="5" data-num-key="pv_plan_pessimism_pct">
                <span style="color:var(--muted);">%</span>
              </div>
            </div>
          </div>

          <div class="section" data-tile="ems-pvblock">
            <div class="section-title">⚡ Blokada ładowania PV</div>
            <div class="action-grid">
              <button class="btn" id="btn-toggle-blokada-pv"><div class="icon" id="icon-blokada-pv">🔋</div><div class="label">Blokada PV<br><span id="txt-blokada-pv">wyłączona</span></div></button>
            </div>
            <div class="row" style="margin-top:10px;">
              <div class="field-info"><div class="name">Minimalny SOC dla sprzedaży</div><div class="eid-hint" id="eid-minimalny_soc_dla_wylaczenia_sprzedazy"></div></div>
              <div class="field-controls"><input type="number" min="0" max="100" step="1" data-num-key="minimalny_soc_dla_wylaczenia_sprzedazy"><span style="color:var(--muted);">%</span></div>
            </div>
            <div class="row">
              <div class="field-info"><div class="name">Min SOC sprzedaży 6000W</div><div class="eid-hint" id="eid-min_soc_for_sell"></div></div>
              <div class="field-controls"><input type="number" min="0" max="100" step="1" data-num-key="min_soc_for_sell"><span style="color:var(--muted);">%</span></div>
            </div>
            <div class="row">
              <div class="field-info"><div class="name">Min SOC eksportu PV</div><div class="eid-hint" id="eid-min_soc_for_pv_export"></div></div>
              <div class="field-controls"><input type="number" min="0" max="100" step="1" data-num-key="min_soc_for_pv_export"><span style="color:var(--muted);">%</span></div>
            </div>
            <div class="row">
              <div class="field-info"><div class="name">Min SOC stop eksportu PV</div><div class="eid-hint" id="eid-min_soc_for_pv_export_stop"></div></div>
              <div class="field-controls"><input type="number" min="0" max="100" step="1" data-num-key="min_soc_for_pv_export_stop"><span style="color:var(--muted);">%</span></div>
            </div>
          </div>

          <div class="section" data-tile="ems-export">
            <div class="section-title">🔋 Eksport z PV i blokada ładowania</div>
            <div class="row"><div class="field-info"><div class="name">Start eksportu</div><div class="eid-hint" id="eid-pv_export_start"></div></div>
              <div class="field-controls"><input type="time" data-time-key="pv_export_start"></div></div>
            <div class="row"><div class="field-info"><div class="name">Stop eksportu</div><div class="eid-hint" id="eid-pv_export_stop"></div></div>
              <div class="field-controls"><input type="time" data-time-key="pv_export_stop"></div></div>
            <div class="action-grid" style="margin-top:10px;">
              <button class="btn" id="btn-script-eksport-pv"><div class="icon">☀️</div><div class="label">Eksportuj PV + blokuj baterię</div></button>
              <button class="btn" id="btn-script-przywroc"><div class="icon">🔋</div><div class="label">Przywróć ładowanie baterii</div></button>
            </div>
          </div>

          <div class="section" data-tile="ems-gridpower">
            <div class="section-title">⚡ Moc ładowania z sieci i ochrona przyłącza</div>
            <div class="row">
              <div class="field-info">
                <div class="name">Moc ładowania baterii z sieci (0 = nie zmieniaj)</div>
                <div class="eid-hint" id="eid-grid_charge_power_kw"></div>
              </div>
              <div class="field-controls">
                <input type="number" min="0" max="30" step="0.1" data-num-key="grid_charge_power_kw">
                <span style="color:var(--muted);">kW</span>
              </div>
            </div>
            <div class="row">
              <div class="field-info">
                <div class="name">Limit poboru z sieci — ochrona przyłącza (0 = wyłączony)</div>
                <div class="eid-hint" id="eid-grid_import_limit_kw"></div>
              </div>
              <div class="field-controls">
                <input type="number" min="0" max="60" step="0.1" data-num-key="grid_import_limit_kw">
                <span style="color:var(--muted);">kW</span>
              </div>
            </div>
            <div class="row">
              <div class="field-info">
                <div class="name">Oszczędzanie energii: wyłączaj urządzenia poniżej SOC (0 = wyłączone)</div>
                <div class="eid-hint" id="eid-device_shed_soc"></div>
              </div>
              <div class="field-controls">
                <input type="number" min="0" max="100" step="1" data-num-key="device_shed_soc">
                <span style="color:var(--muted);">%</span>
              </div>
            </div>
          </div>

          <div class="section" data-tile="ems-gridcharge">
            <div class="section-title">🔌 Ładowanie z sieci</div>
            <div class="action-grid">
              <button class="btn" id="btn-laduj-1"><div class="icon">🔌</div><div class="label">Zestaw 1<br><span id="txt-laduj-1">wyłączono</span></div></button>
              <button class="btn" id="btn-laduj-2"><div class="icon">🔌</div><div class="label">Zestaw 2<br><span id="txt-laduj-2">wyłączono</span></div></button>
              <button class="btn" id="btn-force-charge" style="grid-column: 1 / -1;"><div class="icon">⚡</div><div class="label">Wymuś ładowanie z sieci<br><span id="txt-force-charge">wyłączono</span></div></button>
            </div>
            <div class="action-grid">
              <button class="btn" id="btn-toggle-ladowanie-siec" style="grid-column: 1 / -1;"><div class="icon" id="icon-ladowanie-siec">🔌</div><div class="label">Wymuszone ładowanie z sieci<br><span id="txt-ladowanie-siec">wyłączone</span></div></button>
            </div>
            <div class="row"><div class="field-info"><div class="name">Start 1</div><div class="eid-hint" id="eid-start_grid_charge"></div></div>
              <div class="field-controls"><input type="time" data-time-key="start_grid_charge"></div></div>
            <div class="row"><div class="field-info"><div class="name">Stop 1</div><div class="eid-hint" id="eid-stop_grid_charge"></div></div>
              <div class="field-controls"><input type="time" data-time-key="stop_grid_charge"></div></div>
            <div class="row"><div class="field-info"><div class="name">Start 2</div><div class="eid-hint" id="eid-start_grid_charge_2"></div></div>
              <div class="field-controls"><input type="time" data-time-key="start_grid_charge_2"></div></div>
            <div class="row"><div class="field-info"><div class="name">Stop 2</div><div class="eid-hint" id="eid-stop_grid_charge_2"></div></div>
              <div class="field-controls"><input type="time" data-time-key="stop_grid_charge_2"></div></div>
          </div>
        </div>
      `;
      this.shadowRoot.appendChild(wrap);
      this._safe(() => this._tabsPosSync());

      // Obsługa przycisków czasu dla Historii
      wrap.querySelectorAll('.time-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          wrap.querySelectorAll('.time-btn').forEach(b => b.classList.remove('active'));
          e.target.classList.add('active');
          this._historyRange = e.target.dataset.range;
          this._fetchHistoryData(this._historyRange);
        });
      });

      const logBody = wrap.querySelector('#logTabBody');
      if (logBody) {
        logBody.addEventListener('click', (ev) => {
          const t = ev.target.closest('[data-switch],[data-service]');
          if (!t || !this._hass) return;
          if (t.dataset.switch) {
            this._hass.callService('switch', 'toggle', { entity_id: t.dataset.switch });
          } else if (t.dataset.service) {
            const toast = (msg) => { const el = this._el('logToast'); if (el) { el.textContent = msg; setTimeout(() => { el.textContent = ''; }, 6000); } };
            this._hass.callService('bms_komp_dec', t.dataset.service, {})
              .then(() => toast('Wykonano — wynik w dzienniku decyzji.'))
              .catch((e) => toast('Błąd: ' + (e && e.message ? e.message : e)));
          }
        });
        logBody.addEventListener('change', (ev) => {
          const t = ev.target.closest('input[data-number]');
          if (!t || !this._hass) return;
          const v = parseFloat(String(t.value).replace(',', '.'));
          if (isNaN(v)) return;
          this._hass.callService('number', 'set_value', { entity_id: t.dataset.number, value: v });
        });
      }

      wrap.querySelectorAll('[data-theme-set]').forEach(b => {
        b.addEventListener('click', () => this._setTheme(b.dataset.themeSet, true));
      });
      this._applyTheme();
      this._applyLayout();
      this._layWire(wrap);
      { const lb = this._el('lookBtn'); if (lb) lb.addEventListener('click', () => this._lookOpenSet(!this._lookOpen)); }
      this._bindNodePop(wrap);
      wrap.addEventListener('click', (ev) => {
        const t = ev.target && ev.target.closest ? ev.target.closest('[data-mod-retry]') : null;
        if (!t) return;
        const n = t.dataset.modRetry; if (!MODULES[n]) return;
        MODULES[n].err = ''; MODULES[n].p = null;
        if (n === 'diag') this._safe(() => this._dgOpen());
        else if (n === 'devices') { const r = this._el('devRoot'); if (r) r.innerHTML = ''; this._safe(() => this._devEnsure()); }
        else this._safe(() => this._exRetry && this._exRetry());
      });

      wrap.querySelectorAll('.tab').forEach(btn => {
        btn.addEventListener('click', () => {
          const tab = btn.dataset.tab;
          this._activeTab = tab;
          const subTab = tab === 'ems' || tab === 'dev' || tab === 'diag';
          wrap.querySelectorAll('.tab').forEach(b => b.classList.toggle('active', b === btn || (subTab && b.dataset.tab === 'settings')));
          wrap.querySelectorAll('.tab-content').forEach(c => c.style.display = c.dataset.tabContent === tab ? '' : 'none');
          this._tabEnter(tab);
        });
      });

      // Ustawienia: lista podstron (EMS, Urządzenia, Wygląd, Serwis) i powrót
      wrap.addEventListener('click', (ev) => {
        const it = ev.target && ev.target.closest ? ev.target.closest('[data-hub],[data-hub-back]') : null; if (!it) return;
        if (it.hasAttribute('data-hub-back')) { const t = wrap.querySelector('.tab[data-tab="settings"]'); if (t) t.click(); return; }
        const h = it.dataset.hub;
        if (h === 'look') { const lb = wrap.querySelector('#lookBtn'); if (lb) lb.click(); return; }
        const t = wrap.querySelector(`.tab[data-tab="${h}"]`); if (t) t.click();
      });

      // Ustawienia: wyszukiwarka opcji (sekcje, nazwy przełączników i pól w podstronie EMS)
      {
        const inp = wrap.querySelector('#setSearch'), out = wrap.querySelector('#setFound'), hub = wrap.querySelector('#setHub');
        const norm = (t) => String(t || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/ł/g, 'l');
        let found = [];
        if (inp && out && hub) {
          inp.addEventListener('input', () => {
            const q = norm(inp.value).trim();
            if (q.length < 2) { out.hidden = true; out.innerHTML = ''; hub.hidden = false; found = []; return; }
            const pane = wrap.querySelector('[data-tab-content="ems"]');
            const seen = new Set(); found = [];
            if (pane) pane.querySelectorAll('.section-title, .name, .label, summary').forEach((el) => {
              const txt = (el.textContent || '').trim().replace(/\s+/g, ' ');
              if (txt.length < 3 || txt.length > 90 || !norm(txt).includes(q) || seen.has(txt)) return;
              seen.add(txt); found.push({ el, txt, sec: (el.closest('.section') && el.closest('.section').querySelector(':scope > .section-title') || { textContent: '' }).textContent.trim() });
            });
            hub.hidden = true; out.hidden = false;
            const esc = (t) => String(t).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
            out.innerHTML = found.length ? found.slice(0, 12).map((f, i) => `<button type="button" class="hub-item" data-found="${i}"><span class="hub-tx"><b>${esc(f.txt)}</b><small>EMS${f.sec && f.sec !== f.txt ? ' › ' + esc(f.sec) : ''}</small></span><span class="hub-ar">›</span></button>`).join('')
              : '<div style="padding:12px 4px;color:var(--muted);font-size:13px;">Nic nie znaleziono. Spróbuj krótszego słowa (szuka w podstronie EMS).</div>';
          });
          out.addEventListener('click', (ev) => {
            const b = ev.target && ev.target.closest ? ev.target.closest('[data-found]') : null; if (!b) return;
            const f = found[+b.dataset.found]; if (!f) return;
            const tab = wrap.querySelector('.tab[data-tab="ems"]'); if (tab) tab.click();
            const sec = f.el.closest('.section'); if (sec && sec.classList.contains('collapsed')) { const t = sec.querySelector(':scope > .section-title'); if (t) t.click(); }
            setTimeout(() => { try { f.el.scrollIntoView({ block: 'center', behavior: 'smooth' }); f.el.classList.add('set-flash'); setTimeout(() => f.el.classList.remove('set-flash'), 2200); } catch (e) { /* bez przewijania */ } }, 120);
          });
        }
      }

      // Ustawienia: sekcje zwijane kliknięciem w tytuł (stan w localStorage, domyślnie rozwinięte)
      {
        let saved = {}; try { saved = JSON.parse(localStorage.getItem('bms_ems_collapsed') || '{}') || {}; } catch (e) { saved = {}; }
        wrap.querySelectorAll('.section[data-tile^="ems-"]').forEach((sec) => {
          const t = sec.querySelector(':scope > .section-title'); if (!t) return;
          const key = (t.textContent || '').trim();
          t.classList.add('collapsible'); t.setAttribute('role', 'button'); t.setAttribute('tabindex', '0');
          const apply = (c) => { sec.classList.toggle('collapsed', c); t.setAttribute('aria-expanded', c ? 'false' : 'true'); };
          apply(!!saved[key]);
          const tog = () => {
            const c = !sec.classList.contains('collapsed'); apply(c);
            if (c) saved[key] = 1; else delete saved[key];
            try { localStorage.setItem('bms_ems_collapsed', JSON.stringify(saved)); } catch (e) { /* brak storage */ }
          };
          t.addEventListener('click', tog);
          t.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); tog(); } });
        });
      }

      const addBtn = (id, action) => { const el = this._el(id); if (el) el.addEventListener('click', action); };
      addBtn('btn-sprzedaz-1', () => this._toggle('switch', 'bateria_sprzedaz_1'));
      addBtn('btn-sprzedaz-2', () => this._toggle('switch', 'bateria_sprzedaz_2'));
      addBtn('btn-laduj-1', () => this._toggle('switch', 'ladowanie_z_sieci_1'));
      addBtn('btn-laduj-2', () => this._toggle('switch', 'ladowanie_z_sieci_2'));
      addBtn('btn-force-charge', () => this._toggle('switch', 'force_charge_battery'));
      addBtn('btn-script-9700', () => this._pressButton('nadwyzka_9700w'));
      addBtn('btn-script-6000', () => {
        if (this._isSellBlockedByImport()) {
          this._showToast('⛔ Sprzedaż zablokowana — import z sieci przekracza próg', true);
          return;
        }
        this._pressButton('sprzedaz_6000w');
      });
      addBtn('btn-script-eksport-pv', () => this._pressButton('eksport_pv_blokada'));
      addBtn('btn-script-przywroc', () => this._pressButton('przywroc_ladowanie'));
      addBtn('btn-suggest', () => this._suggestSchedule());
      { const sr = this._el('suggestResults'); if (sr && !sr.innerHTML.trim()) sr.innerHTML = this._sugPlaceholder(); }

      addBtn('btn-toggle-blokada-pv', () => {
        const isBlocked = this._isPvBlocked();
        this._showToast(`⏳ ${isBlocked ? 'Odblokowuję' : 'Blokuję'} PV...`);
        // przez przyciski integracji: wartość „normalnego” prądu i zakres dobiera backend (nie 170 A na sztywno)
        this._call('button', 'press', { entity_id: this._eid('button', isBlocked ? 'odblokuj_ladowanie' : 'zablokuj_ladowanie') })
          .then(() => this._showToast(`✅ PV ${isBlocked ? 'odblokowane' : 'zablokowane'}`))
          .catch(e => this._showToast(`❌ Błąd: ${e.message || e}`, true));
      });

      addBtn('btn-toggle-ladowanie-siec', () => {
        const isOn = this._isGridChargingOn();
        this._showToast(`⏳ ${isOn ? 'Wyłączam' : 'Włączam'} ładowanie z sieci...`);
        this._call('button', 'press', { entity_id: this._eid('button', isOn ? 'wylacz_ladowanie_siec' : 'wlacz_ladowanie_siec') })
          .then(() => this._showToast(`✅ Ładowanie z sieci ${isOn ? 'wyłączone' : 'włączone'}`))
          .catch(e => this._showToast(`❌ Błąd: ${e.message || e}`, true));
      });

      wrap.querySelectorAll('input[type="time"]').forEach(inp => {
        let saveTimer = null;
        inp.addEventListener('change', () => {
          if (saveTimer) clearTimeout(saveTimer);
          saveTimer = setTimeout(async () => {
            const key = inp.dataset.timeKey;
            const eid = this._eid('time', key);
            if (!inp.value) return;
            try {
              await this._call('time', 'set_value', { entity_id: eid, time: inp.value + ':00' });
              this._lastUserChange[key] = Date.now();
              inp.classList.remove('saved-err');
              inp.classList.add('saved-ok');
              setTimeout(() => inp.classList.remove('saved-ok'), 1500);
              // 00:00 w harmonogramie znaczy „nie ustawiono” — okno z taką godziną nie wystartuje ani się nie zakończy
              if (inp.value === '00:00') this._showToast('⚠️ 00:00 oznacza „nie ustawiono” — okno nie zadziała. Dla północy wpisz 23:59 (koniec) albo 00:01 (start).', true);
              else this._showToast(`✅ Zapisano ${inp.value}`);
            } catch (e) {
              inp.classList.remove('saved-ok');
              inp.classList.add('saved-err');
              setTimeout(() => inp.classList.remove('saved-err'), 2500);
              this._showToast(`❌ Błąd [${eid}]: ${e.message || e}`, true);
            }
          }, 400);
        });
      });

      wrap.querySelectorAll('input[type="number"]').forEach(inp => {
        let saveTimer = null;
        inp.addEventListener('change', () => {
          if (saveTimer) clearTimeout(saveTimer);
          saveTimer = setTimeout(async () => {
            const key = inp.dataset.numKey;
            const eid = this._eid('number', key);
            if (inp.value === '') return;
            try {
              await this._call('number', 'set_value', { entity_id: eid, value: parseFloat(inp.value) });
              this._lastUserChange[key] = Date.now();
              inp.classList.remove('saved-err');
              inp.classList.add('saved-ok');
              setTimeout(() => inp.classList.remove('saved-ok'), 1500);
              this._showToast(`✅ Zapisano ${inp.value}`);
            } catch (e) {
              inp.classList.remove('saved-ok');
              inp.classList.add('saved-err');
              setTimeout(() => inp.classList.remove('saved-err'), 2500);
              this._showToast(`❌ Błąd [${eid}]: ${e.message || e}`, true);
            }
          }, 400);
        });
      });
    }

    _toggle(domain, key) {
      const eid = this._eid(domain, key);
      const isOn = this._st(eid) === 'on';
      this._call(domain, isOn ? 'turn_off' : 'turn_on', { entity_id: eid })
        .then(() => this._showToast(`✅ ${isOn ? 'Wyłączono' : 'Włączono'}`))
        .catch(e => this._showToast(`❌ Błąd: ${e.message || e}`, true));
    }

    _pressButton(key) {
      const eid = this._eid('button', key);
      this._call('button', 'press', { entity_id: eid })
        .then(() => this._showToast(`✅ Wysłano`))
        .catch(e => {
          const msg = (e && e.message) ? e.message : String(e);
          this._showToast(`❌ ${msg}`, true);
        });
    }

    // ===== INTELIGENTNY HARMONOGRAM =====
    async _suggestSchedule() {
      const btn = this._el('btn-suggest');
      const results = this._el('suggestResults');
      if (!results) return;
      if (btn) btn.disabled = true;
      results.innerHTML = '<div style="color:var(--muted);padding:8px;">⏳ Analizuję prognozy...</div>';
      try {
        const res = await this._hass.callService(
          'bms_komp_dec', 'suggest_schedule', {}, undefined, false, true
        );
        const data = res?.response || res;
        this._renderSuggestions(data);
        const now = new Date();
        if (this._el('suggLastAt')) {
          this._el('suggLastAt').textContent =
            `Ostatnia: ${now.toLocaleTimeString('pl-PL', {hour:'2-digit', minute:'2-digit'})}`;
        }
      } catch (e) {
        results.innerHTML = `<div style="color:#f43f5e;padding:8px;">❌ Błąd: ${e.message || e}</div>`;
      } finally {
        if (btn) btn.disabled = false;
      }
    }

    _sugRulesHtml() {
      const T = this._tariffTxt();
      return `<details class="sg-rules"><summary>Jak podejmuję decyzje</summary>
        <ul>
          <li><b>Słońce.</b> Produkcję PV liczę tylko między wschodem a zachodem; prognozę PV (Solcast albo Forecast.Solar) poza tym przedziałem traktuję jako zero. Za godziny pracy PV uznaję te, w których prognoza przekracza 3% szczytu dnia.</li>
          <li><b>Ładowanie z sieci.</b> Tylko w tanim oknie nocnym taryfy (${T.night}), kończone tuż przed szczytem${T.dynamic ? ' — przy taryfie dynamicznej w najtańszych godzinach tego okna, a okna szczytu liczę każdego dnia z godzinowych cen zakupu' : ''}. Ilość to tyle, ile bateria potrzebuje, żeby dotrwać do świtu (aż PV pokryje zużycie domu) plus zapas. Gdy prognoza PV na ten dzień jest słaba, a taryfa dzienna droższa od nocnej, cel obejmuje też szczyt ${T.day}. Jeśli SOC wystarcza, pomijam.</li>
          <li><b>Sprzedaż z baterii.</b> Szukam najdroższych godzin RCE w szczytach ${T.peaks}. Sprzedaję tylko gdy cena okna jest wyższa od średniej dnia, a zysk netto (cena × sprawność − koszt alternatywny) przekracza minimalną marżę. Koszt alternatywny to średnia cena RCE w godzinach pracy PV, bo tyle dostałbym za tę energię, sprzedając ją z PV. Okno skracam, aż bateria dotrwa do świtu bez zejścia poniżej progu.</li>
          <li><b>Bezpieczniki.</b> Nie sprzedaję przy zbyt niskim SOC, przy braku cen RCE ani gdy bilans 2-dniowy (ładowanie z sieci vs produkcja PV) blokuje arbitraż.</li>
          <li><b>Blokada ładowania z PV.</b> Całą produkcję kieruję na sprzedaż w godzinach, gdy cena jest wyraźnie wyższa od średniej cen w godzinach PV, ale tylko jeśli po blokadzie zostanie dość nadwyżki PV na dopełnienie baterii.</li>
        </ul></details>`;
    }

    // ---------------------------------------------------------------- dzwonek: propozycje + skrzynka powiadomień
    _inbData() {
      const st = this._hass.states;
      const pa = (st[this._eid('sensor', 'plan_curve')] || {}).attributes || {};
      const ma = (st[this._eid('sensor', 'monitor_status')] || {}).attributes || {};
      const proposals = pa.proposals && typeof pa.proposals === 'object' ? pa.proposals : {};
      Object.keys(this._inbRej || {}).forEach(k => { if (!proposals[k] || proposals[k].proposed !== this._inbRej[k]) delete this._inbRej[k]; });   // lokalne odrzucenie wygasa razem z propozycją
      const rej = Object.assign({}, ma.inbox_rejected || {}, this._inbRej || {});
      const GROUPS = [
        ['🔌', 'Ładowanie z sieci (noc)', ['start_grid_charge', 'stop_grid_charge']],
        ['🔌', 'Ładowanie z sieci (zestaw 2)', ['start_grid_charge_2', 'stop_grid_charge_2']],
        ['💰', 'Sprzedaż z baterii — poranny szczyt', ['bateria_sprzedaz_start', 'bateria_sprzedaz_stop']],
        ['💰', 'Sprzedaż z baterii — wieczorny szczyt', ['bateria_sprzedaz_start_2', 'bateria_sprzedaz_stop_2']],
        ['☀️', 'Blokada ładowania z PV', ['pv_export_start', 'pv_export_stop']],
      ];
      const used = new Set(), groups = [];
      const mk = (icon, title, keys) => {
        const items = keys.filter(k => proposals[k] && typeof proposals[k] === 'object').map(k => { used.add(k); return [k, proposals[k]]; });
        if (!items.length) return;
        const chg = items.filter(([k, p]) => !p.skip && p.proposed && p.proposed !== p.current && rej[k] !== p.proposed);
        if (chg.length) groups.push({ icon, title, items, chg, kind: 'change' });
      };
      GROUPS.forEach(g => mk(...g));
      Object.keys(proposals).filter(k => !used.has(k)).forEach(k => mk('⚙️', proposals[k].label || k, [k]));
      const gone = this._inbGone || new Set(), read = this._inbRead || new Set();
      const notes = (Array.isArray(ma.inbox) ? ma.inbox : []).filter(e => !gone.has(e.id)).map(e => ({ ...e, read: e.read || read.has(e.id) }));
      const auto = (st[this._eid('switch', 'auto_apply')] || {}).state === 'on';
      const askip = ma.auto_skip && typeof ma.auto_skip === 'object' ? ma.auto_skip : {};   // powody, dla których auto-stosowanie nie zmieniło godzin
      const autoRead = ma.inbox_auto_read === true;     // autoodczyt włączony w integracji (starsza integracja nie ma tego atrybutu → zachowanie bez zmian)
      return { groups, notes, auto, askip, autoRead, pending: groups.length, unread: notes.filter(e => !e.read).length };
    }

    // Zamknięcie okienka = „obejrzane”: informacje i ostrzeżenia stają się przeczytane; błędy zostają do odhaczenia (albo 72 h).
    _inbAutoSeen() {
      try {
        const d = this._inbData(); if (!d.autoRead) return;
        const quiet = d.notes.filter(e => !e.read && (e.level === 'info' || e.level === 'ok' || e.level === 'warn')); if (!quiet.length) return;
        this._inbRead = this._inbRead || new Set(); quiet.forEach(e => this._inbRead.add(e.id));
        const p = this._hass.callService('bms_komp_dec', 'inbox_action', { action: 'read_seen' }); if (p && p.catch) p.catch(() => {});
      } catch (e) { /* nie wpływa na działanie panelu */ }
    }

    _renderInbox() {
      const d = this._inbData();
      const bell = this._el('bell'), badge = this._el('bellN');
      if (bell && !bell._wired) { bell._wired = true; bell.addEventListener('click', () => { const was = this._inbOpen; this._inbOpen = !this._inbOpen; if (was) this._inbAutoSeen(); this._renderInbox(); }); }
      const n = d.pending + d.unread;
      if (badge) { badge.hidden = !n; badge.textContent = n > 99 ? '99+' : String(n); badge.classList.toggle('calm', !d.pending); }
      let ov = this.shadowRoot.getElementById('inbOv');
      if (!ov) {
        ov = document.createElement('div'); ov.id = 'inbOv'; ov.className = 'inb-ov'; ov.hidden = true;
        ov.innerHTML = '<div class="inb" role="dialog" aria-label="Do decyzji i powiadomienia"></div>';
        ov.addEventListener('click', ev => {
          if (ev.target === ov) { this._inbOpen = false; this._inbAutoSeen(); this._renderInbox(); return; }
          const b = ev.target.closest('[data-inb]'); if (b) this._inbClick(b);
        });
        ov.addEventListener('toggle', ev => {
          const id = ev.target && ev.target.dataset && ev.target.dataset.exp; if (!id) return;
          this._inbExp = this._inbExp || new Set(); ev.target.open ? this._inbExp.add(id) : this._inbExp.delete(id);
        }, true);
        this.shadowRoot.appendChild(ov);
      }
      // nowe powiadomienie albo nowa propozycja → okno wyskakuje samo (raz); pamiętamy, co już pokazano
      if (!this._hass.states[this._eid('sensor', 'plan_curve')] && !this._hass.states[this._eid('sensor', 'monitor_status')]) { ov.hidden = true; return; }   // dane jeszcze nie dotarły
      const maxId = d.notes.reduce((m, e) => Math.max(m, Number(e.id) || 0), 0);
      const psig = d.groups.map(g => g.chg.map(([k, p]) => k + '=' + p.proposed).join('+')).join('|');
      if (!this._inbInit) {
        this._inbInit = true;
        let st = null;
        try { st = JSON.parse(localStorage.getItem('bms_inb_seen') || 'null'); } catch (e) { /* brak pamięci przeglądarki */ }
        this._inbSeenId = st && typeof st.id === 'number' ? st.id : maxId;
        this._inbSeenP = st && typeof st.p === 'string' ? st.p : psig;
      }
      // okno wyskakuje samo przy nowym powiadomieniu; przy włączonym autoodczycie tylko przy ostrzeżeniu lub błędzie (informacje czekają pod dzwonkiem)
      const freshNote = d.notes.some(e => !e.read && Number(e.id) > this._inbSeenId && (!d.autoRead || e.level === 'warn' || e.level === 'error'));
      if (!this._inbOpen && (freshNote || (psig && psig !== this._inbSeenP))) this._inbOpen = true;
      if (this._inbOpen) { this._inbSeenId = Math.max(this._inbSeenId, maxId); this._inbSeenP = psig; } else if (!psig) this._inbSeenP = '';
      if (this._inbPersisted !== this._inbSeenId + '|' + this._inbSeenP) {
        this._inbPersisted = this._inbSeenId + '|' + this._inbSeenP;
        try { localStorage.setItem('bms_inb_seen', JSON.stringify({ id: this._inbSeenId, p: this._inbSeenP })); } catch (e) { /* ignorujemy */ }
      }
      ov.hidden = !this._inbOpen;
      if (!this._inbOpen) return;
      const sig = JSON.stringify([d.groups.map(g => [g.title, g.kind, g.chg.map(([k, p]) => k + p.proposed + p.current + (p.gain_pln == null ? '' : p.gain_pln) + (p.required ? 'r' : ''))]), d.notes.map(e => [e.id, e.read]), d.auto, Object.keys(d.askip).sort().map(k => [k, d.askip[k] && d.askip[k].why, d.askip[k] && d.askip[k].prop])]);
      if (sig === this._inbSig) return;
      this._inbSig = sig;
      const esc = t => String(t == null ? '' : t).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
      const exp = this._inbExp || new Set();
      const det = (id, label, body) => body ? `<details data-exp="${id}" ${exp.has(id) ? 'open' : ''}><summary>${label}</summary><div class="inb-why">${body}</div></details>` : '';
      const clean = r => { let t = String(r || '').replace(/^Pomiń\s*[—-]\s*/, '').trim(); return t ? t.charAt(0).toUpperCase() + t.slice(1) : ''; };
      const ago = ts => {
        const m = Math.max(0, Math.round((Date.now() / 1000 - ts) / 60));
        if (m < 1) return 'teraz'; if (m < 60) return m + ' min temu'; if (m < 1440) return Math.round(m / 60) + ' h temu';
        return new Date(ts * 1000).toLocaleDateString('pl-PL', { day: 'numeric', month: 'short' });
      };
      const prop = d.groups.map((g, i) => {
        const why = [...new Set(g.items.map(([, p]) => clean(p.reason)).filter(Boolean))].map(esc).join('<br>');
        const vals = g.items.map(([k, p]) => {
          const nm = /stop/.test(k) ? 'STOP' : 'START';
          return g.chg.some(([kk]) => kk === k) ? `<span>${nm} <b>${esc(p.current || '—')} → ${esc(p.proposed)}</b></span>` : `<span>${nm} <b>${esc(p.current)}</b> <i>(bez zmian)</i></span>`;
        }).join('');
        const dat = g.chg.map(([k, p]) => `${k}=${esc(p.proposed)}`).join(',');
        const lp = g.chg[0] && g.chg[0][1];
        const fz = v => (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(2).replace('.', ',') + ' zł';
        const gtag = lp && lp.required ? '<span class="inb-tag" style="background:#ffffff14;color:var(--muted)">WYMAGANE</span>'
          : (lp && typeof lp.gain_pln === 'number' && isFinite(lp.gain_pln) ? `<span class="inb-tag" style="background:#10b98133;color:#10b981">${fz(lp.gain_pln)}</span>` : '');
        // auto-stosowanie włączone, a propozycja wisi → pokazujemy konkretny powód (limit, trwająca sprzedaż, czekanie na stabilność…)
        const nt = d.auto ? g.chg.map(([k, p]) => { const r = d.askip[k]; return r && String(r.prop) === String(p.proposed) ? r : null; }).find(Boolean) : null;
        const autoNote = nt ? `<div class="inb-auto ${nt.kind === 'wait' ? 'wait' : 'warn'}">🤖 Auto-stosowanie: ${esc(nt.why)}</div>` : '';
        return `<div class="inb-card p-change"><div class="inb-r"><span class="inb-t">${g.icon} ${esc(g.title)}</span><span>${gtag} <span class="inb-tag" style="background:#10b98122;color:#10b981">ZMIENIAM</span></span></div>
          <div class="inb-v">${vals}</div>${autoNote}${det('p' + i, 'Dlaczego', why)}
          <div class="inb-btns"><button type="button" data-inb="reject" data-p="${dat}">Odrzuć</button><button type="button" class="ok" data-inb="apply" data-p="${dat}">Potwierdź</button></div></div>`;
      }).join('');
      const ic = { error: '🚨', warn: '⚠️', ok: '✅', info: 'ℹ️' };
      // Długie komunikaty: na wierzchu pierwsza linia albo pierwsze zdanie, reszta pod „Szczegóły”; „EMS:” w tytule jest zbędne.
      const splitMsg = m => {
        m = String(m || '').trim(); const nl = m.indexOf('\n');
        if (nl > 0) return [m.slice(0, nl).trim(), m.slice(nl + 1).trim()];
        if (m.length > 150) { const re = /[.!?](?:\s+(?=[A-ZĄĆĘŁŃÓŚŹŻ0-9])|$)/g; let x; while ((x = re.exec(m))) { if (x.index >= 12 && x.index <= 160) { const h = m.slice(0, x.index + 1), r = m.slice(x.index + 1).trim(); return r ? [h, r] : [m, '']; } } }
        return [m, ''];
      };
      const shortT = t => String(t || '').replace(/\bEMS:\s*/, '');
      const notes = d.notes.map(e => { const [mh, mr] = splitMsg(e.message); return `<div class="inb-card n-${esc(e.level)} ${e.read ? '' : 'unread'}"><div class="inb-r"><span class="inb-t">${ic[e.level] || 'ℹ️'} ${esc(shortT(e.title))}</span><span class="inb-time">${(e.n || 1) > 1 ? `×${e.n} · ` : ''}${esc(ago(e.ts))}</span></div>
        <div class="inb-msg">${esc(mh)}</div>${det('m' + e.id, 'Szczegóły', esc(mr))}<div class="inb-act">${e.read ? (e.auto ? `<span class="inb-autotag">odczytane automatycznie: ${esc(e.auto)}</span>` : '') : `<button type="button" data-inb="read" data-id="${e.id}">Przeczytane</button>`}<button type="button" data-inb="del" data-id="${e.id}">Usuń</button></div></div>`; }).join('');
      const nP = d.pending;
      ov.firstChild.innerHTML = `<div class="inb-grip"></div><div class="inb-h"><b>${nP ? `Do decyzji (${nP})` : 'Powiadomienia'}</b><button type="button" class="inb-x" data-inb="close" aria-label="Zamknij">✕</button></div>
        ${d.auto ? '' : '<span class="inb-pill">auto-stosowanie wył.</span>'}
        <div class="inb-body">${prop ? `<div class="inb-sec"><span>Propozycje planu</span></div>${prop}` : ''}
        <div class="inb-sec"><span>Powiadomienia</span>${d.notes.length ? `<span>${d.unread ? '<button type="button" data-inb="readall">Przeczytane wszystkie</button>' : ''}<button type="button" data-inb="clear">Wyczyść</button></span>` : ''}</div>
        ${notes || '<div class="inb-empty">Brak powiadomień — podsumowania, alarmy i informacje pojawią się tutaj.</div>'}
        ${prop || nP ? '' : '<div class="inb-empty">Brak propozycji planu do zatwierdzenia.</div>'}</div>`;
    }

    async _inbClick(b) {
      const act = b.dataset.inb;
      const call = (svc, data) => this._hass.callService('bms_komp_dec', svc, data);
      const pairs = String(b.dataset.p || '').split(',').filter(Boolean).map(x => x.split('='));
      this._inbGone = this._inbGone || new Set(); this._inbRead = this._inbRead || new Set(); this._inbRej = this._inbRej || {};
      try {
        if (act === 'close') { this._inbOpen = false; this._inbAutoSeen(); }
        else if (act === 'apply') {
          const times = {}; pairs.forEach(([k, v]) => { if (k && /^\d{2}:\d{2}$/.test(v)) times[k] = v; });
          if (!Object.keys(times).length) return;
          await call('apply_schedule_times', { times });
          this._showToast('✅ Zapisano ' + Object.keys(times).length + ' ustawień');
        } else if (act === 'reject') {
          for (const [k, v] of pairs) { await call('inbox_action', { action: 'reject', key: k, proposed: v }); this._inbRej[k] = v; }
          this._showToast('Odrzucono propozycję');
        } else if (act === 'read') { this._inbRead.add(Number(b.dataset.id)); await call('inbox_action', { action: 'read', id: Number(b.dataset.id) }); }
        else if (act === 'del') { this._inbGone.add(Number(b.dataset.id)); await call('inbox_action', { action: 'delete', id: Number(b.dataset.id) }); }
        else if (act === 'readall') { this._inbData().notes.forEach(e => this._inbRead.add(e.id)); await call('inbox_action', { action: 'read_all' }); }
        else if (act === 'clear') { this._inbData().notes.forEach(e => this._inbGone.add(e.id)); await call('inbox_action', { action: 'clear' }); }
      } catch (e) { this._showToast('❌ ' + (e.message || e), true); }
      this._inbSig = null; this._renderInbox();
    }

    _renderSuggestions(data) {
      const el = this._el('suggestResults');
      if (!el) return;
      const esc = t => String(t == null ? '' : t).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
      const proposals = data?.proposals || {};
      if (data?.error) {
        el.innerHTML = `<div style="color:#f43f5e;padding:8px;">❌ ${esc(data.error)}</div>`;
        return;
      }
      if (!Object.keys(proposals).length) {
        el.innerHTML = '<div style="color:var(--muted);padding:8px;">Brak propozycji.</div>';
        return;
      }

      // ---- opis danych, na których oparto decyzje
      const f1 = v => Number(v).toFixed(1).replace('.', ',');
      const f3 = v => Number(v).toFixed(3).replace('.', ',');
      const has = v => v !== undefined && v !== null && !isNaN(Number(v));
      const at = new Date(data.generated_at || Date.now()).toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' });
      const facts = [];
      if (has(data.soc)) facts.push(`bateria <b>${f1(data.soc)}%</b>`);
      if (data.sunrise_today && data.sunset_today) facts.push(`słońce dziś <b>${data.sunrise_today}–${data.sunset_today}</b>`);
      if (has(data.pv_today_kwh) || has(data.pv_tomorrow_kwh))
        facts.push(`prognoza PV: dziś <b>${has(data.pv_today_kwh) ? f1(data.pv_today_kwh) + ' kWh' : '—'}</b>, jutro <b>${has(data.pv_tomorrow_kwh) ? f1(data.pv_tomorrow_kwh) + ' kWh' : '—'}</b>`);
      if (has(data.load_tomorrow_kwh)) facts.push(`przewidywane zużycie jutro <b>${f1(data.load_tomorrow_kwh)} kWh</b>`);
      if (has(data.rce_today_avg) || has(data.rce_tomorrow_avg))
        facts.push(`ceny RCE (śr., zł/kWh): dziś <b>${has(data.rce_today_avg) ? f3(data.rce_today_avg) : '—'}</b>, jutro <b>${has(data.rce_tomorrow_avg) ? f3(data.rce_tomorrow_avg) : 'jeszcze niedostępne'}</b>`);
      if (has(data.g12w_peak) && has(data.g12w_off_peak)) facts.push(data.tariff_dynamic
        ? `taryfa dynamiczna (dziś, śr.): szczyt <b>${f3(data.g12w_peak)}</b>, poza szczytem <b>${f3(data.g12w_off_peak)}</b> zł/kWh`
        : `taryfa: szczyt <b>${f3(data.g12w_peak)}</b>, noc <b>${f3(data.g12w_off_peak)}</b> zł/kWh`);

      // ---- decyzje: pary START/STOP łączymy w jedną kartę
      const GROUPS = [
        { icon: '🔌', title: 'Ładowanie z sieci (noc)', keys: ['start_grid_charge', 'stop_grid_charge'] },
        { icon: '🔌', title: 'Ładowanie z sieci (zestaw 2)', keys: ['start_grid_charge_2', 'stop_grid_charge_2'] },
        { icon: '💰', title: 'Sprzedaż z baterii — poranny szczyt', keys: ['bateria_sprzedaz_start', 'bateria_sprzedaz_stop'] },
        { icon: '💰', title: 'Sprzedaż z baterii — wieczorny szczyt', keys: ['bateria_sprzedaz_start_2', 'bateria_sprzedaz_stop_2'] },
        { icon: '☀️', title: 'Blokada ładowania z PV', keys: ['pv_export_start', 'pv_export_stop'] },
      ];
      const used = new Set();
      const groups = GROUPS.map(g => ({ ...g, items: g.keys.filter(k => proposals[k]).map(k => { used.add(k); return [k, proposals[k]]; }) })).filter(g => g.items.length);
      Object.keys(proposals).filter(k => !used.has(k)).forEach(k => groups.push({ icon: '⚙️', title: proposals[k].label || k, keys: [k], items: [[k, proposals[k]]] }));

      const clean = (r, skip) => {
        let t = String(r || '').replace(/^Pomiń\s*[—-]\s*/, '').trim();
        if (t) t = t.charAt(0).toUpperCase() + t.slice(1);
        return t;
      };
      let nChange = 0, nSkip = 0, nSame = 0, gainSum = 0, nGain = 0, nReq = 0;
      const fz = v => (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(2).replace('.', ',') + ' zł';
      let cards = '', skipCards = '';
      groups.forEach(g => {
        const its = g.items;
        const allSkip = its.every(([, p]) => p.skip);
        const changed = !allSkip && its.some(([, p]) => !p.skip && p.proposed && p.proposed !== p.current);
        const verdict = allSkip ? 'skip' : (changed ? 'change' : 'same');
        if (verdict === 'skip') nSkip++; else if (verdict === 'change') nChange++; else nSame++;
        const conf = (its.find(([, p]) => !p.skip) || its[0])[1].confidence;
        const live = its.find(([, p]) => !p.skip);
        let gainBadge = '';
        if (verdict === 'change' && live) {
          const gp = live[1];
          if (gp.required) { nReq++; gainBadge = '<span class="sg-badge sg-gain sg-req">wymagane do rana</span>'; }
          else if (typeof gp.gain_pln === 'number' && isFinite(gp.gain_pln)) { gainSum += gp.gain_pln; nGain++; gainBadge = `<span class="sg-badge sg-gain">${fz(gp.gain_pln)}</span>`; }
        }
        const confColor = conf === 'high' ? '#10b981' : conf === 'medium' ? '#fbbf24' : TC('muted');
        const badge = verdict === 'skip' ? ['Pomijam', '#f43f5e'] : verdict === 'change' ? ['Zmieniam', '#10b981'] : ['Bez zmian', TC('muted')];
        const rows = its.map(([k, p]) => {
          const nm = /stop/.test(k) ? 'STOP' : 'START';
          if (p.skip) return '';
          if (!p.proposed || p.proposed === p.current) return `<span>${nm} <b>${esc(p.current)}</b> <i>(bez zmian)</i></span>`;
          return `<span>${nm} <b class="sg-new">${esc(p.proposed)}</b> <i>(było ${esc(p.current)})</i></span>`;
        }).filter(Boolean).join('');
        const reasons = [...new Set(its.map(([, p]) => clean(p.reason, p.skip)).filter(Boolean))];
        const why = reasons.map(r => esc(r)).join('<br>');
        const [k1, p1] = its[0], second = its[1];
        const canApply = verdict === 'change';
        const attrs = canApply
          ? `data-suggest-key="${k1}" data-suggest-val="${esc((p1.proposed || '').replace(/"/g, ''))}"` + (second ? ` data-suggest-key2="${second[0]}" data-suggest-val2="${esc((second[1].proposed || '').replace(/"/g, ''))}"` : '')
          : '';
        const card = `<label class="sg sg-${verdict}">
          <input type="checkbox" ${attrs} ${canApply ? 'checked' : 'disabled'}>
          <div class="sg-body">
            <div class="sg-head"><span class="sg-title">${g.icon} ${esc(g.title)}</span>
              <span class="sg-badges">${gainBadge}<span class="sg-badge" style="background:${badge[1]}22;color:${badge[1]};">${badge[0]}</span>${verdict !== 'skip' ? `<span class="sg-badge" style="background:${confColor}22;color:${confColor};">${esc(conf || '?')}</span>` : ''}</span></div>
            ${rows ? `<div class="sg-vals">${rows}</div>` : ''}
            <div class="sg-why"><span>${verdict === 'skip' ? 'Dlaczego pomijam' : 'Dlaczego tak'}</span>${why || '—'}</div>
          </div>
        </label>`;
        if (verdict === 'skip') skipCards += card; else cards += card;
      });

      const head = `<div class="sg-sum"><div class="sg-sum-h">Na czym oparłem decyzje (stan z ${at})</div>
        <div class="sg-sum-t">${facts.join(' · ')}</div>
        <div class="sg-sum-r">Wynik: <b>zmieniam ${nChange}</b>, bez zmian ${nSame}, pomijam ${nSkip}.${nGain ? ` Szacowany zysk z propozycji: <b class="sg-gain-sum">${fz(gainSum)}</b>${nReq ? ` (+ ${nReq} wymagane)` : ''}.` : ''}${has(data.rce_tomorrow_avg) ? '' : ' Bez cen RCE na jutro nie planuję sprzedaży na jutro.'}</div></div>`;

      const skipBox = skipCards ? `<details class="sg-skipbox"><summary>Nie planuję (${nSkip})</summary><div class="sg-list">${skipCards}</div></details>` : '';
      el.innerHTML = head + `<div class="sg-list">${cards}</div>${skipBox}
        <div style="margin-top:12px;display:flex;gap:8px;">
          <button class="btn" id="btn-apply-suggest" style="flex:1;padding:10px;flex-direction:row;gap:6px;background:rgba(16,185,129,0.2);border-color:#10b981;">
            <span style="font-size:16px;">✅</span><span class="label">Zastosuj zaznaczone</span>
          </button>
          <button class="btn" id="btn-close-suggest" style="padding:10px 16px;">✖</button>
        </div>` + this._sugRulesHtml();
      this._el('btn-apply-suggest')?.addEventListener('click', () => this._applySuggestions());
      this._el('btn-close-suggest')?.addEventListener('click', () => { el.innerHTML = this._sugPlaceholder(); });
    }

    _sugPlaceholder() {
      return `<div style="color:var(--muted);padding:8px 0 4px;">Kliknij „Zaproponuj" aby wygenerować propozycję wraz z uzasadnieniem każdej decyzji.</div>` + this._sugRulesHtml();
    }

    async _applySuggestions() {
      const checks = this.shadowRoot.querySelectorAll('input[data-suggest-key]:checked');
      const times = {};
      checks.forEach(c => {
        [[c.dataset.suggestKey, c.dataset.suggestVal], [c.dataset.suggestKey2, c.dataset.suggestVal2]].forEach(([k, v]) => {
          if (k && v && /^\d{2}:\d{2}$/.test(v)) times[k] = v;
        });
      });
      if (!Object.keys(times).length) {
        this._showToast('Nic nie zaznaczono', true);
        return;
      }
      try {
        await this._hass.callService('bms_komp_dec', 'apply_schedule_times', { times });
        this._showToast(`✅ Zapisano ${Object.keys(times).length} ustawień`);
        this._el('suggestResults').innerHTML =
          `<div style="color:#10b981;padding:8px;">✅ Zapisano ${Object.keys(times).length} ustawień. Godziny zaktualizowane.</div>`;
        this._lastUserChange = {};
        setTimeout(() => this._render(), 400);
      } catch (e) {
        this._showToast(`❌ ${e.message || e}`, true);
      }
    }

    _render() {
      if (!this._hass) return;
      try { this._renderInner(); } catch (e) { console.warn('EMS PANEL render error:', e); }
    }

    // „Na ile godzin starczy baterii”: energia nad progiem odcięcia ÷ wygładzony pobór domu, bez PV (liczy integracja)
    _renderAutonomy() {
      const el = this._el('autonomyBox'); if (!el) return;
      const rs = this._hass && this._hass.states[this._eid('sensor', 'reserve_soc')];
      const au = rs && rs.attributes && rs.attributes.autonomy;
      if (!au || typeof au !== 'object' || typeof au.text !== 'string' || !au.text || typeof au.hours !== 'number' || !isFinite(au.hours)) { el.style.display = 'none'; el.textContent = ''; return; }
      const f = (x) => (isFinite(Number(x)) ? Math.round(Number(x)) : '?');
      const col = au.hours < 2 ? 'var(--red)' : (au.hours < 6 ? 'var(--orange)' : 'var(--green)');
      el.innerHTML = '';
      const b = document.createElement('b'); b.style.color = col; b.textContent = au.text;
      el.append('🔋 Bateria starczy na ok. ', b, document.createTextNode(` — dom bierze ${f(au.load_w)} W, do progu ${f(au.floor)}%, bez PV i sieci.`));
      el.title = `Do progu odcięcia zostało ~${isFinite(Number(au.usable_kwh)) ? Number(au.usable_kwh).toFixed(1).replace('.', ',') : '?'} kWh (po sprawności). Pobór wygładzony z ostatnich ~5 minut; w prawdziwym zaniku sieci z PV czas będzie dłuższy.`;
      el.style.display = '';
    }
    _renderFloorAlert() {
      const el = this._el('floorAlert'); if (!el) return;
      const rs = this._hass && this._hass.states[this._eid('sensor', 'reserve_soc')];
      const a = (rs && rs.attributes) || {};
      const fl = Number(a.inverter_floor), soc = this._num('soc', null);
      if (!isFinite(fl) || fl <= 0 || soc === null || soc > fl + 8) { el.style.display = 'none'; return; }
      const hm = (iso) => { const d = new Date(iso); return String(d.getHours()).padStart(2, '0'); };
      let cheap = '';
      if (a.cheap_start && a.cheap_end) {
        const st = new Date(a.cheap_start), en = new Date(a.cheap_end), now = new Date();
        const day = st.toDateString() === now.toDateString() ? 'dziś' : (st.getDate() === now.getDate() + 1 ? 'jutro' : st.toLocaleDateString('pl-PL', { weekday: 'long' }));
        // Koniec okna bywa w kolejnych dobach (weekend G12w kończy się w poniedziałek o 6:00) — samo „06:00” czytało się jak godzina z przeszłości.
        const GEN = ['niedzieli', 'poniedziałku', 'wtorku', 'środy', 'czwartku', 'piątku', 'soboty'];
        const dayOff = (d) => Math.round((new Date(d.getFullYear(), d.getMonth(), d.getDate()) - new Date(now.getFullYear(), now.getMonth(), now.getDate())) / 86400000);
        const endDay = (d) => { const o = dayOff(d); return o <= 0 ? '' : (o === 1 ? 'jutra ' : GEN[d.getDay()] + ' '); };
        cheap = a.cheap_now ? ` Trwa tanie okno do ${endDay(en)}${hm(a.cheap_end)}:00.`
          : (dayOff(en) === dayOff(st) ? ` Najbliższe tanie okno: ${day} ${hm(a.cheap_start)}–${hm(a.cheap_end)}.`
            : ` Najbliższe tanie okno: od ${day} ${hm(a.cheap_start)}:00 do ${endDay(en)}${hm(a.cheap_end)}:00.`);
      }
      const kwh = a.usable_kwh != null ? ` Do progu zostało ~${Number(a.usable_kwh).toFixed(1)} kWh.` : '';
      const atFloor = soc <= fl + 1;
      el.className = 'floor-alert' + (atFloor ? ' bad' : '');
      el.textContent = atFloor
        ? `⚠ Bateria ${Math.round(soc)}% — na progu odcięcia falownika (${Math.round(fl)}%): bateria nie zasila domu, brakującą moc falownik bierze z sieci.${cheap}`
        : `⚠ Bateria ${Math.round(soc)}% — blisko progu odcięcia falownika (${Math.round(fl)}%).${kwh}${cheap}`;
      el.style.display = '';
    }
    _renderPriceBar() {
      const el = this._el('priceBar'); if (!el) return;
      const rs = this._hass && this._hass.states[this._eid('sensor', 'reserve_soc')];
      const a = (rs && rs.attributes) || {};
      const num = (v) => (v === null || v === undefined || v === '' || isNaN(Number(v))) ? null : Number(v);
      const buy = num(a.price_buy), sell = num(a.price_sell);
      if (buy === null && sell === null) { el.style.display = 'none'; return; }
      const f = (v) => v === null ? '—' : this._fx(v, 2);
      el.style.display = '';
      el.innerHTML = `<div class="price-pill buy" title="Aktualna cena kupna energii">🛒 Kupno <b>${f(buy)}</b> zł/kWh</div>`
        + `<div class="price-pill sell${sell !== null && sell < 0 ? ' neg' : ''}" title="Aktualna cena sprzedaży (RCE)">💰 Sprzedaż <b>${f(sell)}</b> zł/kWh</div>`;
    }
    // Baner na górze: to, co wymaga reakcji (alarm falownika, dryf parametru po zapisie) oraz aktywne tryby specjalne.
    // Dane liczy integracja (sensor monitor_status), więc baner działa też po odświeżeniu strony i na każdym urządzeniu.
    _renderStatusBanner() {
      const el = this._el('statusBanner'); if (!el) return;
      const st = this._hass.states[this._eid('sensor', 'monitor_status')];
      const a = (st && st.attributes) || {};
      const sw = (k) => this._st(this._eid('switch', k)) === 'on';
      const items = [];
      (Array.isArray(a.alarms) ? a.alarms : []).slice(0, 4).forEach((x) => {
        items.push(['bad', `⚠ <b>Alarm falownika:</b> ${this._esc(x.entity_id)} = ${this._esc(x.state)}${x.text ? ` — ${this._esc(x.text)} <span title="${this._esc(a.fault_note || '')}" style="cursor:help;">ⓘ</span>` : ''}`]);
      });
      const nowS = Date.now() / 1000;
      (Array.isArray(a.watches) ? a.watches : []).filter((w) => w && w.status === 'drift' && nowS - Number(w.t0 || 0) < 6 * 3600).slice(0, 3).forEach((w) => {
        const last = (Array.isArray(w.checks) ? w.checks : []).slice(-1)[0] || {};
        items.push(['bad', `⚠ <b>${this._esc(w.label || w.entity_id)}:</b> ustawiono ${this._esc(w.expected)}, a falownik raportuje ${this._esc(last.value)}${last.note ? ' (' + this._esc(last.note) + ')' : ''}. Sprawdź w Diagnostyce.`]);
      });
      if (sw('storm_mode')) {
        const until = Number(a.storm_until);
        const when = isFinite(until) && until > 0 ? ` do ${new Date(until * 1000).toLocaleString('pl-PL', { weekday: 'short', hour: '2-digit', minute: '2-digit' })}` : '';
        items.push(['warn', `⛈ <b>Tryb burzowy${when}</b> — rezerwa 100%, sprzedaż z baterii wyłączona.`]);
      }
      if (sw('vacation_mode')) {
        const w = this._st(this._eid('number', 'vacation_load_w'));
        items.push(['', `🏖 <b>Tryb urlopowy</b> — plan zakłada stałe zużycie domu${w ? ' ' + this._esc(Math.round(Number(w))) + ' W' : ''}.`]);
      }
      // dane integracji: brak połączenia z falownikiem / nieaktualny plan
      if (!this._findEntity(ENTITY_FALLBACKS.soc)) items.push(['bad', '⚠ <b>Brak danych z falownika</b> — sprawdź połączenie (Ustawienia → Łączność).']);
      const gen = Date.parse(String(this._pvAttrs().generated_at || '')) / 1000;
      if (isFinite(gen) && gen > 0 && nowS - gen > 3600) items.push(['warn', `⚠ <b>Plan nieaktualny od ${Math.floor((nowS - gen) / 3600)} h</b> — EMS nie odświeżył planu; sprawdź zakładkę Ustawienia.`]);
      // Lista „Co dziś nie działa” (sensor monitor_status → issues) jest w Ustawienia → Diagnostyka → Przegląd.
      const key = JSON.stringify(items);
      if (key === this._sbKey) return;
      this._sbKey = key;
      if (!items.length) { el.style.display = 'none'; el.innerHTML = ''; return; }
      el.style.display = '';
      el.innerHTML = items.map((i) => `<div class="sb-item${i[0] ? ' ' + i[0] : ''}">${i[1]}</div>`).join('');
    }

    _renderInner() {
      this._safe(() => this._renderPriceBar());
      this._safe(() => this._renderFloorAlert());
      this._safe(() => this._renderAutonomy());
      this._safe(() => this._renderStatusBanner());
      // ekran główny korzysta z dodatków (rachunek dnia, wykres SOC, przyciski nadpisań) — ładujemy moduł, gdy integracja podaje „Widok planu”
      if (this._tabNeeds('main') && !MODULES.extras.ready && Object.keys(this._pvAttrs()).length) this._safe(() => this._exEnsure());
      this._safe(() => this._exRender());
      this._safe(() => this._renderWeather());
      this._safe(() => this._renderLoadConsumptionChart());
      this._safe(() => this._renderForecast7dChart());
      this._safe(() => this._renderHourlyForecastChart());
      this._safe(() => this._renderPvProductionChart());
      this._safe(() => this._renderPriceTable());
      this._safe(() => this._renderPlan());
      this._safe(() => this._renderInbox());
      this._safe(() => this._dgSyncTab());
      this._safe(() => this._devTabSync());
      this._safe(() => this._tabsPosSync());
      this._safe(() => this._setWarnSync());
      if (this._activeTab === 'diag') this._safe(() => this._dgTick());
      if (this._activeTab === 'dev') this._safe(() => this._devTick());
      if (this._tabNeeds('log')) this._safe(() => this._renderLogTab());

      const d = new Date();
      if (this._el('date')) {
        this._el('date').textContent = d.toLocaleDateString('pl-PL', { weekday: 'long', day: 'numeric', month: 'long' }) + ' · ' + d.toLocaleTimeString('pl-PL');
      }

      const pvBlocked = this._isPvBlocked();
      const btnBlock = this._el('btn-toggle-blokada-pv');
      const txtBlock = this._el('txt-blokada-pv');
      const iconBlock = this._el('icon-blokada-pv');
      if (btnBlock) btnBlock.classList.toggle('active', pvBlocked);
      if (txtBlock) txtBlock.textContent = pvBlocked ? 'zablokowana' : 'wyłączona';
      if (iconBlock) iconBlock.textContent = pvBlocked ? '🚫' : '✅';
      const badgeBlock = this._el('badge-blokada-pv');
      if (badgeBlock) badgeBlock.classList.toggle('on', pvBlocked);

      const gridOn = this._isGridChargingOn();
      const btnGrid = this._el('btn-toggle-ladowanie-siec');
      const txtGrid = this._el('txt-ladowanie-siec');
      const iconGrid = this._el('icon-ladowanie-siec');
      if (btnGrid) btnGrid.classList.toggle('active', gridOn);
      if (txtGrid) txtGrid.textContent = gridOn ? 'włączone' : 'wyłączone';
      if (iconGrid) iconGrid.textContent = gridOn ? '⚡' : '🔌';
      const badgeGrid = this._el('badge-ladowanie-siec');
      if (badgeGrid) badgeGrid.classList.toggle('on', gridOn);

      const sellBlocked = this._isSellBlockedByImport();
      const badgeSellBlock = this._el('badge-sprzedaz-zablokowana');
      if (badgeSellBlock) badgeSellBlock.classList.toggle('on', sellBlocked);
      {
        // energia naładowana z sieci, której dom jeszcze nie zużył — dopóki jest w baterii, sprzedaż jest zablokowana
        const ra = this._rsAttrs(), gb = Number(ra.grid_batt_kwh), wg = this._el('warn-grid-batt'), bg = this._el('badge-grid-batt');
        const show = isFinite(gb) && gb >= 0.1;
        if (wg) wg.classList.toggle('on', show);
        if (bg && show) {
          const t = `🔌 W baterii ~${gb.toFixed(1).replace('.', ',')} kWh energii z sieci` + (ra.grid_batt_block ? ' — sprzedaż zablokowana, aż dom ją zużyje' : '');
          if (bg.textContent !== t) bg.textContent = t;
          bg.classList.toggle('danger', !!ra.grid_batt_block);
          bg.title = 'Licznik energii naładowanej z sieci: rośnie przy ładowaniu z sieci, maleje, gdy bateria zasila dom. Sprzedaż energii z sieci jest niedozwolona.';
        }
      }
      const warnSell = this._el('warn-sprzedaz-zablokowana');
      if (warnSell) warnSell.classList.toggle('on', sellBlocked);
      const btn6k = this._el('btn-script-6000');
      if (btn6k) {
        // etykieta pokazuje faktyczną moc sprzedaży z ustawień integracji (domyślnie 6000 W)
        const sw = Number(this._rsAttrs().sell_power_w);
        const lab = btn6k.querySelector('.label');
        if (lab && isFinite(sw) && sw > 0) { const t = `Sprzedaż ${Math.round(sw)}W`; if (lab.textContent !== t) lab.textContent = t; }
        btn6k.classList.toggle('blocked', sellBlocked);
        btn6k.disabled = sellBlocked;
        btn6k.title = sellBlocked
          ? 'Zablokowane: import z sieci przekracza próg (kategoryczny zakaz)'
          : '';
      }

      this._updateBadge('switch', 'bateria_sprzedaz_1', 'badge-sprzedaz-1', ['bateria_sprzedaz_start', 'bateria_sprzedaz_stop']);
      this._updateBadge('switch', 'bateria_sprzedaz_2', 'badge-sprzedaz-2', ['bateria_sprzedaz_start_2', 'bateria_sprzedaz_stop_2']);
      this._updateBadge('switch', 'ladowanie_z_sieci_1', 'badge-laduj-1', ['start_grid_charge', 'stop_grid_charge']);
      this._updateBadge('switch', 'ladowanie_z_sieci_2', 'badge-laduj-2', ['start_grid_charge_2', 'stop_grid_charge_2']);
      this._updateBadge('switch', 'force_charge_battery', 'badge-force-charge');
      this._syncBadges();

      this._updateBtn('switch', 'bateria_sprzedaz_1', 'btn-sprzedaz-1', 'txt-sprzedaz-1');
      this._updateBtn('switch', 'bateria_sprzedaz_2', 'btn-sprzedaz-2', 'txt-sprzedaz-2');
      this._updateBtn('switch', 'ladowanie_z_sieci_1', 'btn-laduj-1', 'txt-laduj-1');
      this._updateBtn('switch', 'ladowanie_z_sieci_2', 'btn-laduj-2', 'txt-laduj-2');
      this._updateBtn('switch', 'force_charge_battery', 'btn-force-charge', 'txt-force-charge');

      const activeEl = this.shadowRoot.activeElement;
      const now = Date.now();

      this.shadowRoot.querySelectorAll('input[type="time"]').forEach(inp => {
        const key = inp.dataset.timeKey;
        const eid = this._eid('time', key);
        const status = this._eidStatus(eid);
        const hint = this._el(`eid-${key}`);
        if (hint) {
          if (status === 'ok') {
            hint.textContent = SETTING_HELP[key] || '';
            hint.className = 'eid-hint help';
          } else {
            hint.textContent = status === 'unavail' ? `⚠ Encja ${eid} jest chwilowo niedostępna.` : `⚠ Brak encji ${eid} w Home Assistant — sprawdź, czy integracja jest załadowana.`;
            hint.className = 'eid-hint err';
          }
        }
        if (this._lastUserChange[key] && (now - this._lastUserChange[key]) < 15000) return;
        if (activeEl === inp) return;
        const val = this._st(eid);
        if (val && inp.value !== val.slice(0, 5)) inp.value = val.slice(0, 5);
      });

      this.shadowRoot.querySelectorAll('input[type="number"]').forEach(inp => {
        const key = inp.dataset.numKey;
        const eid = this._eid('number', key);
        const status = this._eidStatus(eid);
        const hint = this._el(`eid-${key}`);
        if (hint) {
          if (status === 'ok') {
            hint.textContent = SETTING_HELP[key] || '';
            hint.className = 'eid-hint help';
          } else {
            hint.textContent = status === 'unavail' ? `⚠ Encja ${eid} jest chwilowo niedostępna.` : `⚠ Brak encji ${eid} w Home Assistant — sprawdź, czy integracja jest załadowana.`;
            hint.className = 'eid-hint err';
          }
        }
        if (this._lastUserChange[key] && (now - this._lastUserChange[key]) < 15000) return;
        if (activeEl === inp) return;
        const val = this._st(eid);
        if (val && inp.value !== val) inp.value = val;
      });

      this._safe(() => { this._renderWhy(); this._applySimple(); });
      this._drawPowerflow();
    }

    // sensor „Widok planu” (dlaczego, tabela planu, nadpisania, historia SOC) — liczy integracja
    _pvAttrs() {
      const s = this._hass && this._hass.states[this._eid('sensor', 'plan_view')];
      return (s && s.attributes) || {};
    }

    // „Dlaczego?”: jedno zdanie o tym, co EMS teraz robi i z jakiego powodu (+ powody poboczne)
    _renderWhy() {
      const box = this._el('whyBox'); if (!box) return;
      const w = this._pvAttrs().why;
      if (!w || !w.text) { if (box.style.display !== 'none') box.style.display = 'none'; return; }
      const key = JSON.stringify([w.kind, w.text, w.details]);
      if (box.dataset.k !== key) {
        const ICON = { sell: '💰', grid: '🔌', pv: '☀️', full: '🔋', home: '🏠', storm: '⛈', vacation: '🏖', idle: '⏸' };
        const det = Array.isArray(w.details) ? w.details : [];
        box.dataset.k = key;
        box.innerHTML = `<div class="why-h"><span class="why-i">${ICON[w.kind] || 'ℹ️'}</span><span class="why-t">${bmsEsc(w.text)}</span></div>`
          + (det.length ? `<ul class="why-d">${det.map(x => `<li>${bmsEsc(x)}</li>`).join('')}</ul>` : '');
      }
      if (box.style.display === 'none') box.style.display = '';
    }

    // Tryb prosty (przełącznik w Ustawieniach → Tryby): zakładki Wykresy / Zysk i log / Urządzenia znikają,
    // zakładka EMS zamienia się w trzy pytania
    _simpleOn() { return this._st(this._eid('switch', 'simple_mode')) === 'on'; }
    _applySimple() {
      const root = this.shadowRoot, app = root && root.querySelector('.app'); if (!app) return;
      const on = this._simpleOn();
      if (app.classList.contains('simple') !== on) {
        app.classList.toggle('simple', on);
        root.querySelectorAll('.tab[data-tab="ems"] .tl, .tab[data-tab="ems"] .tls').forEach((e) => { e.textContent = 'EMS'; });
        const sw = this._el('simpleWrap'); if (sw) sw.style.display = on ? '' : 'none';
        if (on && ['charts', 'log', 'dev'].includes(this._activeTab)) { const m = root.querySelector('.tab[data-tab="main"]'); if (m) m.click(); }
        if (!on && sw) { sw.innerHTML = ''; sw.dataset.k = ''; }
        this._applyLayout(); this._layRefreshTab();   // przeniesienia obowiązują tylko poza trybem prostym
      }
      if (on) this._renderSimple();
    }
    _renderSimple() {
      const w = this._el('simpleWrap'); if (!w) return;
      const ra = this._rsAttrs();
      const sw = (k) => this._st(this._eid('switch', k));
      const AUTO = [['auto_apply', 'Automatyczne stosowanie propozycji planu'], ['auto_enable_sets', 'Auto-włączanie zestawów'],
        ['profit_check', 'Sprawdzanie opłacalności sprzedaży'], ['dynamic_reserve', 'Dynamiczna rezerwa baterii'],
        ['pv_forecast_correction', 'Korekta prognozy PV z historii'], ['live_load_correction', 'Korekta planu o bieżące zużycie']];
      const dyn = ra.tariff_mode === 'dynamic' || ra.tariff_dynamic === true;
      const tariff = dyn ? 'dynamiczna — ceny godzinowe' : `strefowa — szczyt ${bmsEsc(ra.tariff_label || '—')}`;
      const fp = (v) => (isFinite(Number(v)) && v !== null && v !== '') ? Number(v).toFixed(2).replace('.', ',') + ' zł/kWh' : '—';
      const seg = (k) => { const on = sw(k) === 'on', un = sw(k) === 'unavailable' || sw(k) === '';
        return `<div class="sm-seg"><button type="button" data-simple-sw="${k}" data-v="on" class="${on ? 'active' : ''}" ${un ? 'disabled' : ''}>Tak</button><button type="button" data-simple-sw="${k}" data-v="off" class="${!on && !un ? 'active' : ''}" ${un ? 'disabled' : ''}>Nie</button></div>`; };
      const auto = AUTO.filter(([k]) => sw(k) !== '' && sw(k) !== 'unavailable');
      const offN = auto.filter(([k]) => sw(k) !== 'on').length;
      const profit = this._profitToday();
      const key = JSON.stringify([tariff, ra.price_buy, ra.price_sell, sw('sell_enabled'), sw('grid_charge_enabled'), auto.map(([k]) => sw(k)), isFinite(profit) ? profit.toFixed(2) : null]);
      if (w.dataset.k === key) return;
      w.dataset.k = key;
      w.innerHTML = `
        <div class="sm-card"><div class="sm-q">Jaką masz taryfę?</div><div class="sm-tariff">${tariff}</div>
          <div class="sm-h">Kupno teraz ${fp(ra.price_buy)} · sprzedaż ${fp(ra.price_sell)}. EMS wykrył taryfę sam; zmienisz ją w konfiguracji integracji (Ustawienia → Urządzenia i usługi → EMS komp-dec → Konfiguruj).</div></div>
        <div class="sm-card"><div class="sm-q">Sprzedawać energię z baterii w drogich godzinach?</div>
          <div class="sm-h">Tak: EMS sprzeda tylko tyle, ile opłaca się sprzedać, i zostawi rezerwę na noc. Nie: bateria służy wyłącznie domowi, a do sieci idzie sama nadwyżka z PV.</div>${seg('sell_enabled')}</div>
        <div class="sm-card"><div class="sm-q">Ładować baterię z sieci, gdy prąd jest tani?</div>
          <div class="sm-h">Tak: EMS dokupi energię w najtańszych godzinach, jeśli to się opłaca przy dzisiejszych cenach i prognozie PV. Nie: bateria ładuje się tylko z PV.</div>${seg('grid_charge_enabled')}</div>
        <div class="sm-card"><div class="sm-q">Resztę ustawia EMS</div>
          <div class="sm-auto">${auto.map(([k, n]) => `<div class="${sw(k) === 'on' ? 'ok' : 'off'}">${sw(k) === 'on' ? '✓' : '○'} ${n}</div>`).join('')}</div>
          ${offN ? `<button type="button" class="btn" data-simple-auto="1" style="padding:10px 16px;">Włącz zalecaną automatykę (${offN})</button>` : '<div class="sm-h" style="margin:0;">Wszystko włączone — nic więcej nie musisz ustawiać.</div>'}</div>
        ${isFinite(profit) ? `<div class="sm-card"><div class="sm-q">Dziś: ${profit >= 0 ? '+' : '−'}${Math.abs(profit).toFixed(2).replace('.', ',')} zł</div><div class="sm-h" style="margin:0;">Bilans sprzedaży i zakupów energii z sieci od północy.</div></div>` : ''}
        <div class="sm-foot">Tryb prosty wyłączysz w Ustawieniach → Tryby i powiadomienia (administrator).</div>`;
      if (!w.dataset.bound) {
        w.dataset.bound = '1';
        w.addEventListener('click', (ev) => {
          const b = ev.target && ev.target.closest ? ev.target.closest('[data-simple-sw],[data-simple-auto]') : null; if (!b || b.disabled) return;
          if (b.dataset.simpleSw) {
            this._call('switch', b.dataset.v === 'on' ? 'turn_on' : 'turn_off', { entity_id: this._eid('switch', b.dataset.simpleSw) });
          } else {
            let n = 0;
            AUTO.forEach(([k]) => { const st = this._st(this._eid('switch', k)); if (st && st !== 'unavailable' && st !== 'on') { n++; this._call('switch', 'turn_on', { entity_id: this._eid('switch', k) }); } });
            if (n) this._showToast(`Włączono ${n} funkcji automatyki`);
          }
        });
      }
    }

    // Funkcja włączona: z oknem godzin (jeśli ma) — „teraz” trwa w oknie, „soon” dopiero będzie aktywna.
    _updateBadge(domain, key, badgeId, timeKeys) {
      const eid = this._eid(domain, key);
      const isOn = this._st(eid) === 'on';
      const badge = this._el(badgeId);
      if (!badge) return;
      if (!badge.dataset.label) badge.dataset.label = badge.textContent.trim();
      let txt = badge.dataset.label, soon = false;
      if (isOn && timeKeys) {
        const hm = (k) => { const m = /^(\d{1,2}):(\d{2})/.exec(String(this._st(this._eid('time', k)) || '')); return m ? [Number(m[1]), Number(m[2])] : null; };
        const a = hm(timeKeys[0]), b = hm(timeKeys[1]);
        if (a && b) {
          const f = (x) => String(x[0]).padStart(2, '0') + ':' + String(x[1]).padStart(2, '0');
          txt += ` ${f(a)}–${f(b)}`;
          const d = new Date(), cur = d.getHours() * 60 + d.getMinutes(), s = a[0] * 60 + a[1], e = b[0] * 60 + b[1];
          soon = s === e ? false : (s < e ? !(cur >= s && cur < e) : !(cur >= s || cur < e));
        }
      }
      if (timeKeys) {
        // godziny zestawu wyszarzone, gdy zestaw wyłączony albo okno puste (start = stop)
        const raw = (k) => String(this._st(this._eid('time', k)) || '').slice(0, 5);
        const idle = !isOn || raw(timeKeys[0]) === raw(timeKeys[1]);
        timeKeys.forEach((k) => {
          const row = this.shadowRoot.querySelector(`[data-time-key="${k}"]`)?.closest('.row');
          if (row) row.classList.toggle('inactive-row', idle);
        });
      }
      if (badge.textContent !== txt) badge.textContent = txt;
      badge.classList.toggle('on', isOn);
      badge.classList.toggle('soon', isOn && soon);
    }

    // Widoczne są tylko włączone funkcje (aktywne teraz i zaplanowane); bez żadnej — krótka informacja.
    _syncBadges() {
      const box = this._el('badge-none'); if (!box) return;
      const any = !!this.shadowRoot.querySelector('.active-badges .badge.on');
      box.style.display = any ? 'none' : '';
    }

    _updateBtn(domain, key, btnId, txtId) {
      const eid = this._eid(domain, key);
      const isOn = this._st(eid) === 'on';
      const btn = this._el(btnId); const txt = this._el(txtId);
      if (btn) btn.classList.toggle('active', isOn);
      if (txt) txt.textContent = isOn ? 'Włączone' : 'Wyłączone';
    }

    // ===== PRZEPŁYW MOCY (węzły) + PLAN DNIA =====
    // zysk dzisiaj z sensora „EMS Bilans dziś”; brak czujnika lub „unknown” → NaN (a nie 0 zł)
    _profitToday() { const raw = this._st(this._eid('sensor', 'profit_today')); return raw === '' ? NaN : Number(raw); }
    _fmtW(w) {
      const a = Math.abs(w);
      return a >= 1000 ? (a / 1000).toFixed(2).replace('.', ',') + ' kW' : Math.round(a) + ' W';
    }

    // wartość dodatkowego czujnika falownika po slugu nazwy z definicji ha-solarman (np. 'pv1_voltage');
    // prefiks urządzenia bywa inny niż 'inverter', więc szukamy też po końcówce identyfikatora
    _xv(slugs) {
      this._xCache = this._xCache || {};
      const states = this._hass.states;
      for (const sl of slugs) {
        let c = this._xCache[sl];
        if (!c || Date.now() - c.t > 60000 || (c.eid && !states[c.eid])) {
          let eid = this._inv('sensor', sl);
          if (!states[eid]) {
            const suf = '_' + sl;
            eid = Object.keys(states).find(id => id.startsWith('sensor.') && id.endsWith(suf)) || null;
          }
          c = this._xCache[sl] = { eid, t: Date.now() };
        }
        if (!c.eid) continue;
        const v = parseFloat(states[c.eid].state);
        if (!isNaN(v)) return v;
      }
      return null;
    }
    // jedna definicja (wcześniej dwie, druga nadpisywała pierwszą i rzucała błąd dla undefined / NaN): null → null, brak liczby → „—”
    _fx(v, d = 1) { if (v === null) return null; const n = Number(v); return v === undefined || v === '' || !isFinite(n) ? '—' : n.toFixed(d).replace('.', ',').replace('-', '−'); }

    // szczegóły pokazywane w oknie wykresu: napięcia, prądy, częstotliwość, temperatura baterii (pary etykieta/wartość)
    _nodeDetails() {
      const x = (a, d) => this._fx(this._xv(a), d);
      const join = (...p) => p.filter(Boolean).join(' · ');
      const d = { pv: [], home: [], grid: [], batt: [] };
      for (let i = 1; i <= 4; i++) {
        const v = this._xv([`pv${i}_voltage`]), a = this._xv([`pv${i}_current`]);
        if (v === null && a === null) continue;
        if (i > 2 && !(v > 5 || a > 0.05)) continue;          // nieużywane wejścia MPPT pomijamy
        d.pv.push([`PV${i}`, join(v !== null ? `${this._fx(v, 0)} V` : null, a !== null ? `${this._fx(a)} A` : null)]);
      }
      const row = (lab, val) => (val ? [lab, val] : null);
      // fazy: gdy falownik ma więcej niż jedną fazę (L2/L3), pokazujemy wszystkie; jedna faza wygląda jak dotąd
      const ph = (tpls, extraL1) => [1, 2, 3].map(n => this._xv(tpls.map(t => t.replace('#', n)).concat(n === 1 ? extraL1 : [])));
      const multi = (vals) => vals.slice(1).some(v => v !== null);
      const nPh = (...arrs) => Math.max(...arrs.map(a => a.reduce((m, v, i) => (v !== null ? i + 1 : m), 0)));   // ile faz ma ta strona (1–3)
      const trio = (vals, n, d, unit) => vals.slice(0, n).map(v => (v === null ? '—' : this._fx(v, d))).join(' · ') + ` ${unit}`;
      const lab = (txt, n) => `${txt} ${['L1', 'L2', 'L3'].slice(0, n).join(' · ')}`;
      const lf = x(['load_frequency', 'output_frequency'], 1);
      const gf = x(['grid_frequency'], 2);
      const lvs = ph(['load_l#_voltage', 'output_l#_voltage'], ['load_voltage', 'output_voltage']);
      const lcs = ph(['load_l#_current', 'output_l#_current'], ['load_current']);
      const lps = ph(['load_l#_power', 'output_l#_power'], []);
      const gvs = ph(['grid_l#_voltage'], ['grid_voltage']);
      const gcs = ph(['grid_l#_current', 'external_ct#_current'], ['grid_current']);
      const gps = ph(['grid_l#_power', 'external_ct#_power'], []);
      const fr = (f) => (f ? row('Częstotliwość', `${f} Hz`) : null);
      if (multi(lvs) || multi(lcs) || multi(lps)) {
        const n = nPh(lvs, lcs, lps);
        d.home = [lvs.some(v => v !== null) && row(lab('Napięcie', n), trio(lvs, n, 0, 'V')), fr(lf),
                  lcs.some(v => v !== null) && row(lab('Prąd', n), trio(lcs, n, 1, 'A')),
                  lps.some(v => v !== null) && row(lab('Moc', n), trio(lps, n, 0, 'W'))].filter(Boolean);
      } else {
        const lv = this._fx(lvs[0], 0), lc = this._fx(lcs[0], 1);
        d.home = [row('Napięcie · częstotliwość', join(lv && `${lv} V`, lf && `${lf} Hz`)), row('Prąd', lc && `${lc} A`)].filter(Boolean);
      }
      if (multi(gvs) || multi(gcs) || multi(gps)) {
        const n = nPh(gvs, gcs, gps);
        d.grid = [gvs.some(v => v !== null) && row(lab('Napięcie', n), trio(gvs, n, 0, 'V')), fr(gf),
                  gcs.some(v => v !== null) && row(lab('Prąd', n), trio(gcs, n, 1, 'A')),
                  gps.some(v => v !== null) && row(lab('Moc', n), trio(gps, n, 0, 'W'))].filter(Boolean);
      } else {
        const gv = this._fx(gvs[0], 0), gc = this._fx(gcs[0], 1);
        d.grid = [row('Napięcie · częstotliwość', join(gv && `${gv} V`, gf && `${gf} Hz`)), row('Prąd', gc && `${gc} A`)].filter(Boolean);
      }
      const bv = x(['battery_voltage'], 1);
      let ba = this._xv(['battery_current']);
      if (ba !== null && INVERT_BATTERY_SIGN) ba = -ba;
      const bt = x(['battery_temperature'], 0);
      d.batt = [row('Napięcie · prąd', join(bv && `${bv} V`, ba !== null ? `${this._fx(ba)} A` : null)), row('Temperatura baterii', bt && `${bt} °C`)].filter(Boolean);
      return d;
    }

    // Ekran główny w stylu Material 3 (tylko gdy włączony styl „Material 3” w Ustawieniach → Wygląd): karta baterii z paskiem
    // rezerwy i celu, schemat przepływu z „pigułkami”, kafelki zysku/PV/ceny i pasek planu na 24 h. Dane te same co w klasycznym.
    _drawM3Home(box, o0) {
      const o = this._skFin(o0);
      const ra = this._rsAttrs(), pvA = this._pvAttrs(), TH = 20;
      const soc = o.soc, flr = Number(ra.inverter_floor);
      let cap = parseFloat(ra.capacity_kwh);
      if (!(cap > 0)) { try { cap = parseFloat(localStorage.getItem('bms_panel_capacity')); } catch (e) { cap = NaN; } }
      const rows = Array.isArray(pvA.table) ? pvA.table.filter(r => r && r.day) : [];
      const endRow = rows.filter(r => r.day === this._todayKey() && r.h === 23).pop();
      const tgt = endRow ? Number(endRow.soc) : NaN;
      const profit = this._profitToday();
      const pb = Number(ra.price_buy), ps = Number(ra.price_sell);
      const now = new Date(), nowH = now.getHours();
      const todayK = this._todayKey();
      const plan = rows.filter(r => r.day > todayK || (r.day === todayK && r.h >= nowH))
        .sort((a, b) => (a.day === b.day ? a.h - b.h : (a.day < b.day ? -1 : 1))).slice(0, 24);
      const chipsH = this._skChips(Object.assign({}, o, { flr, tgt }), 'm3');
      const dv = this._devNodes();
      const key = JSON.stringify([THEME.mode, dv.sig, Math.round(o.pv / 10), Math.round(o.load / 10), Math.round(o.grid / 10), Math.round(o.batt / 10),
        Math.round(soc), flr, tgt, cap, isFinite(profit) ? profit.toFixed(2) : null, pb, ps, o.D.pv, nowH, plan.map(r => r.action).join(','), JSON.stringify(o.dayTxt || {}), chipsH.sig]);
      if (key === this._lastM3Key) return;
      this._lastM3Key = key;
      const f1 = (v) => (Math.round(v * 10) / 10).toFixed(1).replace('.', ',');
      const zl = (v) => (isFinite(v) ? v.toFixed(2).replace('.', ',') : '—');
      // karta baterii
      const hasFl = isFinite(flr) && flr > 0 && flr < 100, hasT = isFinite(tgt) && tgt > 0 && tgt <= 100;
      const battTxt = o.batt > TH ? `+${this._fmtW(o.batt)} ładowanie` : (o.batt < -TH ? `−${this._fmtW(-o.batt)} rozładowanie` : 'bateria w spoczynku');
      const hero = `<div class="m3-hero">
        <div class="m3-top"><div><div class="m3-lbl">Bateria</div><div class="m3-big">${Math.round(soc)}<span>%</span></div></div>
          <div class="m3-right">${cap > 0 ? `<b>${f1(cap * soc / 100)} kWh</b><br>` : ''}${bmsEsc(battTxt)}</div></div>
        <div class="m3-lp"><div class="v" style="width:${Math.max(0, Math.min(100, soc))}%"></div>${hasFl ? `<div class="m" style="left:${flr}%"></div>` : ''}${hasT ? `<div class="m" style="left:${tgt}%"></div>` : ''}</div>
        <div class="m3-lg">${hasFl ? `<span style="left:${flr}%">rezerwa ${Math.round(flr)}%</span>` : ''}${hasT ? `<span style="left:${tgt}%">plan na koniec dnia ${Math.round(tgt)}%</span>` : ''}</div></div>`;
      // schemat przepływu: pigułki PV / sieć / bateria / dom wokół węzła
      const hub = { x: 170, y: 62 };
      const act = { pv: o.pv > TH, home: o.load > TH, grid: Math.abs(o.grid) > TH, batt: Math.abs(o.batt) > TH };
      const col = { pv: 'var(--m3-pv)', home: 'var(--accent)', grid: o.grid > 0 ? 'var(--red)' : 'var(--m3-grid)', batt: o.batt < 0 ? 'var(--orange)' : 'var(--m3-batt)' };
      // kierunek: 1 = węzeł → węzeł centralny, -1 = od centralnego do węzła
      const dir = { pv: 1, home: -1, grid: o.grid >= 0 ? 1 : -1, batt: o.batt < 0 ? 1 : -1 };
      const path = { pv: [170, 36, 170, 62], grid: [120, 98, 170, 62], batt: [220, 98, 170, 62], home: [170, 62, 170, 100] };
      const line = (k) => { const [x1, y1, x2, y2] = path[k]; const rev = (k !== 'home' && dir[k] < 0) || (k === 'home' && false);
        const d = rev ? `M${x2} ${y2}L${x1} ${y1}` : (k === 'home' && dir.home > 0 ? `M${x2} ${y2}L${x1} ${y1}` : `M${x1} ${y1}L${x2} ${y2}`);
        return act[k] ? `<path d="${d}" class="nf-line" stroke="${col[k]}" stroke-width="3"/>` : `<path d="${d}" class="nf-idle"/>`; };
      const pill = (x, y, w, bg, fg, txt) => `<rect x="${x}" y="${y}" width="${w}" height="30" rx="15" fill="${bg}"/><text x="${x + w / 2}" y="${y + 20}" text-anchor="middle" fill="${fg}">${txt}</text>`;
      const gTxt = Math.abs(o.grid) > TH ? `${o.grid > 0 ? '⚡ import' : '⚡ eksport'} ${this._fmtW(Math.abs(o.grid))}` : '⚡ sieć ' + this._fmtW(Math.abs(o.grid));
      const bTxt = `🔋 ${o.batt > TH ? '+' : (o.batt < -TH ? '−' : '')}${this._fmtW(Math.abs(o.batt))}`;
      const dt = o.dayTxt || {};
      const dayRow = (dt.pv || dt.home || dt.grid || dt.batt) ? `<div class="m3-day">${[['☀', dt.pv], ['🏠', dt.home], ['⚡', dt.grid], ['🔋', dt.batt]].filter((x) => x[1]).map((x) => `<span>${x[0]} ${bmsEsc(x[1])}</span>`).join('')}</div>` : '';
      const dvp = this._devPills(dv, 136);
      const flow = `<div class="m3-flow"><div class="m3-ct">Przepływ mocy<small>teraz</small></div>
        <svg viewBox="0 0 340 ${Math.max(140, Math.ceil(dvp.bottom) + 4)}" role="img" aria-label="Przepływ mocy">
          <g fill="none" stroke-linecap="round">${line('pv')}${line('grid')}${line('batt')}${line('home')}</g>
          <circle cx="${hub.x}" cy="${hub.y}" r="6" fill="var(--seg-bg)" stroke="var(--muted2)"/>
          ${pill(125, 4, 90, 'var(--m3-pvc)', 'var(--m3-pvt)', '☀ ' + this._fmtW(o.pv))}
          ${pill(4, 84, 116, 'var(--m3-gridc)', 'var(--m3-gridt)', gTxt)}
          ${pill(220, 84, 116, 'var(--seg-active)', 'var(--text)', bTxt)}
          ${pill(125, 106, 90, 'var(--tonal)', 'var(--on-tonal)', '🏠 ' + this._fmtW(o.load))}
          ${dvp.svg}
          <rect class="nf-hit" data-k="pv" x="120" y="0" width="100" height="38"/><rect class="nf-hit" data-k="grid" x="0" y="80" width="124" height="38"/><rect class="nf-hit" data-k="batt" x="216" y="80" width="124" height="38"/><rect class="nf-hit" data-k="home" x="120" y="102" width="100" height="38"/>
        </svg>${dayRow}</div>`;
      // kafelki
      const kpis = `<div class="m3-kpis">
        <div class="m3-kpi"><div class="l">Zysk dziś</div><div class="v" style="color:${isFinite(profit) && profit < 0 ? 'var(--red)' : 'var(--green)'}">${isFinite(profit) ? (profit >= 0 ? '+' : '−') + zl(Math.abs(profit)) + ' zł' : '—'}</div><div class="s">bilans EMS</div></div>
        <div class="m3-kpi"><div class="l">PV dziś</div><div class="v">${o.D.pv === null ? '—' : f1(o.D.pv) + ' kWh'}</div><div class="s">${o.pv > TH ? 'teraz ' + this._fmtW(o.pv) : 'teraz brak'}</div></div></div>`;
      // pasek planu na 24 h
      const cmap = { grid: 'var(--m3-grid)', sell: 'var(--m3-sell)', pv: 'var(--m3-pv)', home: 'var(--m3-batt)', idle: 'var(--m3-idle)' };
      let strip = '';
      if (plan.length >= 6) {
        const ticks = [0, 6, 12, 18].filter(i => i < plan.length).map(i => `<span>${i === 0 ? 'teraz' : String(plan[i].h).padStart(2, '0') + ':00'}</span>`).join('');
        strip = `<div class="m3-strip-card"><div class="m3-ct">Najbliższe 24 h<small>plan</small></div>
          <div class="m3-strip">${plan.map((r, i) => `<i class="${i === 0 ? 'now' : ''}" style="background:${cmap[r.action] || cmap.idle}" title="${String(r.h).padStart(2, '0')}:00 — ${bmsEsc(r.label || '')}"></i>`).join('')}</div>
          <div class="m3-ax">${ticks}</div>
          <div class="m3-leg"><span style="background:var(--m3-gridc);color:var(--m3-gridt)">z sieci</span><span style="background:var(--m3-sellc);color:var(--m3-sellt)">sprzedaż</span><span style="background:var(--m3-pvc);color:var(--m3-pvt)">PV</span><span style="background:var(--seg-active);color:var(--text)">z baterii</span></div></div>`;
      }
      box.innerHTML = `<div class="m3-home">${hero}${flow}${kpis}${chipsH.html}${strip}</div>`;
      this._bindCapInput(box); this._devPopRefresh();
    }

    // ---------- „Co EMS planuje na najbliższe 24 h”: opis planu godzinowego (tabela planu, mała karta) ----------
    _planSummary(rows0, nowMs) {
      const now = nowMs || Date.now(), HR = 3600000;
      const rows = (Array.isArray(rows0) ? rows0 : []).map((r) => (r && r.t ? Object.assign({}, r, { ts: Date.parse(r.t) }) : null)).filter((r) => r && isFinite(r.ts)).sort((a, b) => a.ts - b.ts);
      const cur = rows.filter((r) => r.ts + HR > now && r.ts < now + 24 * HR).slice(0, 24);
      if (!cur.length) return null;
      const wins = []; let cu = null;
      cur.forEach((r) => {
        const k = r.action === 'grid' || r.action === 'sell' || r.action === 'pv' ? r.action : null;
        if (k && cu && cu.k === k && r.ts === cu.end) { cu.end = r.ts + HR; cu.n++; } else { if (cu) wins.push(cu); cu = k ? { k, start: r.ts, end: r.ts + HR, n: 1 } : null; }
      });
      if (cu) wins.push(cu);
      const num = (v) => (v !== null && v !== '' && v !== undefined && isFinite(Number(v)) ? Number(v) : null);
      let min = null, cost = 0, imp = 0, exp = 0;
      cur.forEach((r) => { const v = num(r.soc); if (v !== null && (min === null || v < min.soc)) min = { soc: v, ts: r.ts }; cost += num(r.cost) || 0; imp += num(r.import_kwh) || 0; exp += num(r.export_kwh) || 0; });
      const last = cur[cur.length - 1], le = num(last.soc);
      return { cur, wins, min, end: le === null ? null : { soc: le, ts: last.ts + HR }, cost, imp, exp, now };
    }
    _planSummaryHtml(rows, nowMs) {
      const s = this._planSummary(rows, nowMs); if (!s) return '';
      const E = bmsEsc, today = this._todayKey(), tom = this._tomorrowKey(), dk = (ts) => this._dateKey(new Date(ts));
      const hh = (ts) => String(new Date(ts).getHours()).padStart(2, '0') + ':00';
      const day = (ts) => { const k = dk(ts); return k === today ? '' : (k === tom ? 'jutro ' : k.slice(8, 10) + '.' + k.slice(5, 7) + ' '); };
      const win = (w) => `${w.start <= s.now ? 'teraz' : day(w.start) + hh(w.start)}–${hh(w.end)} (${w.n} h)`;
      const fz = (v) => Math.abs(v).toFixed(2).replace('.', ',') + ' zł';
      const line = (ico, label, k, none) => {
        const w = s.wins.filter((x) => x.k === k);
        const t = w.length ? w.slice(0, 3).map(win).join(', ') + (w.length > 3 ? ` i jeszcze ${w.length - 3}` : '') : none;
        return `<div class="ps-l"><i aria-hidden="true">${ico}</i><span><b>${E(label)}:</b> ${E(t)}</span></div>`;
      };
      const soc = s.min ? `<div class="ps-l"><i aria-hidden="true">🔋</i><span><b>Bateria:</b> najniżej ${Math.round(s.min.soc)}% (${E(day(s.min.ts) + hh(s.min.ts))})${s.end ? `, na koniec okresu ${Math.round(s.end.soc)}% (${E(day(s.end.ts) + hh(s.end.ts))})` : ''}</span></div>` : '';
      const bil = s.cost > 0.005 ? 'koszt ' + fz(s.cost) : (s.cost < -0.005 ? 'przychód ' + fz(s.cost) : 'bilans około 0 zł');
      let psOpen = true; try { psOpen = localStorage.getItem('bms_ps_open') !== '0'; } catch (e) { /* brak pamięci przeglądarki: domyślnie rozwinięte */ }
      return `<details class="ps" data-ps${psOpen ? ' open' : ''} aria-label="Plan EMS na najbliższe 24 godziny"><summary class="ps-h">🧭 Co EMS planuje na najbliższe 24 h</summary>
        ${line('⚡', 'Ładowanie z sieci', 'grid', 'nie planuje')}${line('☀️', 'Ładowanie z PV', 'pv', 'brak')}${line('💰', 'Sprzedaż z baterii', 'sell', 'nie planuje')}${soc}
        <div class="ps-l"><i aria-hidden="true">💵</i><span><b>Szacunek:</b> ${E(bil)} · pobór ${s.imp.toFixed(1).replace('.', ',')} kWh, oddanie ${s.exp.toFixed(1).replace('.', ',')} kWh</span></div>
        <div class="ps-n">To szacunek z prognoz — EMS przelicza plan na bieżąco i może go zmienić.</div></details>`;
    }
    // bieżące moce i SOC (jak na ekranie głównym) — dla małej karty
    _flowNow() {
      let pv = Math.max(0, this._num('pv_power'));
      if (pv < 1) {
        const pv1 = parseFloat(this._st(this._inv('sensor', 'pv1_power'))) || 0, pv2 = parseFloat(this._st(this._inv('sensor', 'pv2_power'))) || 0;
        if (pv1 + pv2 > 1) pv = pv1 + pv2;
      }
      const battRaw = this._num('battery_power');
      return this._skFin({ pv, load: Math.max(0, this._num('load_power')), grid: this._num('grid_power'), batt: INVERT_BATTERY_SIGN ? -battRaw : battRaw, soc: this._num('soc') });
    }

    // ---------- wspólny ekran główny stylów Szkło / Matryca / Przestrzeń / Komfort ----------
    // Dane jak w stylu Material 3 (bateria z rezerwą i celem, przepływ mocy, zysk/PV/cena, plan 24 h); różni się tylko sposób rysowania.
    // zabezpieczenie: moce i SOC zawsze skończone (brak odczytu = 0), żeby na ekranie nie pojawiło się „NaN W”
    _skFin(o) { const f = (v) => (isFinite(v) ? Number(v) : 0); return Object.assign({}, o, { pv: f(o.pv), load: f(o.load), grid: f(o.grid), batt: f(o.batt), soc: Math.max(0, Math.min(100, f(o.soc))) }); }

    // ---------- urządzenia przy węźle „dom” (wszystkie style) ----------
    // Pokazujemy WYŁĄCZNIE urządzenia już dodane w zakładce „Urządzenia” (sensor.bms_devices → atrybut devices — to samo źródło
    // co kafelki „Urządzenia — teraz”); brak urządzeń = nic na schemacie. Na schemacie: ikona + moc, reszta danych (nazwa, stan,
    // dziś kWh i zł, pokój) w okienku po dotknięciu. Do 4 miejsc; przy większej liczbie 3 urządzenia + „+N” z resztą w okienku.
    _devNodes() {
      const st = this._hass && this._hass.states ? this._hass.states[this._eid('sensor', 'devices')] : null;
      if (this._dvNSt === st && this._dvN) return this._dvN;          // HA podmienia obiekt stanu przy zmianie — stary wynik jest aktualny
      const a = st && st.attributes, raw = a && Array.isArray(a.devices) ? a.devices : [];
      const num = (v) => { if (v === null || v === undefined || v === '') return null; const n = Number(v); return isFinite(n) ? n : null; };
      const q = (p) => (p < 50 ? Math.round(p) : Math.round(p / 5) * 5);   // do klucza przerysowania: drobne drgania mocy nie przerysowują schematu
      const all = raw.filter((d) => d && d.id !== undefined && d.id !== null && d.id !== '').map((d, i) => {
        const p = num(d.power), run = !!d.running;
        return { id: String(d.id), key: 'dev:' + d.id, i, name: String(d.name || d.id), icon: String(d.icon || '🔌'), room: String(d.room || ''), cat: String(d.category || ''),
          power: p, kwh: num(d.today_kwh), cost: num(d.today_cost), run, w: p === null ? '—' : this._fmtW(Math.max(0, p)), qw: p === null ? null : q(Math.max(0, p)) };
      });
      const MAX = 4;
      let items = all, rest = [];
      if (all.length > MAX) {
        // przy nadmiarze: najpierw pracujące, potem największe dzienne zużycie; wyświetlane w kolejności z zakładki
        const pick = all.slice().sort((x, y) => (y.run - x.run) || ((y.kwh || 0) - (x.kwh || 0)) || (x.i - y.i)).slice(0, MAX - 1).sort((x, y) => x.i - y.i);
        const ids = new Set(pick.map((x) => x.id));
        rest = all.filter((x) => !ids.has(x.id));
        const sum = rest.reduce((s, x) => s + (x.power || 0), 0);
        items = pick.concat([{ id: '+', key: 'dev:+', more: true, n: rest.length, name: `Pozostałe urządzenia (${rest.length})`, icon: '', room: '', cat: '', power: sum,
          kwh: null, cost: null, run: rest.some((x) => x.run), w: this._fmtW(sum), qw: q(sum), rest }]);
      }
      const sig = JSON.stringify(all.map((x) => [x.id, x.name, x.icon, x.run ? 1 : 0, x.qw, x.kwh === null ? null : x.kwh.toFixed(2), x.cost === null ? null : x.cost.toFixed(2), x.room]));
      this._dvNSt = st; return (this._dvN = { items, all, sig, n: all.length });
    }
    // okienko po dotknięciu satelity: te same dane co kafelek w zakładce „Urządzenia” (ikona, nazwa, moc, „pracuje”, dziś kWh · zł, pokój)
    _devPopHtml(k) {
      const D = this._devNodes(), it = D.items.find((x) => x.key === k);
      if (!it) return '';
      const qa = (s) => bmsEsc(s).replace(/"/g, '&quot;');
      const kwh = (v) => (v === null ? '—' : v.toFixed(2).replace('.', ',') + ' kWh'), zl = (v) => (v === null ? '—' : v.toFixed(2).replace('.', ',') + ' zł');
      const pw = (d) => (d.power === null ? '—' : this._fmtW(Math.max(0, d.power)));
      const x = '<button class="np-x" type="button" aria-label="Zamknij">×</button>';
      const go = this._laySimple() ? '' : '<button class="np-go" type="button" data-go="dev">Wszystkie urządzenia →</button>';
      if (it.more) {
        const rows = it.rest.map((d) => `<span>${bmsEsc(d.icon)} ${bmsEsc(d.name)}${d.run ? ' · pracuje' : ''}</span><b>${pw(d)} · dziś ${kwh(d.kwh)} · ${zl(d.cost)}</b>`).join('');
        return `<div class="np-head"><span>${bmsEsc(it.name)}</span><span>${x}</span></div><div class="np-det">${rows}</div>${go}`;
      }
      const rows = [['Stan', it.run ? 'pracuje' : 'nie pracuje'], ['Dziś', kwh(it.kwh)], ['Koszt dziś', zl(it.cost)]];
      if (it.room) rows.push(['Pokój', bmsEsc(it.room)]);
      return `<div class="np-head"><span>${bmsEsc(it.icon)} ${bmsEsc(it.name)}${it.run ? ' <em class="np-run">pracuje</em>' : ''}</span><span><b>${pw(it)}</b>${x}</span></div>
        <div class="np-det" data-dev="${qa(it.id)}">${rows.map(([l, v]) => `<span>${l}</span><b>${v}</b>`).join('')}</div>${go}`;
    }
    // odświeża otwarte okienko urządzenia (po przerysowaniu schematu); zniknęło urządzenie → zamyka okienko
    _devPopRefresh() {
      const k = this._popK; if (!k || String(k).slice(0, 4) !== 'dev:') return;
      const pop = this._el('nodePop'); if (!pop || pop.hidden) return;
      const h = this._devPopHtml(k);
      if (!h) { this._hidePop(); return; }
      if (pop.dataset.h !== h) { pop.dataset.h = h; pop.innerHTML = h; this._placePop(); }
    }
    // Rysowanie satelitów jako fragment SVG. o: { cx, top, step, r, g1, g2, minX, maxX, st } — cx: oś węzła „dom”, top: dół jego opisów,
    // st: kolory stylu { fill, on, off, flow, matrix }. Zwraca { svg, bottom } (bottom = dolna krawędź rysunku) albo pustkę, gdy brak urządzeń.
    _devSat(D, o) {
      const items = D.items, n = items.length;
      if (!n) return { svg: '', bottom: o.top };
      const span = (n - 1) * o.step;
      const x0 = Math.max(o.minX, Math.min(o.maxX - span, o.cx - span / 2));
      const xs = items.map((_, i) => x0 + i * o.step);
      const rail = o.top + o.g1, drop = rail + o.g2, cy = drop + o.r, lab = cy + o.r + o.lh, st = o.st;
      const anyRun = items.some((x) => x.run);
      const qa = (s) => bmsEsc(s).replace(/"/g, '&quot;');
      const f = (v) => +v.toFixed(1);
      let s = anyRun
        ? `<path d="M${o.cx} ${o.top} L${o.cx} ${rail}" class="nf-line" stroke="${st.flow}" stroke-width="2.5"/>`
        : `<path d="M${o.cx} ${o.top} L${o.cx} ${rail}" class="nf-idle"/>`;
      if (n > 1 || xs[0] !== o.cx) s += `<path d="M${f(Math.min(o.cx, xs[0]))} ${rail} L${f(Math.max(o.cx, xs[n - 1]))} ${rail}" class="nf-idle"/>`;
      items.forEach((it, i) => {
        const x = f(xs[i]), col = it.run ? st.on : st.off;
        s += `<g class="nf-dv${it.run ? ' on' : ''}" role="img" aria-label="${qa(it.name)}: ${qa(it.w)}${it.run ? ', pracuje' : ''}"><title>${bmsEsc(it.name)}</title>`
          + (it.run ? `<path d="M${x} ${rail} L${x} ${drop}" class="nf-line" stroke="${st.on}" stroke-width="2"/>` : `<path d="M${x} ${rail} L${x} ${drop}" class="nf-idle"/>`)
          + (st.matrix ? `<circle cx="${x}" cy="${f(cy)}" r="${o.r}" fill="none" stroke="${col}" stroke-width="${it.run ? 1.6 : 1.1}"/>`
            : `<circle cx="${x}" cy="${f(cy)}" r="${o.r}" style="fill:${st.fill};stroke:${col}" stroke-width="${it.run ? 2.5 : 1.8}"/>`)
          + (it.more ? `<text x="${x}" y="${f(cy + o.r * 0.3)}" text-anchor="middle" class="nf-dvm">+${it.n}</text>`
            : `<text x="${x}" y="${f(cy + o.r * 0.32)}" text-anchor="middle" font-size="${Math.round(o.r * 0.9)}"${it.run ? '' : ' opacity=".55"'}>${bmsEsc(it.icon)}</text>`)
          + `<text x="${x}" y="${f(lab)}" text-anchor="middle" class="nf-dvw${it.run ? '' : ' off'}">${bmsEsc(it.w)}</text></g>`
          + `<rect class="nf-hit" data-k="${qa(it.key)}" x="${f(x - o.step / 2)}" y="${f(cy - o.r - 3)}" width="${o.step}" height="${f(lab + 7 - (cy - o.r - 3))}"/>`;
      });
      return { svg: s, bottom: lab + 8 };
    }
    // Material 3: satelity jako pigułki w jednym rzędzie pod pigułką „dom”; y0 = dół pigułki „dom”. Zwraca { svg, bottom }
    _devPills(D, y0) {
      const items = D.items, n = items.length;
      if (!n) return { svg: '', bottom: y0 };
      const gap = 6, pw = Math.min(100, Math.floor((322 - (n - 1) * gap) / n)), tot = n * pw + (n - 1) * gap, x0 = (340 - tot) / 2;
      const rail = y0 + 10, py = rail + 8, ph = 26, qa = (s) => bmsEsc(s).replace(/"/g, '&quot;');
      const anyRun = items.some((x) => x.run);
      let s = anyRun ? `<path d="M170 ${y0} L170 ${rail}" class="nf-line" stroke="var(--accent)" stroke-width="2.5"/>` : `<path d="M170 ${y0} L170 ${rail}" class="nf-idle"/>`;
      const first = x0 + pw / 2, last = x0 + (n - 1) * (pw + gap) + pw / 2;
      if (n > 1) s += `<path d="M${Math.min(170, first)} ${rail} L${Math.max(170, last)} ${rail}" class="nf-idle"/>`;
      items.forEach((it, i) => {
        const x = x0 + i * (pw + gap), mid = x + pw / 2;
        s += `<g class="nf-dv${it.run ? ' on' : ''}" role="img" aria-label="${qa(it.name)}: ${qa(it.w)}${it.run ? ', pracuje' : ''}"><title>${bmsEsc(it.name)}</title>`
          + `<path d="M${mid} ${rail} L${mid} ${py}" ${it.run ? 'class="nf-line" stroke="var(--accent)" stroke-width="2"' : 'class="nf-idle"'}/>`
          + `<rect x="${x}" y="${py}" width="${pw}" height="${ph}" rx="${ph / 2}" fill="${it.run ? 'var(--tonal)' : 'var(--seg-bg)'}"/>`
          + `<text x="${mid}" y="${py + 17}" text-anchor="middle" fill="${it.run ? 'var(--on-tonal)' : 'var(--muted)'}" style="font-weight:${it.run ? 700 : 500}">${it.more ? '+' + it.n : bmsEsc(it.icon)} ${bmsEsc(it.w)}</text></g>`
          + `<rect class="nf-hit" data-k="${qa(it.key)}" x="${x}" y="${py - 4}" width="${pw}" height="${ph + 8}"/>`;
      });
      return { svg: s, bottom: py + ph + 4 };
    }
    _homeModel(o) {
      const ra = this._rsAttrs(), pvA = this._pvAttrs(), TH = 20, soc = o.soc, flr = Number(ra.inverter_floor);
      let cap = parseFloat(ra.capacity_kwh);
      if (!(cap > 0)) { try { cap = parseFloat(localStorage.getItem('bms_panel_capacity')); } catch (e) { cap = NaN; } }
      const rows = Array.isArray(pvA.table) ? pvA.table.filter(r => r && r.day) : [];
      const todayK = this._todayKey(), nowH = new Date().getHours();
      const endRow = rows.filter(r => r.day === todayK && r.h === 23).pop();
      const tgt = endRow ? Number(endRow.soc) : NaN;
      const profit = this._profitToday();
      const plan = rows.filter(r => r.day > todayK || (r.day === todayK && r.h >= nowH))
        .sort((a, b) => (a.day === b.day ? a.h - b.h : (a.day < b.day ? -1 : 1))).slice(0, 24);
      const hasFl = isFinite(flr) && flr > 0 && flr < 100, hasT = isFinite(tgt) && tgt > 0 && tgt <= 100;
      let pace = '';
      if (cap > 0) {
        const usable = Math.max(0, cap * (soc - (hasFl ? flr : 20)) / 100);
        if (o.batt > TH && soc < 99.5) pace = `pełna ok. ${this._fmtAt((100 - soc) / 100 * cap / (o.batt / 1000))}`;
        else if (o.batt < -TH && usable > 0) pace = `do rezerwy ok. ${this._fmtAt(usable / (-o.batt / 1000))}`;
      }
      const battTxt = o.batt > TH ? `+${this._fmtW(o.batt)} ładowanie` : (o.batt < -TH ? `−${this._fmtW(-o.batt)} rozładowanie` : 'bateria w spoczynku');
      return { o, TH, soc, flr, cap, tgt, profit, pb: Number(ra.price_buy), ps: Number(ra.price_sell), plan, hasFl, hasT, pace, battTxt, nowH,
        act: { pv: o.pv > TH, home: o.load > TH, grid: Math.abs(o.grid) > TH, batt: Math.abs(o.batt) > TH }, dev: this._devNodes() };
    }
    // tekst z kwadratowych pikseli (styl Matryca); zwraca gotowy <svg> oraz jego wymiary i same znaczniki
    _skDots(text, cell, color) {
      const ch = [...String(text).toUpperCase()], w = Math.max(1, ch.length * 6 * cell - cell), h = 7 * cell, s = cell * 0.72, off = (cell - s) / 2;
      let d = '';
      ch.forEach((c, i) => (SK_GLYPHS[c] || SK_GLYPHS[' ']).split(',').forEach((row, y) => {
        for (let x = 0; x < row.length; x++) if (row[x] === '1') d += `<rect x="${((i * 6 + x) * cell + off).toFixed(2)}" y="${(y * cell + off).toFixed(2)}" width="${s.toFixed(2)}" height="${s.toFixed(2)}" rx="${(cell * 0.14).toFixed(2)}"/>`;
      }));
      return { w, h, d, svg: `<svg class="sk-dots" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" style="fill:${color}" role="img" aria-label="${bmsEsc(String(text))}">${d}</svg>` };
    }
    // pierścień naładowania: „flat” (Komfort), „grad” (Szkło, Przestrzeń) albo „matrix” (kwadratowe piksele)
    _skRing(m, kind) {
      const soc = Math.max(0, Math.min(100, m.soc)), cx = 60, cy = 60, rad = Math.PI / 180;
      const at = (r, p) => [cx + r * Math.cos((p * 360 - 90) * rad), cy + r * Math.sin((p * 360 - 90) * rad)];
      if (kind === 'matrix') {
        const R = 51, N = 60; let s = '';
        for (let i = 0; i < N; i++) {
          const p = i / N, lit = p < soc / 100, [x, y] = at(R, p), z = lit ? 5.4 : 3.6;
          s += `<rect x="${(x - z / 2).toFixed(1)}" y="${(y - z / 2).toFixed(1)}" width="${z}" height="${z}" rx="1" transform="rotate(${(p * 360).toFixed(1)} ${x.toFixed(1)} ${y.toFixed(1)})" style="fill:${lit ? 'var(--sk-on)' : 'var(--sk-off)'}"/>`;
        }
        if (m.hasFl) { const [x, y] = at(R, m.flr / 100); s += `<rect x="${(x - 4.5).toFixed(1)}" y="${(y - 4.5).toFixed(1)}" width="9" height="9" rx="1.5" transform="rotate(${(m.flr * 3.6).toFixed(1)} ${x.toFixed(1)} ${y.toFixed(1)})" fill="none" style="stroke:var(--sk-on)" stroke-width="1.4"/>`; }
        if (m.hasT) { const [x, y] = at(R, m.tgt / 100); s += `<rect x="${(x - 4.5).toFixed(1)}" y="${(y - 4.5).toFixed(1)}" width="9" height="9" rx="1.5" transform="rotate(${(m.tgt * 3.6).toFixed(1)} ${x.toFixed(1)} ${y.toFixed(1)})" style="fill:var(--sk-acc)"/>`; }
        const t = this._skDots(Math.round(soc) + '%', 4, 'var(--sk-on)');
        return `<svg class="sk-ring" viewBox="0 0 120 120" role="img" aria-label="Poziom baterii ${Math.round(soc)}%">${s}<g transform="translate(${(cx - t.w / 2).toFixed(1)} ${(cy - t.h / 2).toFixed(1)})" style="fill:var(--sk-on)">${t.d}</g></svg>`;
      }
      const r = 46, c = 2 * Math.PI * r, grad = kind === 'grad', sw = grad ? 15 : 13;
      let s = grad ? '<defs><linearGradient id="skrg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" style="stop-color:var(--sk-ring1)"/><stop offset="1" style="stop-color:var(--sk-ring2)"/></linearGradient></defs>' : '';
      s += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" style="stroke:var(--sk-idle)" stroke-width="${sw}"/>`;
      s += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" style="stroke:${grad ? 'url(#skrg)' : 'var(--sk-batt)'}" stroke-width="${sw}" stroke-linecap="round" stroke-dasharray="${(c * soc / 100).toFixed(1)} ${c.toFixed(1)}" transform="rotate(-90 ${cx} ${cy})"/>`;
      if (m.hasFl) { const [x1, y1] = at(r - sw / 2 - 2, m.flr / 100), [x2, y2] = at(r + sw / 2 + 2, m.flr / 100); s += `<path d="M${x1.toFixed(1)} ${y1.toFixed(1)}L${x2.toFixed(1)} ${y2.toFixed(1)}" style="stroke:var(--text)" stroke-width="2.5" stroke-linecap="round" opacity=".85"/>`; }
      if (m.hasT) { const [x, y] = at(r, m.tgt / 100); s += grad ? `<path d="M${x.toFixed(1)} ${(y - 6).toFixed(1)}l5 6-5 6-5-6z" style="fill:var(--text)"/>` : `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4.5" style="fill:var(--card);stroke:var(--text)" stroke-width="2"/>`; }
      s += `<text x="${cx}" y="${cy + 10}" text-anchor="middle" font-weight="600" font-size="30" letter-spacing="-1" style="fill:var(--text);font-family:inherit">${Math.round(soc)}<tspan font-size="15" dy="-10">%</tspan></text>`;
      return `<svg class="sk-ring" viewBox="0 0 120 120" role="img" aria-label="Poziom baterii ${Math.round(soc)}%">${s}</svg>`;
    }
    // schemat przepływu mocy: „sphere” (szklane kule), „tint” (kółka w odcieniu koloru, strzałki kierunku), „matrix” (kropkowane linie, konturowe ikony)
    _skFlow(m, kind) {
      const o = m.o, TH = m.TH, act = m.act, mx = kind === 'matrix';
      const col = { pv: 'var(--sk-pv)', home: 'var(--accent)', grid: o.grid > 0 ? 'var(--red)' : 'var(--sk-grid)', batt: o.batt < 0 ? 'var(--orange)' : 'var(--sk-batt)' };
      const P = { pv: [170, 28], grid: [50, 94], batt: [290, 94], home: [170, 130] }, hub = [170, 94];
      // kierunek strzałki: pv → hub, grid → hub (import) lub hub → grid (eksport), hub → bateria (ładowanie) lub bateria → hub, hub → dom
      const rev = { grid: o.grid < 0, batt: o.batt < 0 };
      const seg = { pv: [170, 54, 170, 92], grid: [76, 94, 164, 94], batt: [176, 94, 264, 94], home: [170, 98, 170, 104] };
      const ln = (k) => {
        const [x1, y1, x2, y2] = seg[k];
        if (!act[k]) return `<path d="M${x1} ${y1}L${x2} ${y2}" style="stroke:${mx ? 'var(--sk-off)' : 'var(--sk-idle)'}" stroke-width="2.5" stroke-linecap="round"/>`;
        if (mx) return `<path d="M${x1} ${y1}L${x2} ${y2}" style="stroke:${k === 'grid' && o.grid > 0 ? 'var(--sk-acc)' : 'var(--sk-on)'}" stroke-width="3.2" stroke-dasharray="3.2 4.8"/>`;
        const glow = kind === 'sphere' ? `<path d="M${x1} ${y1}L${x2} ${y2}" style="stroke:${col[k]}" stroke-width="7" stroke-linecap="round" opacity=".35" filter="url(#skbl)"/>` : '';
        const arrow = kind === 'tint' && k !== 'home' ? (() => { const mx2 = (x1 + x2) / 2, my2 = (y1 + y2) / 2, back = rev[k];
          return k === 'pv' ? `<path d="M${mx2 - 4.5} ${my2 - 4}L${mx2} ${my2 + 4}L${mx2 + 4.5} ${my2 - 4}z" style="fill:${col[k]}"/>`
            : `<path d="M${mx2 + (back ? 4 : -4)} ${my2 - 4.5}L${mx2 + (back ? -4 : 4)} ${my2}L${mx2 + (back ? 4 : -4)} ${my2 + 4.5}z" style="fill:${col[k]}"/>`; })() : '';
        return `${glow}<path d="M${x1} ${y1}L${x2} ${y2}" style="stroke:${col[k]}" stroke-width="3.5" stroke-linecap="round"/>${arrow}`;
      };
      const node = (k) => {
        const [x, y] = P[k], ico = mx ? SK_ICO_LINE[k] : SK_ICO[k], c = mx ? 'var(--sk-on)' : col[k];
        if (mx) return `<circle cx="${x}" cy="${y}" r="19" fill="none" style="stroke:${act[k] ? 'var(--sk-on)' : 'var(--sk-off)'}" stroke-width="1.3"/><svg x="${x - 10}" y="${y - 10}" width="20" height="20" viewBox="0 0 24 24" fill="none" style="stroke:${c}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${ico}</svg>`;
        const base = kind === 'tint'
          ? `<circle cx="${x}" cy="${y}" r="25" style="fill:color-mix(in srgb, ${col[k]} 17%, transparent)"/>`
          : `<circle cx="${x}" cy="${y}" r="26" style="fill:var(--sk-idle);stroke:var(--sk-hi)" stroke-width="1"/><circle cx="${x}" cy="${y}" r="26" fill="url(#skhl)"/>`;
        return `${base}<svg x="${x - 11}" y="${y - 11}" width="22" height="22" viewBox="0 0 24 24" style="fill:${c}">${ico}</svg>`;
      };
      const tx = (x, y, v, sub, a) => `<text x="${x}" y="${y}" text-anchor="${a || 'middle'}" font-size="${mx ? 11.5 : 13}" font-weight="${mx ? 700 : 600}" style="fill:var(--text);font-family:inherit">${v}</text><text x="${x}" y="${y + 14}" text-anchor="${a || 'middle'}" font-size="${mx ? 8.5 : 10.5}" style="fill:var(--muted);font-family:inherit"${mx ? ' letter-spacing=".8"' : ''}>${mx ? sub.toUpperCase() : sub}</text>`;
      const gSub = o.grid > TH ? 'import z sieci' : (o.grid < -TH ? 'eksport do sieci' : 'sieć');
      const bSub = o.batt > TH ? 'ładowanie' : (o.batt < -TH ? 'rozładowanie' : 'spoczynek');
      const bV = (o.batt > TH ? '+' : (o.batt < -TH ? '−' : '')) + this._fmtW(Math.abs(o.batt));
      const dt = o.dayTxt || {};
      const dl = (x, y, t, a) => (t ? `<text x="${x}" y="${y}" text-anchor="${a || 'middle'}" font-size="${mx ? 7.5 : 9}" style="fill:var(--muted);font-family:inherit"${mx ? ' letter-spacing=".5"' : ''}>${mx ? bmsEsc(t).toUpperCase() : bmsEsc(t)}</text>` : '');
      const defs = kind === 'sphere' ? '<defs><radialGradient id="skhl" cx=".3" cy=".2" r=".9"><stop offset="0" stop-color="#fff" stop-opacity=".5"/><stop offset=".6" stop-color="#fff" stop-opacity="0"/></radialGradient><filter id="skbl"><feGaussianBlur stdDeviation="3"/></filter></defs>' : '';
      const dot = mx ? `<rect x="${hub[0] - 4.5}" y="${hub[1] - 4.5}" width="9" height="9" rx="1.5" style="fill:var(--sk-acc)"/>` : `<circle cx="${hub[0]}" cy="${hub[1]}" r="5" style="fill:var(--text)"/>`;
      // urządzenia z zakładki „Urządzenia”: rząd satelitów pod węzłem „dom” (nic nie dodano → schemat bez zmian)
      const sat = this._devSat(m.dev, { cx: 170, top: 162, step: 56, r: 15, g1: 18, g2: 10, lh: 14, minX: 40, maxX: 300,
        st: { fill: 'var(--sk-idle)', on: mx ? 'var(--sk-on)' : 'var(--green)', off: mx ? 'var(--sk-off)' : 'var(--sk-hi)', flow: mx ? 'var(--sk-on)' : 'var(--accent)', matrix: mx } });
      return `<svg viewBox="0 0 340 ${Math.max(178, Math.ceil(sat.bottom) + 4)}" role="img" aria-label="Przepływ mocy">${defs}<g fill="none">${ln('pv')}${ln('grid')}${ln('batt')}${ln('home')}</g>${dot}${node('pv')}${node('grid')}${node('batt')}${node('home')}
        ${tx(206, 24, this._fmtW(o.pv), 'produkcja PV', 'start')}${tx(50, 136, this._fmtW(Math.abs(o.grid)), gSub)}${tx(290, 136, bV, bSub)}${tx(200, 128, this._fmtW(o.load), 'dom', 'start')}${dl(206, 52, dt.pv, 'start')}${dl(200, 156, dt.home, 'start')}${dl(48, 168, dt.grid)}${dl(292, 168, dt.batt)}
        <rect class="nf-hit" data-k="pv" x="140" y="0" width="190" height="60"/><rect class="nf-hit" data-k="grid" x="0" y="66" width="100" height="112"/><rect class="nf-hit" data-k="batt" x="240" y="66" width="100" height="112"/><rect class="nf-hit" data-k="home" x="140" y="100" width="190" height="78"/>${sat.svg}</svg>`;
    }
    // pasek planu na 24 h: kolorowe słupki (Szkło, Przestrzeń, Komfort) albo kolumny pikseli wg planowanego SOC z markerami akcji (Matryca)
    _skStrip(m, kind) {
      const plan = m.plan; if (plan.length < 6) return '';
      const ticks = [0, 6, 12, 18].filter(i => i < plan.length).map(i => `<span>${i === 0 ? 'teraz' : String(plan[i].h).padStart(2, '0') + ':00'}</span>`).join('');
      const head = '<div class="sk-ct">Najbliższe 24 h<small>plan</small></div>';
      if (kind === 'matrix') {
        const W = 330, rows = 5, ch = 9, pw = W / plan.length, y0 = rows * ch + 12; let s = '';
        plan.forEach((r, i) => {
          const x = i * pw + pw / 2, lvl = isFinite(Number(r.soc)) ? Math.round(Math.max(0, Math.min(100, Number(r.soc))) / 100 * rows) : 0, z = pw * 0.62;
          for (let k = 0; k < rows; k++) { const lit = k < lvl, zz = lit ? z : z * 0.6; s += `<rect x="${(x - zz / 2).toFixed(1)}" y="${((rows - 1 - k) * ch + ch / 2 - zz / 2).toFixed(1)}" width="${zz.toFixed(1)}" height="${zz.toFixed(1)}" rx="1" style="fill:${lit ? (i === 0 ? 'var(--sk-acc)' : 'var(--sk-on)') : 'var(--sk-off)'}"/>`; }
          const a = r.action, mz = z * 0.9;
          if (a === 'sell') s += `<rect x="${(x - mz / 2).toFixed(1)}" y="${(y0 - mz / 2).toFixed(1)}" width="${mz.toFixed(1)}" height="${mz.toFixed(1)}" rx="1" style="fill:var(--sk-acc)"/>`;
          else if (a === 'grid') s += `<rect x="${(x - mz / 2).toFixed(1)}" y="${(y0 - mz / 2).toFixed(1)}" width="${mz.toFixed(1)}" height="${mz.toFixed(1)}" rx="1" fill="none" style="stroke:var(--sk-on)" stroke-width="1.2"/>`;
          else if (a === 'pv') s += `<rect x="${(x - mz / 2).toFixed(1)}" y="${(y0 - mz / 2).toFixed(1)}" width="${mz.toFixed(1)}" height="${mz.toFixed(1)}" rx="1" style="fill:var(--sk-on)" opacity=".85"/>`;
          else if (a === 'home') s += `<rect x="${(x - mz / 4).toFixed(1)}" y="${(y0 - mz / 4).toFixed(1)}" width="${(mz / 2).toFixed(1)}" height="${(mz / 2).toFixed(1)}" style="fill:var(--muted)"/>`;
          else s += `<rect x="${(x - 1).toFixed(1)}" y="${(y0 - 1).toFixed(1)}" width="2" height="2" style="fill:var(--sk-off)"/>`;
        });
        return `<div class="sk-card sk-strip-card">${head}<svg class="sk-dots" viewBox="0 0 ${W} ${y0 + 8}" style="width:100%;height:auto;margin-top:8px" role="img" aria-label="Plan baterii na 24 godziny">${s}</svg><div class="sk-ax">${ticks}</div>
          <div class="sk-leg"><span><span style="color:var(--sk-acc)">■</span> sprzedaż</span><span>□ z sieci</span><span>■ PV</span><span>▪ dom</span></div></div>`;
      }
      const cmap = { grid: 'var(--sk-grid)', sell: 'var(--sk-sell)', pv: 'var(--sk-pv)', home: 'var(--sk-batt)', idle: 'var(--sk-idle)' };
      return `<div class="sk-card sk-strip-card">${head}<div class="sk-strip">${plan.map((r, i) => `<i class="${i === 0 ? 'now' : ''}" style="background:${cmap[r.action] || cmap.idle}" title="${String(r.h).padStart(2, '0')}:00 — ${bmsEsc(r.label || '')}"></i>`).join('')}</div><div class="sk-ax">${ticks}</div>
        <div class="sk-leg"><span><b style="background:${cmap.grid}"></b>z sieci</span><span><b style="background:${cmap.sell}"></b>sprzedaż</span><span><b style="background:${cmap.pv}"></b>PV</span><span><b style="background:${cmap.home}"></b>bateria / dom</span></div></div>`;
    }
    _drawSkinHome(box, o0, skin) {
      const o = this._skFin(o0), m = this._homeModel(o), mx = skin === 'matrix';
      const chipsH = this._skChips(Object.assign({}, o, { flr: m.flr, tgt: m.tgt }), 'sk');
      const key = JSON.stringify([skin, THEME.mode, m.dev.sig, Math.round(o.pv / 10), Math.round(o.load / 10), Math.round(o.grid / 10), Math.round(o.batt / 10), Math.round(m.soc), m.flr, m.tgt, m.cap,
        isFinite(m.profit) ? m.profit.toFixed(2) : null, m.pb, m.ps, o.D.pv, m.nowH, m.plan.map(r => r.action + ':' + r.soc).join(','), JSON.stringify(o.dayTxt || {}), chipsH.sig]);
      if (key === this._lastM3Key) return;
      this._lastM3Key = key;
      const f1 = (v) => (Math.round(v * 10) / 10).toFixed(1).replace('.', ','), zl = (v) => (isFinite(v) ? v.toFixed(2).replace('.', ',') : '—');
      const cf = skin === 'comfort' || skin === 'hero';
      const ringKind = mx ? 'matrix' : (cf ? 'flat' : 'grad'), flowKind = mx ? 'matrix' : (cf ? 'tint' : 'sphere');
      const g = mx ? ['□', '■'] : (cf ? ['|', '○'] : ['|', '◆']);
      const big = m.cap > 0 ? (mx ? this._skDots(f1(m.cap * m.soc / 100) + ' KWH', 3.4, 'var(--sk-on)').svg : `${f1(m.cap * m.soc / 100)} kWh`) : '';
      const hero = `<div class="sk-card sk-hero">${this._skRing(m, ringKind)}<div class="sk-htx"><div class="sk-lbl">Bateria</div>${big ? `<div class="sk-big">${big}</div>` : ''}
        <div class="sk-sub">${bmsEsc(m.battTxt)}</div>
        <div class="sk-note">${m.hasFl ? `${g[0]} rezerwa ${Math.round(m.flr)}%` : ''}${m.hasFl && m.hasT ? ' &nbsp; ' : ''}${m.hasT ? `${mx ? '<span style="color:var(--sk-acc)">' + g[1] + '</span>' : g[1]} plan na koniec dnia ${Math.round(m.tgt)}%` : ''}</div></div></div>`;
      const flow = `<div class="sk-card sk-flow"><div class="sk-ct">Przepływ mocy<small>teraz</small></div>${this._skFlow(m, flowKind)}</div>`;
      const kpi = (l, v, s, color, dotsTxt, unit) => `<div class="sk-kpi"><div class="l">${l}</div><div class="v"${color ? ` style="color:${color}"` : ''}>${mx && dotsTxt ? this._skDots(dotsTxt, 2.8, color || 'var(--sk-on)').svg : v}</div><div class="s">${mx ? unit : s}</div></div>`;
      const pTxt = isFinite(m.profit) ? (m.profit >= 0 ? '+' : '−') + zl(Math.abs(m.profit)) : '—';
      const kpis = `<div class="sk-kpis">${kpi('Zysk dziś', pTxt + (isFinite(m.profit) ? ' zł' : ''), 'bilans EMS', isFinite(m.profit) && m.profit < 0 ? 'var(--red)' : 'var(--green)', pTxt === '—' ? '-' : pTxt, 'zł · EMS')}
        ${kpi('PV dziś', o.D.pv === null ? '—' : f1(o.D.pv) + ' kWh', o.pv > m.TH ? 'teraz ' + this._fmtW(o.pv) : 'teraz brak', '', o.D.pv === null ? '-' : f1(o.D.pv), 'kWh · PV')}</div>`;
      box.innerHTML = `<div class="sk-home">${hero}${flow}${kpis}${chipsH.html}${this._skStrip(m, mx ? 'matrix' : 'bars')}</div>`;
      this._bindCapInput(box); this._devPopRefresh();
    }

    _drawPowerflow() {
      if (!this.isConnected || !this._tileOn('main-flow')) return;
      const box = this._el('nodesBox');
      if (!box) return;

      let pv = Math.max(0, this._num('pv_power'));
      if (pv < 1) {
        const pv1 = parseFloat(this._st(this._inv('sensor', 'pv1_power'))) || 0;
        const pv2 = parseFloat(this._st(this._inv('sensor', 'pv2_power'))) || 0;
        if (pv1 + pv2 > 1) pv = pv1 + pv2;
      }
      const load = Math.max(0, this._num('load_power'));
      const grid = this._num('grid_power');                 // >0 import, <0 eksport
      const battRaw = this._num('battery_power');
      const batt = INVERT_BATTERY_SIGN ? -battRaw : battRaw; // >0 ładowanie, <0 rozładowanie
      const soc = Math.max(0, Math.min(100, this._num('soc')));
      const D = {
        pv: this._num('energy_pv_today', null), load: this._num('energy_load_today', null),
        imp: this._num('energy_grid_import_today', null), exp: this._num('energy_grid_export_today', null),
        chg: this._num('energy_battery_charge_today', null), dis: this._num('energy_battery_discharge_today', null),
      };
      const k1 = (v) => this._fx(v, 1);
      const dayTxt = {
        pv: D.pv === null ? '' : `dziś ${k1(D.pv)} kWh`,
        home: D.load === null ? '' : `dziś ${k1(D.load)} kWh`,
        grid: (D.imp === null && D.exp === null) ? '' : `dziś ↓${k1(D.imp)} ↑${k1(D.exp)} kWh`,
        batt: (D.chg === null && D.dis === null) ? '' : `dziś ↓${k1(D.chg)} ↑${k1(D.dis)} kWh`,
      };

      if (this.getAttribute('data-skin') === 'm3') { this._drawM3Home(box, { pv, load, grid, batt, soc, D, dayTxt }); return; }
      { const sk = this.getAttribute('data-skin'); if (sk && SKIN_HOME[sk]) { this._drawSkinHome(box, { pv, load, grid, batt, soc, D, dayTxt }, sk); return; } }
      const cw = box.clientWidth || 0;
      const V = this._flowVariant || (cw > 0 && cw < 520 ? 'A' : '0');                    // '0' = bez zmian; A = przycięcie, B = większe, C = oba (telefon)
      const big = V === 'B' || V === 'C', crop = V === 'A' || V === 'C';
      const lh = big ? 20 : 16;
      const DV = this._devNodes();
      const key = [V, Math.round(pv / 10), Math.round(load / 10), Math.round(grid / 10), Math.round(batt / 10), Math.round(soc), THEME.mode, String(this._rsAttrs().inverter_floor), String(this._rsAttrs().capacity_kwh), (() => { try { return localStorage.getItem('bms_panel_capacity') || ''; } catch (e) { return ''; } })(), String((this._pvAttrs().table || []).length), Object.values(D).map(v => v === null ? 'x' : v.toFixed(1)).join(','), DV.sig].join('|');
      if (key === this._lastFlowKey) return;     // animacja jest w CSS — przerysowujemy tylko przy zmianie
      this._lastFlowKey = key;

      const TH = 20;                                         // poniżej 20 W traktujemy jako brak przepływu
      const H = { x: 300, y: (big ? 165 : 150) + 40 };       // środek niżej: linia PV zaczyna się pod napisami, a nie przecina ich
      const dx = V === 'C' ? 28 : 0;
      const N = { pv: { x: 300, y: 45 }, home: { x: 115 + dx, y: H.y }, grid: { x: 485 - dx, y: H.y }, batt: { x: 300, y: (big ? 308 : 268) + 40 } };
      const R = big ? { pv: 38, home: 38, grid: 38, batt: 60 } : { pv: 32, home: 32, grid: 32, batt: 52 };
      // urządzenia z zakładki „Urządzenia” pod węzłem „dom” (nic nie dodano → nic się nie zmienia)
      const sat = this._devSat(DV, { cx: N.home.x, top: N.home.y + R.home + 21 + (dayTxt.home ? 2 : 1) * lh + 17, step: 48, r: 19, g1: 24, g2: 12, lh: 16, minX: 78 + dx, maxX: 222 + dx,
        st: { fill: 'var(--card)', on: '#34c759', off: 'var(--line)', flow: '#0a84ff' } });
      const vb = (crop ? (V === 'C' ? '52 0 496 ' : '45 0 510 ') : '0 0 600 ') + Math.max(big ? 440 : 380, Math.ceil(sat.bottom) + 6);
      const cl = (a, b, r) => {                              // punkt na odcinku a→b przesunięty o r od a
        const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || 1;
        return { x: a.x + dx / d * r, y: a.y + dy / d * r };
      };
      // dir: 1 = węzeł → hub, -1 = hub → węzeł, 0 = brak
      const flows = [
        { k: 'pv',   w: pv,              dir: pv > TH ? 1 : 0,                      c: '#ffb300' },
        { k: 'home', w: load,            dir: load > TH ? -1 : 0,                   c: '#0a84ff' },
        { k: 'grid', w: Math.abs(grid),  dir: grid > TH ? 1 : (grid < -TH ? -1 : 0), c: grid > 0 ? '#ff3b30' : '#34c759' },
        { k: 'batt', w: Math.abs(batt),  dir: batt < -TH ? 1 : (batt > TH ? -1 : 0), c: batt < 0 ? '#ff9500' : '#34c759' },
      ];
      let lines = '';
      flows.forEach(f => {
        const n = N[f.k];
        const a = f.k === 'pv' ? { x: n.x, y: n.y + R.pv + 21 + (dayTxt.pv ? 2 : 1) * lh + 8 } : cl(n, H, R[f.k] + 4), b = cl(H, n, 12);
        const p = f.dir >= 0 ? `M${a.x.toFixed(1)} ${a.y.toFixed(1)} L${b.x.toFixed(1)} ${b.y.toFixed(1)}`
                             : `M${b.x.toFixed(1)} ${b.y.toFixed(1)} L${a.x.toFixed(1)} ${a.y.toFixed(1)}`;
        const sw = f.dir === 0 ? 2 : Math.min(7, 3 + f.w / 1500);
        lines += f.dir === 0
          ? `<path d="${p}" class="nf-idle"/>`
          : `<path d="${p}" class="nf-line" stroke="${f.c}" stroke-width="${sw.toFixed(1)}"/>`;
      });

      // kreska rezerwy (próg odcięcia falownika) i znacznik planowanego SOC na koniec dnia — na pierścieniu baterii
      const pvA = this._pvAttrs();
      const flr = Number(this._rsAttrs().inverter_floor);
      const tRows = Array.isArray(pvA.table) ? pvA.table : [];
      const endRow = tRows.filter(r => r && r.day === this._todayKey() && r.h === 23).pop();
      const tgt = endRow ? Number(endRow.soc) : NaN;
      const ang = (pct) => (pct / 100 * 360 - 90) * Math.PI / 180, rr = R.batt - 6;
      let marks = '';
      if (isFinite(flr) && flr > 0 && flr < 100) {
        const a1 = ang(flr);
        marks += `<line x1="${(N.batt.x + (rr - 7) * Math.cos(a1)).toFixed(1)}" y1="${(N.batt.y + (rr - 7) * Math.sin(a1)).toFixed(1)}" x2="${(N.batt.x + (rr + 7) * Math.cos(a1)).toFixed(1)}" y2="${(N.batt.y + (rr + 7) * Math.sin(a1)).toFixed(1)}" stroke="#ff3b30" stroke-width="3" stroke-linecap="round"><title>Rezerwa (próg odcięcia falownika) ${Math.round(flr)}%</title></line>`;
      }
      if (isFinite(tgt) && tgt > 0 && tgt <= 100) {
        const a2 = ang(tgt), cx = N.batt.x + rr * Math.cos(a2), cy = N.batt.y + rr * Math.sin(a2);
        marks += `<rect x="${(cx - 4.5).toFixed(1)}" y="${(cy - 4.5).toFixed(1)}" width="9" height="9" rx="2" fill="#af52de" stroke="var(--card)" stroke-width="1.5" transform="rotate(45 ${cx.toFixed(1)} ${cy.toFixed(1)})"><title>Plan: ${Math.round(tgt)}% na koniec dnia</title></rect>`;
      }
      const circ = 2 * Math.PI * (R.batt - 6);
      const socCol = soc < 20 ? '#ff3b30' : soc < 40 ? '#ff9500' : '#34c759';
      const node = (k, icon, fill, stroke) => `<circle cx="${N[k].x}" cy="${N[k].y}" r="${R[k]}" fill="${fill}" stroke="${stroke}" stroke-width="2.5"/>
        <text x="${N[k].x}" y="${N[k].y + 8}" text-anchor="middle" font-size="${big ? 30 : 24}">${icon}</text>`;
      const lab = (k, line1, line2, dy) => `<text x="${N[k].x}" y="${N[k].y + dy}" text-anchor="middle" class="nf-v">${line1}</text><text x="${N[k].x}" y="${N[k].y + dy + lh}" text-anchor="middle" class="nf-s">${line2}</text>`;

      const gridTxt = grid > TH ? 'import z sieci' : (grid < -TH ? 'eksport do sieci' : 'sieć');
      const battTxt = batt < -TH ? 'rozładowanie' : (batt > TH ? 'ładowanie' : 'bateria');

      box.innerHTML = `<svg viewBox="${vb}" class="nf-svg${big ? ' nf-big' : ''}" role="img" aria-label="Przepływ mocy">
        ${lines}
        <circle cx="${H.x}" cy="${H.y}" r="9" class="nf-hub"/>
        ${node('pv', '☀️', 'rgba(255,204,0,0.16)', '#ffcc00')}
        ${node('home', '🏠', 'rgba(10,132,255,0.14)', '#0a84ff')}
        ${node('grid', '⚡', 'rgba(52,199,89,0.14)', grid > TH ? '#ff3b30' : '#34c759')}
        <circle cx="${N.batt.x}" cy="${N.batt.y}" r="${R.batt}" class="nf-bg"/>
        <circle cx="${N.batt.x}" cy="${N.batt.y}" r="${R.batt - 6}" fill="none" class="nf-track" stroke-width="8"/>
        <circle cx="${N.batt.x}" cy="${N.batt.y}" r="${R.batt - 6}" fill="none" stroke="${socCol}" stroke-width="8" stroke-linecap="round" stroke-dasharray="${(circ * soc / 100).toFixed(1)} ${circ.toFixed(1)}" transform="rotate(-90 ${N.batt.x} ${N.batt.y})"/>
        ${marks}
        <text x="${N.batt.x}" y="${N.batt.y + (big ? 9 : 7)}" text-anchor="middle" class="nf-soc">${Math.round(soc)}%</text>
        ${lab('pv', this._fmtW(pv), 'produkcja PV', R.pv + 20)}
        ${lab('home', this._fmtW(load), 'dom', R.home + 20)}
        ${lab('grid', this._fmtW(grid), gridTxt, R.grid + 20)}
        ${dayTxt.pv ? `<text x="${N.pv.x}" y="${N.pv.y + R.pv + 21 + 2 * lh}" text-anchor="middle" class="nf-d">${dayTxt.pv}</text>` : ''}
        ${dayTxt.home ? `<text x="${N.home.x}" y="${N.home.y + R.home + 21 + 2 * lh}" text-anchor="middle" class="nf-d">${dayTxt.home}</text>` : ''}
        ${dayTxt.grid ? `<text x="${N.grid.x}" y="${N.grid.y + R.grid + 21 + 2 * lh}" text-anchor="middle" class="nf-d">${dayTxt.grid}</text>` : ''}
        <text x="${N.batt.x + R.batt + 26}" y="${N.batt.y - 4}" class="nf-v" fill="${batt < -TH ? '#ff9500' : (batt > TH ? '#34c759' : 'currentColor')}">${(batt < -TH ? '−' : (batt > TH ? '+' : '')) + this._fmtW(batt)}</text>
        <text x="${N.batt.x + R.batt + 26}" y="${N.batt.y + 2 + lh}" class="nf-s">${battTxt}</text>
        ${dayTxt.batt ? `<text x="${N.batt.x + R.batt + 26}" y="${N.batt.y + 3 + 2 * lh}" class="nf-d">${dayTxt.batt}</text>` : ''}
        ${sat.svg}
        <rect class="nf-hit" data-k="pv" x="${N.pv.x - 60}" y="${N.pv.y - R.pv - 2}" width="120" height="${R.pv * 2 + 4 + 40}"/>
        <rect class="nf-hit" data-k="home" x="${N.home.x - 60}" y="${N.home.y - R.home - 2}" width="120" height="${R.home * 2 + 4 + 40}"/>
        <rect class="nf-hit" data-k="grid" x="${N.grid.x - 60}" y="${N.grid.y - R.grid - 2}" width="120" height="${R.grid * 2 + 4 + 40}"/>
        <rect class="nf-hit" data-k="batt" x="${N.batt.x - R.batt - 2}" y="${N.batt.y - R.batt - 2}" width="${R.batt * 2 + 4 + 150}" height="${R.batt * 2 + 4}"/>
      </svg>` + this._flowChips({ soc, batt, load, pv, grid, flr, tgt });
      this._bindCapInput(box); this._devPopRefresh();
    }

    // Wspólne dane paska wskaźników pod schematem (styl klasyczny i wszystkie style): zgromadzone / do rezerwy / przy tym tempie /
    // straty falownika / zysk dziś. Style różnią się tylko rysowaniem — zestaw informacji jest ten sam.
    // opt.hero: styl pokazuje zgromadzoną energię w karcie baterii u góry; opt.profit: dołóż „Zysk dziś” (style mają go w kafelku)
    _homeChips(o, opt) {
      opt = opt || {};
      const ra = this._rsAttrs();
      let cap = parseFloat(ra.capacity_kwh);
      if (!(cap > 0)) { try { cap = parseFloat(localStorage.getItem('bms_panel_capacity')); } catch (e) { cap = NaN; } }
      const hasFl = isFinite(o.flr) && o.flr > 0 && o.flr < 100;
      const FL = hasFl ? o.flr : 20;
      const items = [];
      if (cap > 0) {
        const kwh = cap * o.soc / 100, usable = Math.max(0, cap * (o.soc - FL) / 100);
        let pace = '—', paceTip = '';
        if (o.soc <= FL) pace = 'osiągnięte';
        else if (o.batt < -20) { const h = usable / (-o.batt / 1000); pace = `do ${Math.round(FL)}% ok. ${this._fmtAt(h)}`; paceTip = `przy obecnym rozładowaniu ${this._fmtW(-o.batt)}`; }
        else if (o.batt > 20 && o.soc < 99.5) { const h = (100 - o.soc) / 100 * cap / (o.batt / 1000); pace = `pełna ok. ${this._fmtAt(h)}`; paceTip = `przy obecnym ładowaniu ${this._fmtW(o.batt)}`; }
        else { const h = usable / (Math.max(o.load, 100) / 1000); pace = `do ${Math.round(FL)}% ok. ${this._fmtAt(h)}`; paceTip = `przy obecnym zużyciu domu ${this._fmtW(Math.max(o.load, 100))} (bez PV)`; }
        if (!opt.hero) items.push({ id: 'stored', l: 'Zgromadzone', v: `~ ${this._fx(kwh)} kWh` });
        items.push({ id: 'usable', l: `Do rezerwy ${Math.round(FL)}%`, v: `${this._fx(usable)} kWh` }, { id: 'pace', l: 'Przy tym tempie', v: pace, t: paceTip });
      }
      // straty z bilansu mocy (PV + sieć − dom − bateria); to szacunek, a nie pomiar falownika
      const loss = o.pv + o.grid - o.load - o.batt;
      if (isFinite(loss) && (o.pv > 50 || Math.abs(o.batt) > 50)) items.push({ id: 'loss', l: 'Straty falownika (szac.)', v: `${Math.max(0, Math.round(loss))} W`, t: 'Szacunek z bilansu mocy: PV + sieć − dom − bateria' });
      if (opt.profit) { const p = this._profitToday(); if (isFinite(p)) items.push({ id: 'profit', l: 'Zysk dziś', v: (p < 0 ? '−' : '+') + this._fx(Math.abs(p), 2) + ' zł', t: 'Bilans EMS z dzisiaj' }); }
      return { items, capMissing: !(cap > 0), hasFl, FL };
    }
    _capPromptHtml(cls) {
      return `<div class="${cls || ''} nf-cap" style="grid-column:1/-1;">Integracja nie podała pojemności baterii — wpisz ją, a pokażę zgromadzoną energię i czas do rezerwy: <input type="number" id="capInput" min="1" max="200" step="0.1" placeholder="kWh"> kWh</div>`;
    }
    _bindCapInput(box) {
      const ci = box.querySelector('#capInput');
      if (ci) ci.addEventListener('change', () => {
        const v = parseFloat(String(ci.value).replace(',', '.'));
        try { if (v > 0) localStorage.setItem('bms_panel_capacity', String(v)); else localStorage.removeItem('bms_panel_capacity'); } catch (e) { /* ignoruj */ }
        this._lastFlowKey = null; this._lastM3Key = null;
        this._drawPowerflow();
      });
    }
    // styl klasyczny: legenda znaczników pierścienia + kafelki wskaźników
    _flowChips(o) {
      const H = this._homeChips(o, { profit: true });
      const chip = (it) => `<div class="nf-chip"${it.t ? ` title="${bmsEsc(it.t)}"` : ''}><small>${bmsEsc(it.l)}</small><b>${bmsEsc(it.v)}</b></div>`;
      const c = (H.capMissing ? this._capPromptHtml('') : '') + H.items.map(chip).join('');
      const leg = H.hasFl || isFinite(o.tgt)
        ? `<div class="nf-leg">${H.hasFl ? `<span><i class="nf-k"></i>rezerwa ${Math.round(H.FL)}%</span>` : ''}${isFinite(o.tgt) ? `<span><i class="nf-t"></i>plan na koniec dnia ${Math.round(o.tgt)}%</span>` : ''}</div>` : '';
      return leg + (c ? `<div class="nf-chips">${c}</div>` : '');
    }
    // style (Material 3, Szkło, Matryca, Przestrzeń, Komfort): te same wskaźniki jako kafelki w kolorach stylu; pre = 'm3' | 'sk'
    _skChips(o, pre) {
      const H = this._homeChips(o, { hero: true });
      const tile = (it) => `<div class="${pre}-kpi ${pre}-chip"${it.t ? ` title="${bmsEsc(it.t)}"` : ''}><div class="l">${bmsEsc(it.l)}</div><div class="v">${bmsEsc(it.v)}</div></div>`;
      const cap = H.capMissing ? this._capPromptHtml(pre === 'm3' ? 'm3-kpi m3-cap' : 'sk-card sk-cap') : '';
      const chips = H.items.length ? `<div class="${pre}-kpis ${pre}-chips"">${H.items.map(tile).join('')}</div>` : '';
      return { html: (cap || chips) ? (pre === 'm3' ? cap + chips : `<div class="sk-extra">${cap}${chips}</div>`) : '', sig: JSON.stringify([H.capMissing, H.items.map((x) => x.v)]) };
    }

    // ===== MINI WYKRES 24 h (popover przy węzłach) =====
    _bindNodePop(wrap) {
      const box = wrap.querySelector('#nodesBox');
      const pop = wrap.querySelector('#nodePop');
      if (!box || !pop || box.dataset.npBound) return;
      box.dataset.npBound = '1';
      this._nodeHist = this._nodeHist || {};
      this._popK = null; this._popPinned = false;
      const hitOf = e => e.target && e.target.closest ? e.target.closest('.nf-hit') : null;
      box.addEventListener('mouseover', e => {
        const h = hitOf(e);
        if (h && !this._popPinned) this._showPop(h.dataset.k, h);
      });
      box.addEventListener('mouseleave', () => { if (!this._popPinned) this._hidePop(); });
      box.addEventListener('click', e => {
        const h = hitOf(e);
        if (!h) { this._hidePop(); return; }
        const k = h.dataset.k;
        if (this._popPinned && this._popK === k) { this._hidePop(); return; }
        this._popPinned = true;
        this._showPop(k, h);
        pop.classList.add('pin');
      });
      pop.addEventListener('click', e => {
        if (e.target.closest('.np-x')) { this._hidePop(); return; }
        if (e.target.closest('.np-go')) { this._hidePop(); const t = this.shadowRoot.querySelector('.tab[data-tab="dev"]'); if (t) t.click(); }
      });
      this.shadowRoot.addEventListener('click', e => {
        if (!this._popPinned) return;
        if (e.target.closest && (e.target.closest('.nf-hit') || e.target.closest('.node-pop'))) return;
        this._hidePop();
      });
      window.addEventListener('keydown', e => { if (e.key === 'Escape') this._hidePop(); });
    }

    _hidePop() {
      const pop = this._el('nodePop');
      this._popK = null; this._popPinned = false;
      if (pop) {
        pop.hidden = true; pop.classList.remove('pin'); delete pop.dataset.h;
        const wrap = pop.parentElement;
        if (wrap && wrap.dataset && wrap.dataset.h0) { wrap.style.height = ''; delete wrap.dataset.h0; }   // karta wraca do swojej wysokości
      }
    }

    _showPop(k, hitEl) {
      const pop = this._el('nodePop');
      if (!pop) return;
      const changed = this._popK !== k;
      this._popK = k;
      pop.hidden = false;
      if (String(k).slice(0, 4) === 'dev:') {                  // urządzenie: dane z czujnika, bez historii
        const h = this._devPopHtml(k);
        if (!h) { this._hidePop(); return; }
        if (changed || pop.dataset.h !== h) { pop.dataset.h = h; pop.innerHTML = h; }
        this._placePop();
        return;
      }
      delete pop.dataset.h;
      this._placePop();
      if (!changed) return;
      const c = this._nodeHist && this._nodeHist[k];
      if (c && Date.now() - c.t < 5 * 60000 && c.data) { this._renderPop(k); return; }
      pop.innerHTML = `<div class="np-msg">Ładowanie historii…</div>`;
      this._fetchNodeHist(k).then(() => { if (this._popK === k) this._renderPop(k); });
    }

    // pozycja popovera: pod węzłem, a gdy się nie mieści — nad nim; zawsze w granicach karty
    _placePop() {
      const pop = this._el('nodePop');
      if (!pop || pop.hidden || !this._popK) return;
      const hit = [...this.shadowRoot.querySelectorAll('.nf-hit')].find(h => h.dataset.k === this._popK);   // identyfikator urządzenia bywa dowolny — bez selektora CSS
      if (!hit) return;
      const wrap = pop.parentElement;
      const card = wrap.getBoundingClientRect();
      const r = hit.getBoundingClientRect();
      const pw = pop.offsetWidth || 320, ph = pop.offsetHeight || 200;
      // na wąskim ekranie karta schematu może urosnąć, żeby okno z danymi mieściło się w całości
      const narrow = card.width <= 600;
      const baseH = narrow ? (parseFloat(wrap.dataset.h0) || card.height) : card.height;
      if (narrow && !wrap.dataset.h0) wrap.dataset.h0 = String(card.height);
      let left = (r.left + r.width / 2) - card.left - pw / 2;
      left = Math.max(8, Math.min(card.width - pw - 8, left));
      const below = r.bottom - card.top + 6;
      const above = r.top - card.top - ph - 6;
      let top;
      if (this._popK === 'batt') top = above >= 4 ? above : below;
      else top = (below + ph <= baseH - 4) ? below : (above >= 4 ? above : (narrow ? below : baseH - ph - 4));
      if (narrow) {
        top = Math.max(4, top);
        const need = Math.ceil(top + ph + 10);
        wrap.style.height = need > baseH ? need + 'px' : '';
      } else {
        top = Math.max(4, Math.min(top, baseH - ph - 4));
      }
      pop.style.left = left + 'px';
      pop.style.bottom = 'auto';
      pop.style.top = top + 'px';
    }

    _detHtml(k) {
      const rows = (this._nodeDetails()[k] || []);
      if (!rows.length) return '';
      return `<div class="np-det">${rows.map(([l, v]) => `<span>${l}</span><b>${v}</b>`).join('')}</div>`;
    }

    _nodeCfg(k) {
      const mk = key => { const f = this._findEntity(ENTITY_FALLBACKS[key]); return f ? f.eid : null; };
      return {
        pv:   { title: 'Produkcja PV', eid: mk('pv_power'),      sign: 1,  pos: '#ffb300', neg: '#ffb300', pl: 'produkcja', nl: '' },
        home: { title: 'Pobór domu',   eid: mk('load_power'),    sign: 1,  pos: '#0a84ff', neg: '#0a84ff', pl: 'pobór', nl: '' },
        grid: { title: 'Sieć',         eid: mk('grid_power'),    sign: 1,  pos: '#ff3b30', neg: '#34c759', pl: 'import', nl: 'eksport' },
        batt: { title: 'Bateria',      eid: mk('battery_power'), sign: INVERT_BATTERY_SIGN ? -1 : 1, pos: '#34c759', neg: '#ff9500', pl: 'ładowanie', nl: 'rozładowanie', socEid: mk('soc') },
      }[k];
    }

    async _fetchNodeHist(k) {
      this._nodeHist = this._nodeHist || {};
      const cfg = this._nodeCfg(k);
      const slot = this._nodeHist[k] = { t: Date.now(), data: null };
      if (!cfg || !cfg.eid) return;
      const now = new Date();
      const start = new Date(now.getTime() - 24 * 3600000);
      const ids = [cfg.eid].concat(cfg.socEid ? [cfg.socEid] : []);
      try {
        const res = await this._hass.callWS({
          type: 'history/history_during_period',
          start_time: start.toISOString(), end_time: now.toISOString(),
          entity_ids: ids, minimal_response: true, no_attributes: true,
          significant_changes_only: false, include_start_time_state: true,
        });
        const N = 96, step = 15 * 60000, t0 = start.getTime();
        const series = (eid, mul) => {
          const raw = (res && res[eid]) || [];
          const pts = raw.map(it => {
            let ts = typeof it.lc === 'number' ? it.lc * 1000 : typeof it.lu === 'number' ? it.lu * 1000 : new Date(it.last_changed || it.last_updated).getTime();
            const v = parseFloat(it.s !== undefined ? it.s : it.state);
            return isNaN(ts) || isNaN(v) ? null : { ts, v: v * mul };
          }).filter(Boolean).sort((a, b) => a.ts - b.ts);
          if (!pts.length) return null;
          const out = new Array(N).fill(null);
          let i = 0, last = null;
          for (let b = 0; b < N; b++) {
            const lo = t0 + b * step, hi = lo + step;
            let sum = 0, n = 0;
            while (i < pts.length && pts[i].ts < hi) { if (pts[i].ts >= lo) { sum += pts[i].v; n++; } last = pts[i].v; i++; }
            out[b] = n ? sum / n : last;        // brak próbek w przedziale → ostatnia znana wartość
          }
          return out;
        };
        const unit = e => { const s = this._hass.states[e]; return s && s.attributes && s.attributes.unit_of_measurement === 'kW' ? 1000 : 1; };
        const p = series(cfg.eid, cfg.sign * unit(cfg.eid));
        if (p) slot.data = { p, soc: cfg.socEid ? series(cfg.socEid, 1) : null, t0, step };
      } catch (e) { console.warn('EMS node history error:', e); }
    }

    _renderPop(k) {
      const pop = this._el('nodePop');
      const cfg = this._nodeCfg(k);
      const slot = this._nodeHist && this._nodeHist[k];
      if (!pop || !cfg) return;
      const head = (val) => `<div class="np-head"><span>${cfg.title} · ostatnie 24 h</span><span><b>${val}</b><button class="np-x" type="button" aria-label="Zamknij">×</button></span></div>`;
      if (!slot || !slot.data) {
        pop.innerHTML = head('') + `<div class="np-msg">${cfg.eid ? 'Brak historii (czy encja jest w recorderze?)' : 'Nie znaleziono encji mocy'}</div>` + this._detHtml(k);
        this._placePop();
        return;
      }
      const { p, soc, t0, step } = slot.data;
      const vals = p.map(v => v === null ? 0 : v);
      const W = 300, H = 110, L = 4, R = 4, T = 6, B = 16, iw = W - L - R, ih = H - T - B;
      let mx = Math.max(0, ...vals), mn = Math.min(0, ...vals);
      if (mx - mn < 50) mx = mn + 50;
      const X = i => L + iw * i / (vals.length - 1);
      const Y = v => T + ih * (mx - v) / (mx - mn);
      const y0 = Y(0);
      const area = fn => `M${X(0).toFixed(1)} ${y0.toFixed(1)} ` + vals.map((v, i) => `L${X(i).toFixed(1)} ${Y(fn(v)).toFixed(1)}`).join(' ') + ` L${X(vals.length - 1).toFixed(1)} ${y0.toFixed(1)} Z`;
      const line = vals.map((v, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)} ${Y(v).toFixed(1)}`).join(' ');
      let socPath = '';
      if (soc) socPath = `<path d="${soc.map((v, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)} ${(T + ih * (1 - (v === null ? 0 : v) / 100)).toFixed(1)}`).join(' ')}" fill="none" stroke="var(--muted)" stroke-width="1.2" stroke-dasharray="3 3"/>`;
      const hrs = 0.25;
      const pos = vals.reduce((a, v) => a + (v > 0 ? v : 0), 0) * hrs / 1000;
      const neg = -vals.reduce((a, v) => a + (v < 0 ? v : 0), 0) * hrs / 1000;
      const fk = x => x.toFixed(1).replace('.', ',') + ' kWh';
      const peak = Math.max(...vals), low = Math.min(...vals);
      const stats = cfg.nl
        ? `<span>${cfg.pl}: <b>${fk(pos)}</b></span><span>${cfg.nl}: <b>${fk(neg)}</b></span><span>szczyt: <b>${this._fmtW(Math.abs(Math.abs(peak) >= Math.abs(low) ? peak : low))}</b></span>`
        : `<span>energia: <b>${fk(pos)}</b></span><span>szczyt: <b>${this._fmtW(peak)}</b></span><span>średnio: <b>${this._fmtW(vals.reduce((a, v) => a + v, 0) / vals.length)}</b></span>`;
      const t0d = new Date(t0);
      const ticks = [0, 24, 48, 72, 95].map(i => {
        const d = new Date(t0 + i * step);
        return `<text class="np-tick" x="${X(i).toFixed(1)}" y="${H - 3}" text-anchor="${i === 0 ? 'start' : i === 95 ? 'end' : 'middle'}">${i === 95 ? 'teraz' : String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0')}</text>`;
      }).join('');
      const last = vals[vals.length - 1];
      pop.innerHTML = head(this._fmtW(last)) + `
        <svg class="np-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Moc z ostatnich 24 godzin">
          <path class="np-area-p" d="${area(v => Math.max(0, v))}" fill="${cfg.pos}" fill-opacity="0.35"/>
          ${cfg.nl ? `<path class="np-area-n" d="${area(v => Math.min(0, v))}" fill="${cfg.neg}" fill-opacity="0.35"/>` : ''}
          <line class="np-zero" x1="${L}" x2="${W - R}" y1="${y0.toFixed(1)}" y2="${y0.toFixed(1)}"/>
          ${socPath}
          <path d="${line}" fill="none" stroke="${cfg.pos}" stroke-width="1.6" stroke-linejoin="round"/>
          <line class="np-cur" id="npCur" x1="0" x2="0" y1="${T}" y2="${T + ih}" style="display:none"/>
          ${ticks}
          <rect id="npTouch" x="0" y="0" width="${W}" height="${H}" fill="transparent"/>
        </svg>
        <div class="np-stats">${stats}${soc ? '<span>┄ SOC</span>' : ''}</div>${this._detHtml(k)}`;
      // czytnik wartości po przesunięciu kursora/palca (tryb przypięty)
      const svg = pop.querySelector('.np-svg'), cur = pop.querySelector('#npCur'), hv = pop.querySelector('.np-head b');
      const move = e => {
        if (!this._popPinned) return;
        const rc = svg.getBoundingClientRect();
        const i = Math.max(0, Math.min(vals.length - 1, Math.round(((e.clientX - rc.left) / rc.width * W - L) / iw * (vals.length - 1))));
        cur.style.display = ''; cur.setAttribute('x1', X(i)); cur.setAttribute('x2', X(i));
        const d = new Date(t0 + i * step);
        hv.textContent = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')} · ${this._fmtW(vals[i])}`;
      };
      svg.addEventListener('pointermove', move);
      svg.addEventListener('pointerdown', move);
      this._placePop();
    }

    _fmtDur(h) {
      if (!isFinite(h) || h < 0) return '—';
      if (h > 48) return '> 2 dni';
      const m = Math.round(h * 60);
      const dd = Math.floor(m / 1440), hh = Math.floor((m % 1440) / 60), mm = m % 60;
      if (dd > 0) return `${dd} d ${hh} h`;                              // od doby wzwyż: „1 d 7 h” zamiast „31 h 57 min”
      return hh > 0 ? `${hh} h ${String(mm).padStart(2, '0')} min` : `${mm} min`;
    }
    _fmtAt(h) {
      const d = new Date(Date.now() + h * 3600000);
      const day = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
      const diff = Math.round((day(d) - day(new Date())) / 86400000);   // różnica w dniach kalendarzowych, nie w dobach
      const prefix = diff <= 0 ? '' : diff === 1 ? 'jutro ' : diff === 2 ? 'pojutrze ' : d.toLocaleDateString('pl-PL', { weekday: 'short' }) + ' ';
      return prefix + d.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' });
    }

    // Prognoza PV z integracji (Solcast albo Forecast.Solar — ta sama, której używa planer); null = starsza integracja
    _pvInt() {
      const rs = this._hass && this._hass.states[this._eid('sensor', 'reserve_soc')];
      const a = rs && rs.attributes;
      return a && Array.isArray(a.pv_daily) ? a : null;
    }

    // suma prognozy PV na dzień (offset 0 = dziś) w kWh; null = brak prognozy
    _pvDayKwh(offset) {
      const a = this._pvInt();
      if (a) {
        const d = a.pv_daily[offset];
        return d && typeof d.kwh === 'number' && isFinite(d.kwh) ? d.kwh : null;
      }
      for (const eid of (PV_FORECAST_DAYS[offset] || [])) {
        const st = this._hass.states[eid];
        if (st && st.state !== 'unknown' && st.state !== 'unavailable') {
          const v = parseFloat(st.state);
          if (!isNaN(v)) return v;
        }
      }
      return null;
    }

    // wiersz prognozy dnia z integracji (kwh po korekcie, raw, factor, lo, hi); null = starsza integracja
    _pvDayInfo(offset) {
      const a = this._pvInt();
      const d = a && a.pv_daily[offset];
      return d && typeof d === 'object' ? d : null;
    }

    _pvRange(offset) {
      const d = this._pvDayInfo(offset);
      if (d && d.est === true) return '<div class="pv-rng" data-role="pv-est">szac.</div>';      // brak prognozy: średnia z ostatnich dni
      if (!d || typeof d.lo !== 'number' || typeof d.hi !== 'number') return '';
      const f = (x) => x.toFixed(1).replace('.', ',');
      return `<div class="pv-rng">${f(d.lo)}–${f(d.hi)}</div>`;
    }

    _pvTip(offset) {
      const d = this._pvDayInfo(offset);
      if (d && d.est === true) {
        const a = this._pvInt(), fb = a && a.pv_fallback;
        return ` title="Brak prognozy PV — szacunek: typowy dzień z ostatnich ${fb && typeof fb.days === 'number' ? fb.days : ''} dni, pomnożony przez ostrożność ${fb && typeof fb.caution === 'number' ? String(fb.caution).replace('.', ',') : ''}. To nie jest prognoza pogody."`;
      }
      if (!d || typeof d.raw !== 'number' || typeof d.factor !== 'number') return '';
      const f = (x, n) => x.toFixed(n).replace('.', ',');
      const src = d.range === 'solcast' ? 'zakres z Solcast' : d.range === 'historia' ? 'zakres z historii błędów' : 'zakres szacunkowy (za mało historii)';
      const t = `surowa prognoza ${f(d.raw, 1)} kWh · korekta ×${f(d.factor, 2)} z ${d.n || 0} dni · ${src}`;
      return ` title="${t}"`;
    }

    _pvSourceLabel() {
      const a = this._pvInt();
      return a && a.pv_forecast_source ? String(a.pv_forecast_source) : '';
    }

    // godzinowa prognoza PV (kW ≈ kWh/h): mapa 'YYYY-MM-DD|hh' -> kW
    _pvHourlyMap() {
      const map = {};
      const a = this._pvInt();
      if (a) {
        [['pv_hourly_today', 0], ['pv_hourly_tomorrow', 1]].forEach(([k, off]) => {
          const arr = Array.isArray(a[k + '_adj']) ? a[k + '_adj'] : a[k], day = a.pv_daily[off];
          if (!Array.isArray(arr) || !day || !day.date) return;
          arr.forEach((v, h) => { if (typeof v === 'number' && isFinite(v)) map[`${day.date}|${h}`] = v; });
        });
        return map;
      }
      for (let off = 0; off < 2; off++) {
        for (const eid of PV_FORECAST_DAYS[off]) {
          const st = this._hass.states[eid];
          if (!st || !st.attributes) continue;
          const arr = st.attributes.detailedHourly || st.attributes.detailedForecast;
          if (!Array.isArray(arr)) continue;
          const acc = {};
          arr.forEach(it => {
            const t = new Date(it.period_start || it.datetime);
            const v = parseFloat(it.pv_estimate ?? it.estimate);
            if (isNaN(t.getTime()) || isNaN(v)) return;
            const k = `${this._dateKey(t)}|${t.getHours()}`;
            (acc[k] = acc[k] || []).push(v);
          });
          Object.keys(acc).forEach(k => { map[k] = acc[k].reduce((a, b) => a + b, 0) / acc[k].length; });
          break;
        }
      }
      return map;
    }

    // symulacja godzina po godzinie: czas (h) do osiągnięcia celu (100% lub 20%) albo null
    _simulateSoc(soc0, cap, target, up, hourlyLoad, pvMap) {
      let soc = soc0;
      const start = new Date();
      let t = start.getTime();
      for (let step = 0; step < 60; step++) {
        const d = new Date(t);
        const frac = step === 0 ? (60 - d.getMinutes()) / 60 : 1;      // reszta bieżącej godziny
        const pv = pvMap[`${this._dateKey(d)}|${d.getHours()}`] || 0;
        const load = hourlyLoad ? (hourlyLoad[d.getHours()] ?? 0.5) : 0.5;
        const dSoc = (pv - load) * frac / cap * 100;
        const next = soc + dSoc;
        const thr = typeof target === 'function' ? target(d.getHours()) : target;   // próg odcięcia zmienia się z programami ToU
        if ((up && next >= thr) || (!up && next <= thr)) {
          const part = dSoc !== 0 ? Math.max(0, Math.min(1, (thr - soc) / dSoc)) : 0;
          return ((t - start.getTime()) / 3600000) + part * frac;
        }
        soc = Math.max(0, Math.min(100, next));
        t += frac * 3600000;
      }
      return null;
    }

    // SOC w chwili, gdy PV zacznie pokrywać zużycie domu (tylko w nocy / bez produkcji). null = nie dotyczy.
    _socAtSun(soc0, cap, hourlyLoad, pvMap, floorFn) {
      const pvNow = this._num('pv_power');
      const sunSt = this._hass.states['sun.sun'];
      const night = (sunSt && sunSt.state === 'below_horizon') || !(pvNow > 50);
      if (!night || !(cap > 0)) return null;
      const start = new Date();
      let t = start.getTime(), soc = soc0, floorAt = null, at = null, flo = null;
      const rising = sunSt && sunSt.attributes && sunSt.attributes.next_rising ? new Date(sunSt.attributes.next_rising) : null;
      const havePv = Object.keys(pvMap || {}).length > 0;
      for (let step = 0; step < 30; step++) {
        const d = new Date(t);
        const pv = pvMap[`${this._dateKey(d)}|${d.getHours()}`] || 0;
        const load = hourlyLoad ? (hourlyLoad[d.getHours()] ?? 0.5) : 0.5;
        const covered = havePv ? (pv >= load && pv > 0.05) : (rising && d >= rising);
        if (covered) { at = d; break; }
        const frac = step === 0 ? (60 - d.getMinutes()) / 60 : 1;
        const thr = typeof floorFn === 'function' ? floorFn(d.getHours()) : floorFn;
        const next = soc + (pv - load) * frac / cap * 100;
        if (floorAt === null && next <= thr && soc > thr) {
          const part = soc !== next ? (soc - thr) / (soc - next) : 0;
          floorAt = new Date(t + part * frac * 3600000); flo = thr;
        }
        soc = Math.max(thr, Math.min(100, next));
        t = (step === 0 ? new Date(d.getFullYear(), d.getMonth(), d.getDate(), d.getHours() + 1).getTime() : t + 3600000);
      }
      if (!at || (at.getTime() - start.getTime()) < 15 * 60000) return null;
      return { at, soc, floorAt, floor: flo };
    }

    // zaplanowane ładowanie z sieci z planu 24 h (sensor plan_curve): trwa teraz albo najbliższy start.
    // null = brak sensora planu / błąd planu, {none:true} = plan jest, ale ładowania z sieci w nim nie ma
    _plannedGridCharge() {
      const s = this._hass.states[this._eid('sensor', 'plan_curve')];
      const a = s && s.attributes;
      if (!a || a.error || !a.proposals) return null;
      const hm = (t) => { const m = /^(\d\d):(\d\d)$/.exec(String(t || '')); return m ? +m[1] * 60 + +m[2] : null; };
      const d0 = new Date(); d0.setHours(0, 0, 0, 0);
      const nowMin = (Date.now() - d0.getTime()) / 60000;
      let best = null;
      [['start_grid_charge', 'stop_grid_charge'], ['start_grid_charge_2', 'stop_grid_charge_2']].forEach(([k1, k2]) => {
        const ps = a.proposals[k1], pe = a.proposals[k2];
        if (!ps || !pe || ps.skip || pe.skip) return;
        const sM = hm(ps.proposed), eM = hm(pe.proposed);
        if (sM === null || eM === null || sM === eM) return;
        const active = sM < eM ? (nowMin >= sM && nowMin < eM) : (nowMin >= sM || nowMin < eM);
        const c = { active, startTxt: ps.proposed, endTxt: pe.proposed, hStart: active ? 0 : ((sM - nowMin + 1440) % 1440) / 60 };
        if (!best || (c.active && !best.active) || (c.active === best.active && c.hStart < best.hStart)) best = c;
      });
      return best || { none: true };
    }

    _renderPlan() {
      const box = this._el('planBox');
      if (!box) return;
      const pvDone = this._num('energy_pv_today');
      const loadDone = this._num('energy_load_today');
      const ch = this._num('energy_battery_charge_today');
      const dis = this._num('energy_battery_discharge_today');
      const imp = this._num('energy_grid_import_today');
      const exp = this._num('energy_grid_export_today');

      const pvFc = this._pvDayKwh(0);
      const pvSrc = this._pvSourceLabel();
      let loadFc = null;
      const lf = this._hass.states['sensor.bms_load_forecast'] || this._hass.states[this._eid('sensor', 'load_forecast')];
      if (lf && lf.attributes && Array.isArray(lf.attributes.days)) {
        const today = lf.attributes.days.find(d => d && d.label === 'Dziś');
        if (today && typeof today.forecast === 'number') loadFc = today.forecast;
      }
      const row = (icon, label, val, max, unit, col, note) => {
        const pct = max > 0 ? Math.max(0, Math.min(100, val / max * 100)) : 0;
        return `<div class="pl-row"><div class="pl-h"><span>${icon} ${label}</span><b>${this._fx(val, 1)}${max > 0 ? ' / ' + this._fx(max, 1) : ''} ${unit}</b></div>
          <div class="pl-bar"><div style="width:${pct.toFixed(0)}%;background:${col};"></div></div>${note ? `<div class="pl-n">${note}</div>` : ''}</div>`;
      };
      const rs = this._hass.states[this._eid('sensor', 'reserve_soc')];
      const capK = rs && rs.attributes ? parseFloat(rs.attributes.capacity_kwh) || 0 : 0;
      const selfSuff = loadDone > 0.1 ? Math.max(0, Math.min(100, (1 - imp / loadDone) * 100)) : null;
      box.innerHTML =
        row('☀️', 'Produkcja PV — prognoza' + (pvSrc ? ` (${this._esc(pvSrc)})` : ''), pvDone, pvFc || 0, 'kWh', '#ffcc00', pvFc ? '' : 'brak prognozy PV') +
        row('🏠', 'Zużycie domu — prognoza EMS', loadDone, loadFc || 0, 'kWh', '#0a84ff', loadFc ? '' : 'brak prognozy zużycia') +
        (() => {
          let pvW = Math.max(0, this._num('pv_power'));
          if (pvW < 1) {
            const p1 = parseFloat(this._st(this._inv('sensor', 'pv1_power'))) || 0;
            const p2 = parseFloat(this._st(this._inv('sensor', 'pv2_power'))) || 0;
            if (p1 + p2 > 1) pvW = p1 + p2;
          }
          const pvKw = pvW / 1000;
          const map = this._pvHourlyMap();
          const vals = Object.values(map);
          const peak = vals.length ? Math.max(...vals) : 0;
          const hKey = `${this._todayKey()}|${new Date().getHours()}`;
          const fcNow = (map[hKey] != null) ? map[hKey] : null;
          const scale = Math.max(1, Math.ceil(Math.max(peak, pvKw) * 1.1));
          const pct = Math.max(0, Math.min(100, pvKw / scale * 100));
          const mark = fcNow != null ? Math.max(0, Math.min(100, fcNow / scale * 100)) : null;
          let rel = '';
          if (fcNow != null && fcNow >= 0.3) {
            const r = Math.round(pvKw / fcNow * 100);
            const colr = r >= 90 ? '#34c759' : (r >= 60 ? '#ff9f0a' : '#ff453a');
            rel = `<span style="color:${colr}">${r}% prognozy</span>`;
          } else if (fcNow == null) {
            rel = 'brak prognozy godzinowej';
          }
          return `<div class="pl-row"><div class="pl-h"><span>☀️ Moc PV teraz</span><b>${this._fx(pvKw, 1)} kW${fcNow != null ? ` <small style="color:var(--muted);font-weight:500;">· prognoza ${this._fx(fcNow, 1)} kW</small>` : ''}</b></div>
            <div class="pl-bar" style="position:relative;overflow:visible;"><div style="width:${pct.toFixed(0)}%;background:#ffcc00;"></div>${mark != null ? `<span title="prognoza PV na tę godzinę" style="position:absolute;top:-2px;bottom:-2px;left:${mark.toFixed(1)}%;width:2px;background:var(--text);"></span>` : ''}</div>
            <div class="pl-n" style="display:flex;justify-content:space-between;"><span>0 — ${scale} kW</span><span>${rel}</span></div></div>`;
        })() +
        (() => {
          const socNow = Math.max(0, Math.min(100, this._num('soc')));
          const unit = capK > 0 ? capK : 0;
          const kwhNow = unit * socNow / 100;
          const rsA = (this._hass.states[this._eid('sensor', 'reserve_soc')] || {}).attributes || {};
          const flr = Number(rsA.inverter_floor); const hasFl = isFinite(flr) && flr > 0 && flr < 100;
          const note = `dziś naładowano ${this._fx(ch, 1)} kWh · oddano ${this._fx(dis, 1)} kWh`;
          const flNote = hasFl ? ` · próg odcięcia falownika ${Math.round(flr)}%${unit > 0 ? ` (dostępne ~${this._fx(Math.max(0, unit * (socNow - flr) / 100), 1)} kWh)` : ''}` : '';
          return `<div class="pl-row"><div class="pl-h"><span>🔋 W baterii teraz</span><b>${unit > 0 ? this._fx(kwhNow, 1) + ' kWh · ' : ''}${socNow.toFixed(0)}%</b></div>
            <div class="pl-bar" style="position:relative;overflow:visible;"><div style="width:${socNow.toFixed(0)}%;background:#34c759;"></div>${hasFl ? `<span title="próg odcięcia falownika ${Math.round(flr)}%" style="position:absolute;top:-2px;bottom:-2px;left:${flr.toFixed(1)}%;width:2px;background:var(--red);"></span>` : ''}</div>
            <div class="pl-n">${unit > 0 ? '0 — ' + this._fx(unit, 1) + ' kWh · ' : ''}${note}${flNote}</div></div>`;
        })() +
        row('🔌', 'Sieć: eksport względem importu', exp, Math.max(exp, imp), 'kWh', '#af52de', `import ${this._fx(imp, 1)} kWh` + (selfSuff != null ? ` · samowystarczalność ${Math.round(selfSuff)}%` : '')) +
        this._moneyTableHtml();
    }

    // Tabelka „Sprzedaż i zakup energii”: dziś / miesiąc / razem (kwoty z księgi rozliczeń, sensor „EMS Bilans dziś”).
    _moneyTableHtml() {
      const st = this._hass && this._hass.states[this._eid('sensor', 'profit_today')];
      const sums = st && st.attributes && st.attributes.sums;
      if (!sums || !sums.day) return '';
      const cols = [['Dziś', sums.day], ['Tydz.', sums.week || {}], ['Miesiąc', sums.month || {}], ['Poprz. m.', sums.prev_month || {}], ['Rok', sums.year || sums.total || {}]];
      const money = (v, sign) => { const n = Number(v); if (!isFinite(n)) return '—'; const a = Math.abs(n); const t = a >= 1000 ? String(Math.round(a)).replace(/\B(?=(\d{3})+(?!\d))/g, '\u00a0') : a.toFixed(2).replace('.', ','); return (sign ? (n < 0 ? '−' : '+') : '') + t; };
      const td = (c, st2) => `<td style="text-align:right;padding:7px 0;border-top:0.5px solid rgba(128,128,128,.3);${st2 || ''}">${c}</td>`;
      const lab = (t, st2) => `<td style="text-align:left;padding:7px 0;border-top:0.5px solid rgba(128,128,128,.3);${st2 || ''}">${t}</td>`;
      const mut = 'color:var(--muted);';
      const ex = (st.attributes && st.attributes.extras) || {};
      const keys = ['day', 'week', 'month', 'prev_month', 'year'];
      const sv = (k) => ex[k] && ex[k].savings;
      const hasSv = keys.some(k => sv(k) && sv(k).saving != null);
      const pc = (v) => String(Math.round(Number(v) || 0));
      const sp = ex.day && ex.day.split;
      const splitHtml = sp ? `<div data-role="split" style="margin-top:12px;"><div style="font-size:12px;${mut}">Skąd energia dla domu dziś (szac.) · ${Number(sp.load_kwh).toFixed(1).replace('.', ',')} kWh</div>
          <div style="display:flex;height:14px;border-radius:7px;overflow:hidden;margin-top:5px;background:var(--line);">
            <div title="PV bezpośrednio" style="width:${pc(sp.pv_pct)}%;background:#ffcc00;"></div>
            <div title="bateria" style="width:${pc(sp.battery_pct)}%;background:#34c759;"></div>
            <div title="sieć" style="width:${pc(sp.grid_pct)}%;background:#af52de;"></div></div>
          <div style="font-size:12px;margin-top:4px;display:flex;gap:12px;flex-wrap:wrap;"><span><span style="color:#ffcc00;">■</span> PV ${pc(sp.pv_pct)}%</span><span><span style="color:#34c759;">■</span> bateria ${pc(sp.battery_pct)}%</span><span><span style="color:#af52de;">■</span> sieć ${pc(sp.grid_pct)}%</span></div></div>` : '';
      const tf = ex.month && ex.month.tariff;
      const tariffHtml = tf ? `<div data-role="tariff" style="font-size:12px;margin-top:10px;${mut}">Pobór z sieci w tym miesiącu: drogie godziny ${Number(tf.peak_kwh).toFixed(1).replace('.', ',')} kWh (${pc(tf.peak_pct)}%) · tanie ${Number(tf.offpeak_kwh).toFixed(1).replace('.', ',')} kWh (${pc(tf.offpeak_pct)}%)</div>` : '';
      return `<div class="pl-row" data-role="money-table"><div class="pl-h"><span>💰 Sprzedaż i zakup energii</span><small style="color:var(--muted);font-weight:400;">kwoty w zł</small></div>
        <table style="width:100%;border-collapse:collapse;font-size:12.5px;margin-top:6px;">
          <tr><th style="text-align:left;font-weight:400;${mut}"></th>${cols.map(([n]) => `<th style="text-align:right;font-weight:400;${mut}">${n}</th>`).join('')}</tr>
          <tr>${lab('Sprzedałem')}${cols.map(([, d]) => td(money(d.revenue), 'color:#34c759;')).join('')}</tr>
          <tr>${lab('Kupiłem')}${cols.map(([, d]) => td(money(d.cost), 'color:#ff9f0a;')).join('')}</tr>
          <tr>${lab('<b style="font-weight:500;">Saldo</b>')}${cols.map(([, d]) => td(money(d.net, true), `font-weight:500;color:${Number(d.net) < 0 ? '#ff453a' : '#34c759'};`)).join('')}</tr>
          ${hasSv ? `<tr>${lab('Bez PV i baterii (szac.)', mut)}${keys.map(k => td(sv(k) && sv(k).without_cost != null ? money(sv(k).without_cost) : '—', mut)).join('')}</tr>
          <tr>${lab('Oszczędzam (szac.)')}${keys.map(k => td(sv(k) && sv(k).saving != null ? money(sv(k).saving, true) : '—', 'font-weight:500;color:#34c759;')).join('')}</tr>` : ''}
        </table>${splitHtml}${tariffHtml}</div>`;
    }
  }

  // <<MODULES-BEGIN>>
  // =====================================================================
  //  MODUŁY ŁADOWANE NA ŻĄDANIE
  //  Diagnostyka (bms-diag.js) i dodatki (bms-extras.js: plan 24 h, raport, kreator) są osobnymi plikami,
  //  pobieranymi dopiero przy pierwszym użyciu. Dzięki temu rdzeń (ten plik) jest o ponad jedną trzecią mniejszy,
  //  a użytkownik bez uprawnień administratora nigdy nie pobiera kodu Diagnostyki.
  //  Kontrakt (numer) musi zgadzać się w obu plikach — inaczej moduł nie jest instalowany, a karta pokazuje
  //  czytelny komunikat zamiast działać na niezgodnej wersji.
  // =====================================================================
  // Wersja tego pliku (ustawiana skryptem pakującym z manifest.json). Każdy moduł niesie tę samą w install.version:
  // gdy się różnią, przeglądarka podała starą kopię modułu z pamięci podręcznej.
  const CARD_VERSION = '0.9.6.3';
  const MOD_TIMEOUT_MS = 20000;
  const MODULES = {
    diag:   { file: 'bms-diag.js',   global: '__bmsDiagInstall',   contract: 1, label: 'Diagnostyki', p: null, ready: false, err: '', got: '' },
    extras: { file: 'bms-extras.js', global: '__bmsExtrasInstall', contract: 1, label: 'dodatków (plan 24 h, raport, kreator)', p: null, ready: false, err: '', got: '' },
    devices: { file: 'bms-devices.js', global: '__bmsDevicesInstall', contract: 1, label: 'Urządzeń', p: null, ready: false, err: '', got: '' },
  };
  // Adres tego pliku (z parametrem ?v=wersja.mtime). Rdzeń bywa ładowany przez import() bez elementu <script>, a bufor
  // zasobów przeglądarki w długo otwartym Home Assistancie bywa pełny — wtedy adresu nie da się ustalić.
  const OWN_URL = (() => {
    try { if (document.currentScript && document.currentScript.src) return document.currentScript.src; } catch (e) { /* moduł ES */ }
    try { const sc = Array.from(document.scripts).find(x => /\/bms_komp_dec\/bms-panel\.js/.test(x.src)); if (sc) return sc.src; } catch (e) { /* ignoruj */ }
    try { const en = performance.getEntriesByType('resource').find(x => /\/bms_komp_dec\/bms-panel\.js/.test(x.name)); if (en) return en.name; } catch (e) { /* ignoruj */ }
    return '';
  })();
  const MOD_BASE = OWN_URL ? OWN_URL.replace(/[?#].*$/, '').replace(/[^/]*$/, '') : '/bms_komp_dec/';
  const MOD_VER = (() => { try { return new URL(OWN_URL).searchParams.get('v') || ''; } catch (e) { return ''; } })();
  // Wersja uruchomionej integracji (z adresu rdzenia) zgadza się z wersją tego pliku?
  const VER_SAME = (v) => !v || v === CARD_VERSION || v.indexOf(CARD_VERSION + '.') === 0;
  // Adres modułu ZAWSZE niesie wersję (dawniej, gdy adresu rdzenia nie dało się ustalić, moduł był pobierany bez ?v=
  // i przeglądarka mogła podać starą kopię sprzed aktualizacji).
  const MOD_TAG = MOD_VER && VER_SAME(MOD_VER) ? MOD_VER : CARD_VERSION;

  // Pobiera skrypt; zwraca '' (OK), 'net' (błąd pobierania) albo 'timeout'. Nie wisi w nieskończoność — po MOD_TIMEOUT_MS kończy z błędem.
  function bmsLoadScript(url, ms) {
    return new Promise((resolve) => {
      let done = false, timer = 0;
      const el = document.createElement('script');
      const fin = (err) => { if (done) return; done = true; clearTimeout(timer); if (err) el.remove(); resolve(err); };
      timer = setTimeout(() => fin('timeout'), ms);
      el.async = true;
      el.onload = () => fin('');
      el.onerror = () => fin('net');
      el.src = url;
      document.head.appendChild(el);
    });
  }

  function bmsLoadModule(name) {
    const m = MODULES[name];
    if (!m) return Promise.resolve(false);
    if (m.ready) return Promise.resolve(true);
    if (m.p) return m.p;
    // Sprawdza moduł z window: {} = OK, {err, stale} = powód (stale: zła wersja → warto pobrać ponownie z unikalnym adresem)
    const check = () => {
      const fn = window[m.global];
      if (typeof fn !== 'function') return { err: `plik ${m.file} nie zawiera modułu` };
      m.got = fn.version || '';
      if (fn.contract !== m.contract) return { err: `niezgodna wersja modułu (jest ${fn.contract}, wymagana ${m.contract}) — odśwież stronę (Ctrl+F5) lub zaktualizuj wszystkie pliki integracji`, stale: true };
      if (m.got !== CARD_VERSION) return { err: `moduł ${m.file} ma wersję ${m.got || 'nieznaną'}, a karta ${CARD_VERSION} — przeglądarka podała starą kopię z pamięci podręcznej; odśwież stronę (Ctrl+F5) lub wyczyść pamięć podręczną aplikacji`, stale: true };
      return {};
    };
    const install = () => {
      const fn = window[m.global];
      try { fn(BmsPanel, { TC, version: CARD_VERSION, urlVersion: MOD_VER }); } catch (e) { m.err = 'błąd modułu: ' + (e && e.message ? e.message : e); console.error('EMS: moduł ' + name, e); return false; }
      m.ready = true; m.err = ''; return true;
    };
    m.p = (async () => {
      if (typeof window[m.global] === 'function') {                                // moduł już na stronie (np. pakiet)
        const c = check();
        if (!c.err) return install();
      }
      for (let attempt = 0; attempt < 2; attempt++) {
        try { delete window[m.global]; } catch (e) { window[m.global] = undefined; }
        // druga próba: unikalny adres omija kopię z pamięci podręcznej przeglądarki
        const url = MOD_BASE + m.file + '?v=' + encodeURIComponent(MOD_TAG) + (attempt ? '&nc=' + Date.now() : '');
        const err = await bmsLoadScript(url, MOD_TIMEOUT_MS);
        if (err) {
          m.err = err === 'timeout'
            ? `pobieranie ${m.file} trwa zbyt długo (ponad ${Math.round(MOD_TIMEOUT_MS / 1000)} s) — sprawdź połączenie z Home Assistantem`
            : `nie udało się pobrać ${m.file} (sprawdź, czy plik jest w folderze frontend integracji i zrestartuj HA)`;
          return false;
        }
        const c = check();
        if (!c.err) return install();
        m.err = c.err;
        if (!c.stale) return false;
      }
      return false;
    })().catch((e) => { m.err = 'błąd ładowania: ' + (e && e.message ? e.message : e); return false; });
    m.p.then((ok) => { if (!ok) m.p = null; });      // kolejna próba możliwa po błędzie
    return m.p;
  }
  const bmsEsc = (t) => String(t).replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  const bmsModuleError = (name) => `<div class="chart-empty" style="color:var(--danger,#d33);">Nie udało się wczytać modułu ${MODULES[name].label}: ${bmsEsc(MODULES[name].err || 'nieznany błąd')}<br><button type="button" class="btn" data-mod-retry="${name}" style="margin-top:10px;padding:8px 14px;">↻ Spróbuj ponownie</button><div style="margin-top:10px;font-size:11px;opacity:.75;color:var(--secondary-text-color,inherit);">karta ${bmsEsc(CARD_VERSION)} · integracja ${bmsEsc(MOD_VER || '?')} · moduł ${bmsEsc(MODULES[name].got || '—')}</div></div>`;

  // Ikony zakładek (SVG, kolor = currentColor)
  const TAB_SVG = (() => {
    const mk = (p) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;
    return {
      main: mk('<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/>'),
      charts: mk('<path d="M5 20V11"/><path d="M12 20V4"/><path d="M19 20v-6"/>'),
      ems: mk('<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>'),
      log: mk('<circle cx="12" cy="12" r="9"/><path d="M9 9.5c0-1 1-1.5 3-1.5s3 .5 3 1.5-1 1.5-3 1.5-3 .5-3 1.5 1 1.5 3 1.5 3-.5 3-1.5"/><path d="M12 6v2M12 16v2"/>'),
      dev: mk('<path d="M9 2v5M15 2v5"/><path d="M6 7h12v4a6 6 0 0 1-12 0z"/><path d="M12 17v5"/>'),
      diag: mk('<circle cx="12" cy="12" r="3"/><circle cx="12" cy="12" r="8" stroke-dasharray="3.1 2.6"/>'),
    };
  })();

  // Zaślepki: działają do czasu załadowania modułu, potem moduł nadpisuje je pełnymi wersjami.
  const DG_STUBS = {
    _devTabSync() {            // przełącznik z Ustawień → Tryby: chowa całą zakładkę Urządzenia
      const st = this._hass && this._hass.states[this._eid('switch', 'hide_devices_tab')];
      const hide = !!st && st.state === 'on';
      const b = this._el('tabDev'); if (!b) return;
      b.style.display = hide ? 'none' : '';
      const hd = this._el('hubDev'); if (hd) hd.style.display = hide ? 'none' : '';
      if (hide && this._activeTab === 'dev') { const m = this.shadowRoot && this.shadowRoot.querySelector('.tab[data-tab="main"]'); if (m) m.click(); }
    },
    _tabsPosSync() {           // przełącznik z Ustawień → Tryby: pasek zakładek na górze zamiast na dole
      const wrap = this.shadowRoot && this.shadowRoot.querySelector('.app');
      const nav = wrap && wrap.querySelector('#tabsNav'); if (!nav) return;
      const st = this._hass && this._hass.states[this._eid('switch', 'tabs_top')];
      const top = !!st && st.state === 'on';
      nav.classList.toggle('bottom', !top);
      if (top) { const pb = wrap.querySelector('#priceBar'); if (pb && nav.nextElementSibling !== pb) wrap.insertBefore(nav, pb); }
      else if (wrap.lastElementChild !== nav) wrap.appendChild(nav);
    },
    _setWarnSync() {           // zestaw z ustawionymi godzinami, ale wyłączonym przełącznikiem — okno nigdy nie wystartuje
      const root = this.shadowRoot, ems = root && root.querySelector('[data-tab-content="ems"]'); if (!ems || !this._hass) return;
      const SETS = [
        ['bateria_sprzedaz_1', 'Sprzedaż z baterii — zestaw 1', 'bateria_sprzedaz_start', 'bateria_sprzedaz_stop'],
        ['bateria_sprzedaz_2', 'Sprzedaż z baterii — zestaw 2', 'bateria_sprzedaz_start_2', 'bateria_sprzedaz_stop_2'],
        ['ladowanie_z_sieci_1', 'Ładowanie z sieci — zestaw 1', 'start_grid_charge', 'stop_grid_charge'],
        ['ladowanie_z_sieci_2', 'Ładowanie z sieci — zestaw 2', 'start_grid_charge_2', 'stop_grid_charge_2'],
      ];
      const hm = (k) => String(this._st(this._eid('time', k)) || '').slice(0, 5);
      const items = [];
      SETS.forEach(([sw, name, k1, k2]) => {
        if (this._st(this._eid('switch', sw)) !== 'off') return;
        const a = hm(k1), b = hm(k2);
        if (!/^\d\d:\d\d$/.test(a) || !/^\d\d:\d\d$/.test(b) || a === '00:00' || b === '00:00' || a === b) return;
        items.push([sw, name, a, b]);
      });
      let box = root.getElementById('setWarn');
      if (!items.length) { if (box) box.remove(); return; }
      const sig = JSON.stringify(items);
      if (!box) {
        box = document.createElement('div'); box.id = 'setWarn'; box.className = 'set-warn';
        box.addEventListener('click', (ev) => {
          const bt = ev.target.closest && ev.target.closest('[data-set-on]'); if (!bt) return;
          this._hass.callService('switch', 'turn_on', { entity_id: this._eid('switch', bt.dataset.setOn) });
        });
        ems.insertBefore(box, ems.firstChild);
      }
      if (box._sig === sig) return;
      box._sig = sig;
      box.innerHTML = items.map(([sw, name, a, b]) => `<div class="set-warn-row"><span>⚠️ <b>${name}</b> jest wyłączony, a ma ustawione godziny ${a}–${b} — okno nie wystartuje.</span><button type="button" data-set-on="${sw}">Włącz</button></div>`).join('');
    },
    _dgIsAdmin() { const u = this._hass && this._hass.user; return !!(u && u.is_admin); },
    _dgSyncTab() {
      const b = this._el('tabDiag');
      if (b) {
        b.style.display = this._dgIsAdmin() ? '' : 'none';
        const hg = this._el('hubDiag'); if (hg) hg.style.display = this._dgIsAdmin() ? '' : 'none';
        // alarm z integracji widać na zakładce, zanim załaduje się moduł Diagnostyki
        const ms = this._hass && this._hass.states[this._eid('sensor', 'monitor_status')];
        const be = ms && ms.attributes && Array.isArray(ms.attributes.alarms) ? ms.attributes.alarms.length : 0;
        const want = 'Ustawienia' + (be ? ' ⚠' : '');
        const lb = b.querySelector('.tl');
        if (lb && lb.textContent !== want) lb.textContent = want;
        b.classList.toggle('warn', !!be);
        const sb = this._el('tabSettings');
        if (sb) { sb.classList.toggle('warn', !!be && this._dgIsAdmin()); const sl = sb.querySelector('.tl'); const w2 = 'Ustawienia' + (be && this._dgIsAdmin() ? ' ⚠' : ''); if (sl && sl.textContent !== w2) sl.textContent = w2; }
      }
    },
    _dgTick() { /* bez modułu nic do odświeżania */ },
    _dgDestroyChart() { /* bez modułu brak wykresu */ },
    _dgOpen() {
      const root = this._el('diagRoot');
      if (MODULES.diag.ready) return;
      if (root) root.innerHTML = '<div class="chart-empty">Ładowanie modułu Diagnostyki…</div>';
      bmsLoadModule('diag').then((ok) => {
        if (this._activeTab !== 'diag') return;
        const fail = (why) => { MODULES.diag.err = why; MODULES.diag.p = null; const r = this._el('diagRoot'); if (r) r.innerHTML = bmsModuleError('diag'); };
        if (!ok) { fail(MODULES.diag.err || 'nieznany błąd'); return; }
        if (this._dgOpen === DG_STUBS._dgOpen) { fail('moduł załadowany, ale nie zainstalował Diagnostyki'); return; }     // moduł nie podmienił zaślepki
        try { this._dgOpen(); } catch (e) { console.error('EMS: Diagnostyka', e); fail('błąd przy otwieraniu Diagnostyki: ' + (e && e.message ? e.message : e)); return; }
        if (!this._el('dgHost')) fail('moduł nie wyświetlił Diagnostyki');          // nigdy nie zostawiamy samego napisu „Ładowanie…”
      });
    },
  };
  Object.assign(BmsPanel.prototype, DG_STUBS);

  // Dodatki (bms-extras.js): plan 24 h, raport miesięczny, zdrowie baterii, kreator instalacji.
  // Placeholdery w karcie: #exPlanBox, #exWizBox (zakładka EMS) oraz #exReportBox, #exHealthBox (Zysk i log).
  const EX_BOXES = ['exPlanBox', 'exWizBox', 'exProfBox', 'exReportBox', 'exHealthBox', 'exSavBox', 'exAccBox', 'exTblBox', 'exOvrBox', 'exHistBox', 'exSimBox'];  // exMainBox (ekran główny) celowo poza listą: ma własny pusty stan
  const EX_STUBS = {
    _exRender() { /* bez modułu nic do rysowania */ },
    _exFail() {
      const html = bmsModuleError('extras');
      EX_BOXES.forEach((id) => { const b = this._el(id); if (b) b.innerHTML = html; });
    },
    _exEnsure() {
      if (MODULES.extras.ready) { this._exRender(); return; }
      if (MODULES.extras.err && Date.now() - (this._exTryAt || 0) < 30000) { this._exFail(); return; }     // nie ponawiamy w pętli
      this._exTryAt = Date.now();
      bmsLoadModule('extras').then((ok) => {
        if (ok && this._exRender === EX_STUBS._exRender) { MODULES.extras.err = 'moduł załadowany, ale nie zainstalował dodatków'; ok = false; }
        if (!ok) { this._exFail(); return; }
        this._safe(() => this._exRender());
      });
    },
    _exRetry() { this._exTryAt = 0; this._exEnsure(); },
  };
  Object.assign(BmsPanel.prototype, EX_STUBS);
  // Urządzenia (bms-devices.js): zakładka „Urządzenia” — ładowana przy pierwszym otwarciu.
  const DEV_STUBS = {
    _devOpen() { /* bez modułu nic do rysowania */ },
    _devTick() { /* bez modułu nic do odświeżania */ },
    _devEnsure() {
      const root = this._el('devRoot');
      if (MODULES.devices.ready) { this._devOpen(); return; }
      if (root && !root.innerHTML) root.innerHTML = '<div class="chart-empty">Ładowanie modułu Urządzeń…</div>';
      bmsLoadModule('devices').then((ok) => {
        if (ok && this._devOpen === DEV_STUBS._devOpen) { MODULES.devices.err = 'moduł załadowany, ale nie zainstalował Urządzeń'; ok = false; }
        const r = this._el('devRoot');
        if (!ok) { if (r) r.innerHTML = bmsModuleError('devices'); return; }
        if (this._activeTab === 'dev') this._safe(() => this._devOpen());
      });
    },
  };
  Object.assign(BmsPanel.prototype, DEV_STUBS);
  // <<MODULES-END>>

  // ======================= MAŁA KARTA (bms-mini-card) =======================
  // Osobna, niewielka karta do wstawienia w dowolnym dashboardzie HA: bateria, moce, pasek planu 24 h i opis, co EMS zaplanował.
  // Dziedziczy odczyt encji z karty głównej, ale nie ładuje modułów, historii ani pogody.
  const MINI_CSS = `
    .mini { padding: 14px 16px; color: var(--text); }
    .mini[data-nav] { cursor: pointer; }
    .mini-h { display: flex; align-items: baseline; gap: 8px; justify-content: space-between; margin-bottom: 10px; }
    .mini-t { font-size: 15px; font-weight: 700; } .mini-sub { font-size: 12px; color: var(--muted); text-align: right; }
    .mini-top { display: flex; align-items: center; gap: 14px; }
    .mini-ring { flex: none; width: 104px; } .mini-ring svg { width: 100%; height: auto; display: block; }
    .mini-nums { flex: 1; min-width: 0; display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    .mini-n { background: var(--surface); border-radius: 12px; padding: 8px 10px; display: flex; flex-direction: column; gap: 1px; min-width: 0; }
    .mini-n i { font-style: normal; font-size: 14px; line-height: 1.2; } .mini-n b { font-size: 15px; white-space: nowrap; } .mini-n span { font-size: 11px; color: var(--muted); }
    .mini-strip { display: flex; align-items: flex-end; gap: 2px; height: 46px; margin-top: 14px; }
    .mini-strip i { flex: 1; min-width: 0; border-radius: 3px 3px 1px 1px; opacity: .92; }
    .mini-strip i.now { outline: 2px solid var(--text); outline-offset: 1px; }
    .mini-ticks { display: flex; justify-content: space-between; font-size: 10.5px; color: var(--muted); margin-top: 4px; }
    .mini-leg { display: flex; gap: 10px; flex-wrap: wrap; font-size: 10.5px; color: var(--muted); margin-top: 4px; } .mini-leg b { display: inline-block; width: 8px; height: 8px; border-radius: 2px; margin-right: 4px; }
    .mini .ps { margin: 12px 0 0; }
    .mini-empty { padding: 18px 8px; text-align: center; color: var(--muted); font-size: 13px; }
  `;
  let MINI_SHEET;
  const miniSheet = () => {
    if (MINI_SHEET !== undefined) return MINI_SHEET;
    try { const sh = new CSSStyleSheet(); sh.replaceSync(STYLES + SKIN_M3 + SKIN_COMMON + SKIN_GLASS + SKIN_MATRIX + SKIN_SPACE + SKIN_COMFORT + SKIN_HERO + MINI_CSS); MINI_SHEET = sh; } catch (e) { MINI_SHEET = null; }
    return MINI_SHEET;
  };
  class BmsMini extends BmsPanel {
    static getStubConfig() { return { title: 'Centrum Energii' }; }
    getCardSize() { return 6; }
    getGridOptions() { return { columns: 12, rows: 'auto', min_columns: 6 }; }
    setConfig(config) {
      this._config = Object.assign({ title: 'Centrum Energii', show_flow: true, show_strip: true, show_summary: true }, config || {});
      this._miniKey = null;
      if (this._hass && this.shadowRoot) this._miniDraw();
    }
    connectedCallback() { /* bez pętli animacji karty głównej */ }
    disconnectedCallback() { /* nic do sprzątania */ }
    // mała karta korzysta tylko ze stylu i motywu konta — układu panelu nie ma
    _prefsApplied() { this._applyTheme(); this._miniKey = null; if (this._hass && this.shadowRoot) this._miniDraw(); }
    set hass(hass) {
      this._hass = hass;
      PREFS.attach(this, hass);
      try { const bs = Number(this._rsAttrs().battery_charge_sign); if (bs === 1 || bs === -1) INVERT_BATTERY_SIGN = (bs === -1); } catch (e) { /* zostaje poprzednia wartość */ }
      if (!this.shadowRoot) this.attachShadow({ mode: 'open' });
      if (!this._miniInit) {
        this._miniInit = true;
        const sh = miniSheet();
        if (sh) this.shadowRoot.adoptedStyleSheets = [sh];
        else { const st = document.createElement('style'); st.textContent = STYLES + SKIN_M3 + SKIN_COMMON + SKIN_GLASS + SKIN_MATRIX + SKIN_SPACE + SKIN_COMFORT + SKIN_HERO + MINI_CSS; this.shadowRoot.appendChild(st); }
        const box = document.createElement('div'); box.id = 'miniBox'; this.shadowRoot.appendChild(box);
        box.addEventListener('click', () => {
          const p = this._config && this._config.navigation_path; if (!p || typeof p !== 'string') return;
          try { history.pushState(null, '', p); window.dispatchEvent(new CustomEvent('location-changed', { detail: { replace: false } })); } catch (e) { /* brak nawigacji */ }
        });
        box.addEventListener('keydown', (ev) => { if ((ev.key === 'Enter' || ev.key === ' ') && ev.target === box.firstElementChild && box.firstElementChild.hasAttribute('data-nav')) { ev.preventDefault(); box.click(); } });
      }
      this._applyTheme();
      this._miniDraw();
    }
    _miniDraw() {
      const box = this.shadowRoot && this.shadowRoot.getElementById('miniBox'); if (!box || !this._hass) return;
      const cfg = this._config || { title: 'Centrum Energii', show_flow: true, show_strip: true, show_summary: true };
      if (!this._hass.states[this._eid('sensor', 'plan_view')] && !this._hass.states[this._eid('sensor', 'reserve_soc')] && !isFinite(this._num('soc', NaN))) {
        const html = '<div class="chart-card mini"><div class="mini-empty">Brak danych EMS — sprawdź, czy integracja „EMS komp-dec” jest uruchomiona.</div></div>';
        if (this._miniKey !== html) { this._miniKey = html; box.innerHTML = html; } return;
      }
      const o = this._flowNow(), m = this._homeModel(o), pvA = this._pvAttrs(), rows = Array.isArray(pvA.table) ? pvA.table : [];
      const hour = new Date().getHours(), nav = !!(cfg.navigation_path && typeof cfg.navigation_path === 'string');
      const key = JSON.stringify([cfg, Math.round(o.pv / 50), Math.round(o.load / 50), Math.round(o.grid / 50), Math.round(o.batt / 50), Math.round(o.soc), m.flr, m.tgt, hour, pvA.generated_at, rows.length, THEME.mode, this.getAttribute('data-skin')]);
      if (key === this._miniKey) return;
      this._miniKey = key;
      const E = bmsEsc, kw = (w) => (Math.abs(w) < 1000 ? Math.round(Math.abs(w)) + ' W' : (Math.abs(w) / 1000).toFixed(1).replace('.', ',') + ' kW');
      const TH = m.TH, bcol = o.batt > TH ? 'var(--green)' : (o.batt < -TH ? 'var(--orange)' : 'var(--accent)');
      const r = 46, c = 2 * Math.PI * r, soc = Math.max(0, Math.min(100, o.soc)), at = (rad, p) => [60 + rad * Math.cos((p * 360 - 90) * Math.PI / 180), 60 + rad * Math.sin((p * 360 - 90) * Math.PI / 180)];
      let ring = `<circle cx="60" cy="60" r="${r}" fill="none" style="stroke:var(--seg-bg)" stroke-width="13"/><circle cx="60" cy="60" r="${r}" fill="none" style="stroke:${bcol}" stroke-width="13" stroke-linecap="round" stroke-dasharray="${(c * soc / 100).toFixed(1)} ${c.toFixed(1)}" transform="rotate(-90 60 60)"/>`;
      if (m.hasFl) { const [x1, y1] = at(r - 9, m.flr / 100), [x2, y2] = at(r + 9, m.flr / 100); ring += `<path d="M${x1.toFixed(1)} ${y1.toFixed(1)}L${x2.toFixed(1)} ${y2.toFixed(1)}" style="stroke:var(--text)" stroke-width="2.4" stroke-linecap="round"><title>rezerwa falownika ${Math.round(m.flr)}%</title></path>`; }
      ring += `<text x="60" y="70" text-anchor="middle" font-weight="700" font-size="30" style="fill:var(--text);font-family:inherit">${Math.round(soc)}<tspan font-size="15" dy="-10">%</tspan></text>`;
      const gl = o.grid > TH ? 'z sieci' : (o.grid < -TH ? 'do sieci' : 'sieć');
      const nums = cfg.show_flow === false ? '' : `<div class="mini-nums">
        <div class="mini-n"><i aria-hidden="true">☀️</i><b>${E(kw(o.pv))}</b><span>produkcja PV</span></div>
        <div class="mini-n"><i aria-hidden="true">🏠</i><b>${E(kw(o.load))}</b><span>zużycie domu</span></div>
        <div class="mini-n"><i aria-hidden="true">⚡</i><b>${E(kw(o.grid))}</b><span>${E(gl)}</span></div>
        <div class="mini-n"><i aria-hidden="true">🔋</i><b>${E(kw(o.batt))}</b><span>${o.batt > TH ? 'ładowanie' : (o.batt < -TH ? 'rozładowanie' : 'spoczynek')}</span></div></div>`;
      const cmap = { grid: '#0a84ff', sell: '#ff9f0a', pv: '#30d158', home: '#a78bfa', idle: 'var(--seg-bg)' };   // stałe kolory akcji — czytelne w każdym stylu
      const plan = m.plan;
      const strip = cfg.show_strip === false || plan.length < 6 ? '' : `<div class="mini-strip" role="img" aria-label="Plan baterii na najbliższe 24 godziny">${plan.map((p, i) => `<i class="${i === 0 ? 'now' : ''}" style="height:${Math.max(14, Math.min(100, isFinite(Number(p.soc)) ? Number(p.soc) : 0))}%;background:${cmap[p.action] || cmap.idle}" title="${String(p.h).padStart(2, '0')}:00 — ${E(p.label || '')}${isFinite(Number(p.soc)) ? ', SOC ' + Math.round(Number(p.soc)) + '%' : ''}"></i>`).join('')}</div>
        <div class="mini-ticks">${[0, 6, 12, 18].filter((i) => i < plan.length).map((i) => `<span>${i === 0 ? 'teraz' : String(plan[i].h).padStart(2, '0') + ':00'}</span>`).join('')}<span>+24 h</span></div>
        <div class="mini-leg"><span><b style="background:${cmap.grid}"></b>z sieci</span><span><b style="background:${cmap.sell}"></b>sprzedaż</span><span><b style="background:${cmap.pv}"></b>PV</span><span><b style="background:${cmap.home}"></b>bateria → dom</span><span>wysokość = planowany SOC</span></div>`;
      const sum = cfg.show_summary === false ? '' : (this._planSummaryHtml(rows) || '<div class="ps"><div class="ps-h">🧭 Co EMS planuje na najbliższe 24 h</div><div class="ps-n">Plan jeszcze nie jest policzony albo brakuje danych (SOC, prognozy).</div></div>');
      const sub = [m.battTxt, m.pace].filter(Boolean).join(' · ');
      box.innerHTML = `<div class="chart-card mini" ${nav ? 'data-nav="1" role="link" tabindex="0"' : ''} aria-label="${E(cfg.title || 'Centrum Energii')}">
        <div class="mini-h"><span class="mini-t">${E(cfg.title || 'Centrum Energii')}</span><span class="mini-sub">${E(sub)}</span></div>
        <div class="mini-top"><div class="mini-ring"><svg viewBox="0 0 120 120" role="img" aria-label="Poziom baterii ${Math.round(soc)}%">${ring}</svg></div>${nums}</div>${strip}${sum}</div>`;
    }
  }

  if (!customElements.get('bms-panel-card')) {
    try { customElements.define('bms-panel-card', BmsPanel); }
    catch (e) { console.error('EMS PANEL: define failed', e); }
  }
  window.customCards = window.customCards || [];
  if (!window.customCards.some(c => c && c.type === 'bms-panel-card')) {
    window.customCards.push({ type: 'bms-panel-card', name: 'Centrum Energii', description: 'EMS Panel', preview: true });
  }
  if (!customElements.get('bms-mini-card')) {
    try { customElements.define('bms-mini-card', BmsMini); }
    catch (e) { console.error('EMS PANEL: define mini failed', e); }
  }
  if (!window.customCards.some(c => c && c.type === 'bms-mini-card')) {
    window.customCards.push({ type: 'bms-mini-card', name: 'Centrum Energii — mała karta', description: 'Bateria, moce i plan EMS na najbliższe 24 h', preview: true });
  }
})();