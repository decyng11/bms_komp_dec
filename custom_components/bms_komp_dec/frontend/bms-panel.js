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

  const STYLES = `
    :host { --bg:#000; --card:#1c1c1e; --surface:rgba(255,255,255,0.06); --line:rgba(255,255,255,0.10); --text:#fff; --text2:#e5e5ea; --muted:#8e8e93; --muted2:#6e6e73; --accent:#0a84ff; --green:#30d158; --orange:#ff9f0a; --red:#ff453a; --input-bg:#2c2c2e; --seg-bg:rgba(118,118,128,0.24); --seg-active:#636366; --shadow:none; --pf-bg:#1c1c1e; color-scheme: dark; }
    :host([data-theme="light"]) { --bg:#e4e4e9; --card:#f0f0f4; --surface:rgba(60,60,67,0.07); --line:rgba(60,60,67,0.12); --text:#1c1c1e; --text2:#3a3a3c; --muted:#6c6c70; --muted2:#8e8e93; --accent:#0a84ff; --green:#34c759; --orange:#ff9500; --red:#ff3b30; --input-bg:#e4e4e9; --seg-bg:rgba(118,118,128,0.14); --seg-active:#f7f7fa; --shadow:0 1px 2px rgba(0,0,0,0.05),0 6px 18px rgba(0,0,0,0.07); --pf-bg:#f0f0f4; color-scheme: light; }
    :host { display: block; background: var(--bg); color: var(--text); border-radius: 22px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; overflow-x: hidden; }
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
    .theme-seg { display: inline-flex; padding: 3px; background: var(--seg-bg); border-radius: 999px; flex: none; }
    .theme-seg button { border: none; background: transparent; color: var(--muted); width: 34px; height: 30px; border-radius: 999px; cursor: pointer; font-size: 15px; line-height: 1; padding: 0; }
    .theme-seg button.active { background: var(--seg-active); color: var(--text); box-shadow: 0 1px 4px rgba(0,0,0,0.18); }
    .tabs { background: var(--seg-bg); border-radius: 14px; padding: 3px; }
    .tab { border-radius: 11px; color: var(--text2); font-weight: 600; }
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
      if (this._rendered && this._activeTab === 'main') this._startFlowLoop();
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
    disconnectedCallback() { this._stopFlowLoop(); }

    _startFlowLoop() {
      this._stopFlowLoop();
      const loop = () => {
        if (this._activeTab === 'main') this._drawPowerflow();
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
      const pvSig = PV_FORECAST_DAYS.map((_l, i) => String(this._pvDayKwh(i))).join('|');
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
            ${pvVal !== null ? `<div class="pv">${pvVal.toFixed(1)} kWh</div>` : ''}
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

      const key = JSON.stringify({ d: days, c: confidence, m: mape, h: historyDays, p: profileDays });
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
        if (historyDays > 0) parts.push(`<span class="stat">Historia: <b>${historyDays} dni</b></span>`);
        if (profileDays >= 3) parts.push(`<span class="stat">Profil godzinowy: <b>${profileDays} dni</b></span>`);
        else if (profileDays > 0) parts.push(`<span class="stat" style="color:#fbbf24">Profil: ${profileDays}/3 dni</span>`);
        footer.innerHTML = parts.join('') || '<span class="stat">Zbieram historię...</span>';
      }

      this._drawLoadConsumptionChart(canvas, days, confidence);
      this._safe(() => this._renderLoadHistTable(st.attributes.history_14d, st.attributes.forecast_bias));
    }

    _renderLoadHistTable(rows, bias) {
      const box = this._el('loadHistTable'); if (!box) return;
      if (!Array.isArray(rows) || !rows.length) { box.innerHTML = '<div class="lh-note">Brak historii prognoz (zbieram dane).</div>'; return; }
      const wd = ['pn', 'wt', 'śr', 'czw', 'pt', 'sob', 'nd'];
      const f1 = (v) => (typeof v === 'number' ? v.toFixed(1).replace('.', ',') : '—');
      let n = 0, sumAbs = 0, sumBias = 0, hit = 0;
      const body = rows.map(r => {
        const hasA = typeof r.actual === 'number';
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
        return `<tr><td title="${r.holiday || ''}">${dayTxt}</td><td class="num">${f1(r.actual)}</td><td class="num ${retro ? 'lh-retro' : ''}">${f1(fc)}${retro ? '*' : ''}</td><td class="num ${cls}">${diff}</td><td class="num lh-dim">${typeof r.temp === 'number' ? r.temp.toFixed(0) + '°' : ''}</td></tr>`;
      }).join('');
      const sum = n ? `<div class="lh-sum"><span>Średni błąd: <b>${f1(sumAbs / n)} kWh</b></span><span>Obciążenie: <b>${sumBias / n > 0 ? '+' : ''}${f1(sumBias / n)} kWh</b> ${sumBias / n > 0.5 ? '(model zawyża)' : sumBias / n < -0.5 ? '(model zaniża)' : ''}</span><span>Trafione ±20%: <b>${hit}/${n}</b></span></div>` : '';
      box.innerHTML = `${sum}<table class="lh-tbl"><thead><tr><th>Dzień</th><th class="num">Rzeczywiste</th><th class="num">Prognoza</th><th class="num">Różnica</th><th class="num">Temp.</th></tr></thead><tbody>${body}</tbody></table><div class="lh-note">Prognoza = wydana dzień wcześniej. * = brak zapisanej prognozy z tamtego dnia, pokazano model liczony wstecz (nie wlicza się do podsumowania). 🎌 = święto.${typeof bias === 'number' && Math.abs(bias - 1) >= 0.02 ? ` Korekta obciążenia modelu: <b>×${bias.toFixed(2).replace('.', ',')}</b> (z ostatnich 14 dni).` : ''}</div>`;
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

      days.forEach((d, i) => {
        const cx = padL + (i + 0.5) * slotW;
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

      forecast7d.forEach((d, i) => {
        const cx = padL + (i + 0.5) * slotW;
        const dateStr = d.date || '';
        const isTomorrow = dateStr === tomorrow;

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
      const padL = 46, padR = 12, padT = 18, padB = 22;     // padL/padR takie same jak w tabeli pod wykresem
      const plotW = w - padL - padR;
      const plotH = h - padT - padB;
      const baseY = padT + plotH;
      const groupW = plotW / 24;

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
    _renderPvProductionChart() {
      const canvas = this._el('chartPvProd24h');
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

    _drawPvProductionChart(canvas, actual, forecast) {
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
          if (i === nowH) {
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

    // tabela 2 × 12 godzin (dziś / jutro); wartości w zł/kWh, null = brak ceny
    _priceTableHtml(today, tomorrow, title, src) {
      const vals = (a) => (a || []).filter(v => v !== null);
      const mm = (a) => { const v = vals(a); return v.length ? [Math.max(...v), Math.min(...v)] : [null, null]; };
      const [maxD, minD] = mm(today), [maxJ, minJ] = mm(tomorrow);
      const fmt = (val, max, min) => {
        if (val === null || val === undefined) return '--';
        const str = val.toFixed(2);
        if (val === max) return `<span class="price-max">${str}</span>`;
        if (val === min) return `<span class="price-min">${str}</span>`;
        return str;
      };
      const at = (a, i) => (a && i < a.length) ? a[i] : null;
      const nowHour = new Date().getHours();
      let html = title ? `<div class="price-header" style="margin-top:8px;">${this._esc(title)}${src ? ` <span style="opacity:.6;font-size:11px;">(${this._esc(src)})</span>` : ''}</div>` : '';
      html += `<table class="price-table">
        <tr><th>Godz.</th><th>Dziś</th><th>Jutro</th><th width="10"></th>
            <th>Godz.</th><th>Dziś</th><th>Jutro</th></tr>`;
      for (let i = 0; i < 12; i++) {
        const h1 = `${String(i).padStart(2, '0')}-${String(i + 1).padStart(2, '0')}`;
        const h2 = `${String(i + 12).padStart(2, '0')}-${String((i + 13) % 24).padStart(2, '0')}`;
        const rc1 = i === nowHour ? ' class="price-now-hour"' : '';
        const rc2 = (i + 12) === nowHour ? ' class="price-now-hour"' : '';
        html += `<tr>
          <td${rc1}><b>${h1}</b></td><td${rc1}>${fmt(at(today, i), maxD, minD)}</td><td${rc1}>${fmt(at(tomorrow, i), maxJ, minJ)}</td>
          <td></td>
          <td${rc2}><b>${h2}</b></td><td${rc2}>${fmt(at(today, i + 12), maxD, minD)}</td><td${rc2}>${fmt(at(tomorrow, i + 12), maxJ, minJ)}</td>
        </tr>`;
      }
      return html + `</table>`;
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
        const cur = num(Number(a.price_sell));
        header.textContent = `Ceny sprzedaży > Teraz: ${cur === null ? '--' : cur.toFixed(2)} PLN/kWh`;
        const key = JSON.stringify([sT, sJ, bT, bJ, a.price_sell_source, a.price_buy_source, new Date().getHours()]);
        if (this._lastPriceTableKey === key) return;
        this._lastPriceTableKey = key;
        let html = this._priceTableHtml(sT, sJ, '', '');
        if (bT || bJ) html += this._priceTableHtml(bT, bJ, 'Ceny zakupu (taryfa dynamiczna)', a.price_buy_source || a.price_buy_entity || '');
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
      if (root && root.activeElement && body.contains(root.activeElement) && root.activeElement.tagName === 'INPUT') return;

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
        ['min_sell_margin', 'Min. marża sprzedaży (PLN/kWh)', 0.01],
        ['cycle_efficiency', 'Sprawność cyklu baterii (%)', 1],
        ['reserve_floor_soc', 'Rezerwa SOC — minimum (%)', 1],
        ['auto_apply_max_shift_h', 'Auto-stosowanie: maks. przesunięcie (h, 0 = bez limitu)', 1],
      ];

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

      const toggle = (eid, label, state) => {
        const on = state === 'on';
        const dis = state === 'unavailable' || state === 'unknown';
        return `<button class="btn${on ? ' active' : ''}" data-switch="${this._esc(eid)}" ${dis ? 'disabled' : ''}
          style="padding:10px 12px;flex-direction:row;gap:8px;justify-content:flex-start;text-align:left;">
          <span>${on ? '✅' : '⬜'}</span><span class="label" style="font-size:12px;">${this._esc(label)}</span></button>`;
      };
      const featureBtns = FEATURES.map(f => toggle(this._eid('switch', f[0]), f[1], swState(f[0]))).join('');
      const dayBtns = DAYS.map(d => {
        const on = swState(d[0]) === 'on';
        return `<button class="btn${on ? ' active' : ''}" data-switch="${this._esc(this._eid('switch', d[0]))}"
          style="padding:8px 0;min-width:44px;flex:1;"><span class="label">${d[1]}</span></button>`;
      }).join('');
      const numInputs = NUMS.map(n => `
        <label style="display:flex;justify-content:space-between;align-items:center;gap:10px;font-size:12px;color:#c7c7cc;padding:4px 0;">
          <span>${this._esc(n[1])}</span>
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

      body.innerHTML = `
        <div class="section" style="margin-top:6px;">
          <div class="section-title">💰 Bilans w PLN</div>
          <div class="chart-card full" style="padding:14px 16px;">${tiles}${bars}</div>
        </div>
        <div class="section">
          <div class="section-title">💡 Oszczędności</div>
          <div class="chart-card full" style="padding:14px 16px;"><div id="exSavBox"><div class="chart-empty">Ładowanie…</div></div></div>
        </div>
        <div class="section">
          <div class="section-title">🎯 Trafność prognoz</div>
          <div class="chart-card full" style="padding:14px 16px;"><div id="exAccBox"><div class="chart-empty">Ładowanie…</div></div></div>
        </div>
        <div class="section">
          <div class="section-title">📅 Raport miesięczny</div>
          <div class="chart-card full" style="padding:14px 16px;"><div id="exReportBox"><div class="chart-empty">Ładowanie…</div></div></div>
        </div>
        <div class="section">
          <div class="section-title">🔋 Zdrowie i sprawność baterii</div>
          <div class="chart-card full" style="padding:14px 16px;"><div id="exHealthBox"><div class="chart-empty">Ładowanie…</div></div></div>
        </div>
        <div class="section">
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
        <div class="section">
          <div class="section-title">📋 Dziennik decyzji (ostatnie ${entries.length})</div>
          <div class="chart-card full" style="padding:8px 16px;max-height:520px;overflow-y:auto;">${rows}</div>
        </div>`;
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
      if (persist) { try { localStorage.setItem(THEME_KEY, mode); } catch (e) { /* ignoruj */ } }
      this._applyTheme(mode);
    }
    _applyTheme(force) {
      const mode = force || this._resolveTheme();
      const changed = THEME.mode !== mode || this.getAttribute('data-theme') !== mode;
      THEME.mode = mode;
      this.setAttribute('data-theme', mode);
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
        if (this._activeTab === 'charts') {
          this._renderLoadConsumptionChart(); this._renderForecast7dChart();
          this._renderHourlyForecastChart(); this._renderPvProductionChart(); this._renderPriceTable();
          if (this._historyData) this._renderHistoryChart();
        }
        if (this._activeTab === 'log') this._renderLogTab();
      });
    }

    _renderShell() {
      const style = document.createElement('style');
      style.textContent = STYLES;
      this.shadowRoot.appendChild(style);

      const wrap = document.createElement('div');
      wrap.className = 'app';
      wrap.innerHTML = `
        <div class="header">
          <div>
            <div class="title">Centrum Energii</div>
            <div class="date" id="date"></div>
          </div>
          <div class="theme-seg" role="group" aria-label="Motyw">
            <button type="button" data-theme-set="light" title="Jasny" aria-label="Motyw jasny">☀️</button>
            <button type="button" data-theme-set="dark" title="Ciemny" aria-label="Motyw ciemny">🌙</button>
          </div>
        </div>
        <nav class="tabs">
          <button class="tab active" data-tab="main">🏠 Główny</button>
          <button class="tab" data-tab="charts">📊 Wykresy</button>
          <button class="tab" data-tab="ems">🎛️ EMS</button>
          <button class="tab" data-tab="log">💰 Zysk i log</button>
          <button class="tab" data-tab="dev">🔌 Urządzenia</button>
          <button class="tab" data-tab="diag" id="tabDiag" style="display:none;">🛠️ Diagnostyka</button>
        </nav>

        <div class="price-bar" id="priceBar" style="display:none;"></div>
        <div class="floor-alert" id="floorAlert" style="display:none;"></div>
        <div class="status-banner" id="statusBanner" style="display:none;"></div>

        <!-- Pogoda na samej górze -->
        <div class="weather-global">
          <div class="section-title">Pogoda i prognoza PV (7 dni)</div>
          <div class="weather-scroll" id="weatherContainer"></div>
        </div>

        <div class="tab-content" data-tab-content="main">
          <!-- Aktywne funkcje przeniesione pod pogodę -->
          <div class="section" style="margin-top:6px;">
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
          </div>

          <!-- Przepływ mocy (węzły) -->
          <div class="section" style="margin-top:6px;">
            <div class="chart-card full nodes-card"><div id="nodesBox"></div><div id="nodePop" class="node-pop" hidden></div></div>
          </div>
          <div class="section">
            <div class="section-title">Plan dnia</div>
            <div class="eta-grid" id="etaBox" style="margin-bottom:10px;"></div>
            <div class="chart-card full" style="padding:6px 20px 12px;"><div id="planBox"></div></div>
          </div>
        </div>

        <div class="tab-content" data-tab-content="charts" style="display:none;">
          
          <div class="section" style="margin-top:6px;">
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

          <div class="section">
            <div class="section-title">Zużycie domu — wczoraj / dziś / jutro</div>
            <div class="chart-card full">
              <div class="chart-head"><span>🏠 Porównanie</span><span class="sub" id="loadConsSub">—</span></div>
              <canvas id="chartLoadCons"></canvas>
              <div class="chart-footer" style="border-top:0;margin-top:2px;padding-top:2px;"><span class="stat"><i class="dot" style="background:#34d399"></i>rzeczywiste</span><span class="stat"><i class="dot" style="background:#60a5fa"></i>prognoza wydana dzień wcześniej</span><span class="stat"><i class="dot" style="background:#ff9f0a"></i>tempo dnia (szacunek na koniec doby)</span><span class="stat"><i class="dot" style="background:#fbbf24"></i>jutro — prognoza i zakres</span></div>
              <div class="chart-footer" id="loadConsFooter"></div>
              <details class="lh-wrap" open><summary>Ostatnie 14 dni: rzeczywiste vs prognoza</summary><div id="loadHistTable"></div></details>
            </div>
          </div>
          <div class="section">
            <div class="section-title">Prognoza 7-dniowa zużycia domu</div>
            <div class="chart-card full">
              <div class="chart-head"><span>📅 Najbliższe 7 dni</span><span class="sub">kWh / dzień</span></div>
              <canvas id="chartForecast7d"></canvas>
              <div class="chart-footer" style="border-top:0;margin-top:2px;padding-top:2px;"><span class="stat"><i class="dot" style="background:#60a5fa"></i>prognoza dnia</span><span class="stat"><i class="dot" style="background:#fbbf24"></i>dziś / jutro</span></div>
            </div>
          </div>
          <div class="section">
            <div class="section-title">Profil godzinowy dziś</div>
            <div class="chart-card full">
              <div class="chart-head"><span>⏰ Prognoza godzinowa — dziś</span><span class="sub" id="hourlyTodaySub">—</span></div>
              <canvas id="chartHourlyToday"></canvas>
              <div class="chart-footer" style="border-top:0;margin-top:2px;padding-top:2px;"><span class="stat"><i class="dot" style="background:#60a5fa"></i>prognoza na dziś (kWh na godzinę)</span><span class="stat"><i class="dot" style="background:#fbbf24"></i>szczyt (≥ 70% maksimum)</span><span class="stat" id="hfcLegActual"><i class="dot" style="width:14px;height:3px;border-radius:2px;background:var(--hfc-today)"></i>rzeczywiste zużycie</span></div>
              <div id="hourlyTodayTable" class="hfc-wrap" role="group" aria-label="Tabela godzin dziś: prognoza i zużycie w Wh"></div>
            </div>
          </div>
          <div class="section">
            <div class="section-title">Profil godzinowy jutra</div>
            <div class="chart-card full">
              <div class="chart-head"><span>⏰ Prognoza godzinowa — jutro</span><span class="sub" id="hourlyFcSub">—</span></div>
              <canvas id="chartHourlyFc"></canvas>
              <div class="chart-footer" style="border-top:0;margin-top:2px;padding-top:2px;"><span class="stat"><i class="dot" style="background:#60a5fa"></i>jutro — prognoza (kWh na godzinę)</span><span class="stat"><i class="dot" style="background:#fbbf24"></i>szczyt (≥ 70% maksimum)</span></div>
              <div id="hourlyFcTable" class="hfc-wrap" role="group" aria-label="Tabela godzin jutro: prognoza w Wh"></div>
            </div>
          </div>
          <div class="section">
            <div class="section-title">Produkcja PV dziś — rzeczywista vs prognoza (kWh/h)</div>
            <div class="chart-card full">
              <div class="chart-head"><span>☀️ Produkcja PV</span><span class="sub" id="pvProdSub">—</span></div>
              <canvas id="chartPvProd24h"></canvas>
            </div>
          </div>
          <div class="section">
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

        <div class="tab-content" data-tab-content="diag" style="display:none;"><div id="diagRoot"></div></div>
        <div class="tab-content" data-tab-content="dev" style="display:none;"><div id="devRoot"></div></div>

        <div class="tab-content" data-tab-content="ems" style="display:none;">
          <div class="section" style="margin-top:6px;">
            <div class="section-title">📈 Plan na najbliższe 24 h</div>
            <div class="chart-card full" style="padding:14px 16px;"><div id="exPlanBox"><div class="chart-empty">Ładowanie planu…</div></div></div>
          </div>

          <div class="section">
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

          <div class="section">
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
          </div>

          <div class="section">
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

          <div class="section">
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

          <div class="section">
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
          if (tab === 'log') { this._lastLogKey = null; this._safe(() => this._renderLogTab()); }
          wrap.querySelectorAll('.tab').forEach(b => b.classList.toggle('active', b === btn));
          wrap.querySelectorAll('.tab-content').forEach(c => c.style.display = c.dataset.tabContent === tab ? '' : 'none');
          
          if (tab === 'main') this._startFlowLoop();
          else this._stopFlowLoop();
          if (tab === 'diag') this._safe(() => this._dgOpen());
          else if (this._dg) this._dgDestroyChart();
          if (tab === 'ems' || tab === 'diag') this._safe(() => this._exEnsure());
          if (tab === 'dev') this._safe(() => this._devEnsure());

          if (tab === 'charts') {
            this._lastLoadConsKey = null;
            this._lastForecast7dKey = null;
            this._lastHourlyFcKey = null;
            this._lastPvProdKey = null;
            this._lastPriceTableKey = null;
            if (!this._history24h) this._fetchHistory24h();
            if (!this._historyData) this._fetchHistoryData(this._historyRange);
            setTimeout(() => {
              this._renderLoadConsumptionChart();
              this._renderForecast7dChart();
              this._renderHourlyForecastChart();
              this._renderPvProductionChart();
              this._renderPriceTable();
              this._renderHistoryChart();
            }, 100);
          }
        });
      });

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
      let nChange = 0, nSkip = 0, nSame = 0;
      let cards = '';
      groups.forEach(g => {
        const its = g.items;
        const allSkip = its.every(([, p]) => p.skip);
        const changed = !allSkip && its.some(([, p]) => !p.skip && p.proposed && p.proposed !== p.current);
        const verdict = allSkip ? 'skip' : (changed ? 'change' : 'same');
        if (verdict === 'skip') nSkip++; else if (verdict === 'change') nChange++; else nSame++;
        const conf = (its.find(([, p]) => !p.skip) || its[0])[1].confidence;
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
        cards += `<label class="sg sg-${verdict}">
          <input type="checkbox" ${attrs} ${canApply ? 'checked' : 'disabled'}>
          <div class="sg-body">
            <div class="sg-head"><span class="sg-title">${g.icon} ${esc(g.title)}</span>
              <span class="sg-badges"><span class="sg-badge" style="background:${badge[1]}22;color:${badge[1]};">${badge[0]}</span>${verdict !== 'skip' ? `<span class="sg-badge" style="background:${confColor}22;color:${confColor};">${esc(conf || '?')}</span>` : ''}</span></div>
            ${rows ? `<div class="sg-vals">${rows}</div>` : ''}
            <div class="sg-why"><span>${verdict === 'skip' ? 'Dlaczego pomijam' : 'Dlaczego tak'}</span>${why || '—'}</div>
          </div>
        </label>`;
      });

      const head = `<div class="sg-sum"><div class="sg-sum-h">Na czym oparłem decyzje (stan z ${at})</div>
        <div class="sg-sum-t">${facts.join(' · ')}</div>
        <div class="sg-sum-r">Wynik: <b>zmieniam ${nChange}</b>, bez zmian ${nSame}, pomijam ${nSkip}.${has(data.rce_tomorrow_avg) ? '' : ' Bez cen RCE na jutro nie planuję sprzedaży na jutro.'}</div></div>`;

      el.innerHTML = head + `<div class="sg-list">${cards}</div>
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
        cheap = a.cheap_now ? ` Trwa tanie okno do ${hm(a.cheap_end)}:00.` : ` Najbliższe tanie okno: ${day} ${hm(a.cheap_start)}–${hm(a.cheap_end)}.`;
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
      const f = (v) => v === null ? '—' : v.toFixed(2);
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
      this._safe(() => this._renderStatusBanner());
      this._safe(() => this._exRender());
      this._safe(() => this._renderWeather());
      this._safe(() => this._renderLoadConsumptionChart());
      this._safe(() => this._renderForecast7dChart());
      this._safe(() => this._renderHourlyForecastChart());
      this._safe(() => this._renderPvProductionChart());
      this._safe(() => this._renderPriceTable());
      this._safe(() => this._renderPlan());
      this._safe(() => this._renderEta());
      this._safe(() => this._dgSyncTab());
      if (this._activeTab === 'diag') this._safe(() => this._dgTick());
      if (this._activeTab === 'dev') this._safe(() => this._devTick());
      if (this._activeTab === 'log') this._safe(() => this._renderLogTab());

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

      if (this._activeTab === 'main') this._drawPowerflow();
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
    _fx(v, d = 1) { return v === null ? null : v.toFixed(d).replace('.', ',').replace('-', '−'); }

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

    _drawPowerflow() {
      if (!this.isConnected || this._activeTab !== 'main') return;
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
      const k1 = (v) => (v === null ? '—' : v.toFixed(1));
      const dayTxt = {
        pv: D.pv === null ? '' : `dziś ${k1(D.pv)} kWh`,
        home: D.load === null ? '' : `dziś ${k1(D.load)} kWh`,
        grid: (D.imp === null && D.exp === null) ? '' : `dziś ↓${k1(D.imp)} ↑${k1(D.exp)} kWh`,
        batt: (D.chg === null && D.dis === null) ? '' : `dziś ↓${k1(D.chg)} ↑${k1(D.dis)} kWh`,
      };

      const cw = box.clientWidth || 0;
      const V = this._flowVariant || (cw > 0 && cw < 520 ? 'A' : '0');                    // '0' = bez zmian; A = przycięcie, B = większe, C = oba (telefon)
      const big = V === 'B' || V === 'C', crop = V === 'A' || V === 'C';
      const lh = big ? 20 : 16;
      const key = [V, Math.round(pv / 10), Math.round(load / 10), Math.round(grid / 10), Math.round(batt / 10), Math.round(soc), THEME.mode, Object.values(D).map(v => v === null ? 'x' : v.toFixed(1)).join(',')].join('|');
      if (key === this._lastFlowKey) return;     // animacja jest w CSS — przerysowujemy tylko przy zmianie
      this._lastFlowKey = key;

      const TH = 20;                                         // poniżej 20 W traktujemy jako brak przepływu
      const H = { x: 300, y: big ? 165 : 150 };
      const dx = V === 'C' ? 28 : 0;
      const N = { pv: { x: 300, y: 45 }, home: { x: 115 + dx, y: H.y }, grid: { x: 485 - dx, y: H.y }, batt: { x: 300, y: big ? 308 : 268 } };
      const R = big ? { pv: 38, home: 38, grid: 38, batt: 52 } : { pv: 32, home: 32, grid: 32, batt: 44 };
      const vb = (crop ? (V === 'C' ? '52 0 496 ' : '45 0 510 ') : '0 0 600 ') + (big ? 400 : 340);
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
        const a = cl(n, H, R[f.k] + 4), b = cl(H, n, 12);
        const p = f.dir >= 0 ? `M${a.x.toFixed(1)} ${a.y.toFixed(1)} L${b.x.toFixed(1)} ${b.y.toFixed(1)}`
                             : `M${b.x.toFixed(1)} ${b.y.toFixed(1)} L${a.x.toFixed(1)} ${a.y.toFixed(1)}`;
        const sw = f.dir === 0 ? 2 : Math.min(7, 3 + f.w / 1500);
        lines += f.dir === 0
          ? `<path d="${p}" class="nf-idle"/>`
          : `<path d="${p}" class="nf-line" stroke="${f.c}" stroke-width="${sw.toFixed(1)}"/>`;
      });

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
        <rect class="nf-hit" data-k="pv" x="${N.pv.x - 60}" y="${N.pv.y - R.pv - 2}" width="120" height="${R.pv * 2 + 4 + 40}"/>
        <rect class="nf-hit" data-k="home" x="${N.home.x - 60}" y="${N.home.y - R.home - 2}" width="120" height="${R.home * 2 + 4 + 40}"/>
        <rect class="nf-hit" data-k="grid" x="${N.grid.x - 60}" y="${N.grid.y - R.grid - 2}" width="120" height="${R.grid * 2 + 4 + 40}"/>
        <rect class="nf-hit" data-k="batt" x="${N.batt.x - R.batt - 2}" y="${N.batt.y - R.batt - 2}" width="${R.batt * 2 + 4 + 150}" height="${R.batt * 2 + 4}"/>
      </svg>`;
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
      pop.addEventListener('click', e => { if (e.target.closest('.np-x')) this._hidePop(); });
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
        pop.hidden = true; pop.classList.remove('pin');
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
      const hit = this.shadowRoot.querySelector(`.nf-hit[data-k="${this._popK}"]`);
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
          const arr = a[k], day = a.pv_daily[off];
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

    _renderEta() {
      const box = this._el('etaBox');
      if (!box) return;
      const soc = this._num('soc');
      const battRaw = this._num('battery_power');
      const batt = INVERT_BATTERY_SIGN ? -battRaw : battRaw;     // >0 ładowanie, <0 rozładowanie
      const load = Math.max(0, this._num('load_power'));
      const rs = this._hass.states[this._eid('sensor', 'reserve_soc')];
      let cap = rs && rs.attributes ? parseFloat(rs.attributes.capacity_kwh) : NaN;
      // próg odcięcia: z falownika (SOC wyłączenia + aktywny program ToU, albo wpisany ręcznie) — integracja wystawia go w atrybutach;
      // bez niego (starszy backend, brak encji falownika) przyjmujemy 20% i mówimy o tym w opisie
      const ra = (rs && rs.attributes) || {};
      const flNow = Number(ra.inverter_floor);
      const flHourly = Array.isArray(ra.inverter_floor_hourly) && ra.inverter_floor_hourly.length === 24 ? ra.inverter_floor_hourly.map(Number) : null;
      const fromInv = isFinite(flNow) && flNow > 0 && flNow < 100;
      const FLOOR = fromInv ? flNow : 20;
      const floorFn = fromInv && flHourly && flHourly.every(x => isFinite(x) && x >= 0 && x < 100) ? (h => flHourly[h]) : FLOOR;
      const floorTxt = fromInv ? `${Math.round(FLOOR * 10) / 10}%` : `${FLOOR}% (domyślnie)`;
      const floorTip = fromInv ? `Próg odcięcia z falownika${ra.inverter_floor_source ? ': ' + ra.inverter_floor_source : ''}` : 'Brak progu z falownika — przyjęto 20%';
      let manual = false;
      if (!(cap > 0)) {                                   // integracja nie podała pojemności — użyj wpisanej ręcznie
        try { cap = parseFloat(localStorage.getItem('bms_panel_capacity')); } catch (e) { cap = NaN; }
        manual = cap > 0;
      }
      const needCap = !(cap > 0);
      let full = { v: '—', s: 'brak pojemności baterii' };
      let low = { v: '—', s: full.s };
      if (cap > 0) {
        const lf = this._hass.states[this._eid('sensor', 'load_forecast')] || this._hass.states['sensor.bms_load_forecast'];
        const hl = lf && lf.attributes && Array.isArray(lf.attributes.hourly_forecast) && lf.attributes.hourly_forecast.length === 24
          ? lf.attributes.hourly_forecast.map(Number) : null;
        const pvMap = this._pvHourlyMap();
        const havePv = Object.keys(pvMap).length > 0;
        // --- do pełna
        if (soc >= 99.5) full = { v: 'Pełna', s: 'bateria naładowana' };
        else if (batt > 20) {
          const h = (100 - soc) / 100 * cap / (batt / 1000);
          full = { v: this._fmtDur(h), s: `ok. ${this._fmtAt(h)} · ładowanie ${this._fmtW(batt)}` };
        } else {
          const h = havePv ? this._simulateSoc(soc, cap, 100, true, hl, pvMap) : null;
          full = h != null
            ? { v: this._fmtDur(h), s: `ok. ${this._fmtAt(h)} · wg prognozy PV i zużycia` }
            : { v: 'nie w 2 dni', s: havePv ? 'prognoza PV nie wystarczy do pełnego naładowania' : 'brak prognozy PV' };
        }
        // --- do 20%
        if (soc <= FLOOR) low = { v: `≤ ${Math.round(FLOOR * 10) / 10}%`, s: 'poziom już osiągnięty' };
        else {
          const discharging = batt < -20;
          let basis = '';
          // wynik główny: przy obecnym poborze (rozładowanie, a gdy bateria się ładuje — zużycie domu bez PV)
          const rate = discharging ? -batt : Math.max(load, 100);
          const hNow = (soc - FLOOR) / 100 * cap / (rate / 1000);
          basis = discharging ? `przy obecnym rozładowaniu ${this._fmtW(rate)}` : `przy obecnym zużyciu domu ${this._fmtW(rate)} (bez PV)`;
          low = { v: this._fmtDur(hNow), s: `ok. ${this._fmtAt(hNow)} · ${basis}`, h: hNow };
          // w nocy: ile zostanie, zanim słońce pokryje zużycie domu (prognoza zużycia i PV)
          const sun = this._socAtSun(soc, cap, hl, pvMap, floorFn);
          if (sun) {
            const hhmm = (d) => d.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' });
            low.s2 = sun.floorAt
              ? `Przed słońcem (ok. ${hhmm(sun.at)}) dojdzie do ${Math.round(sun.floor)}% ok. ${hhmm(sun.floorAt)}`
              : `Do słońca (ok. ${hhmm(sun.at)}) zostanie ok. ${Math.round(sun.soc)}%`;
          }
        }
      }
      // ---- jedna kafelka „Bateria”: treść zależy od stanu (naładowana / ładuje się / zaplanowane ładowanie z sieci / rozładowanie)
      const plan = this._plannedGridCharge();
      const socTxt = `${Math.round(soc)}%`;
      const lowLine = low.v === '—' ? '' : `Do ${floorTxt}: ${low.v} · ${low.s}`;
      const hCh = cap > 0 && batt > 20 && soc < 99.5 ? (100 - soc) / 100 * cap / (batt / 1000) : null;
      let st;
      if (cap > 0 && soc >= 99.5) {
        st = { l: '🔋 Bateria · naładowana', c: 'var(--green)', v: low.v.startsWith('>') ? 'wystarczy na ponad 2 dni' : `wystarczy na ${low.v}`, s: low.s, s2: low.s2 };
      } else if (hCh !== null) {
        st = { l: '⚡ Bateria · ładuje się', c: 'var(--green)', v: `pełna ok. ${this._fmtAt(hCh)}`,
               s: `${socTxt} → 100% · ładowanie ${this._fmtW(batt)} · jeszcze ${this._fmtDur(hCh)}`, s2: [lowLine, low.s2].filter(Boolean).join('<br>') };
      } else if (plan && !plan.none) {
        const warnEarly = !plan.active && low.h != null && low.h < plan.hStart;
        const parts = [];
        if (warnEarly) parts.push(`Uwaga: bateria dojdzie do ${floorTxt} ok. ${this._fmtAt(low.h)}, przed startem ładowania.`);
        else if (lowLine) parts.push(lowLine);
        if (low.s2) parts.push(low.s2);
        st = plan.active
          ? { l: '🔌 Bateria · ładowanie z sieci', c: 'var(--accent)', v: `okno do ${plan.endTxt}`, s: `plan ładowania z sieci trwa ${plan.startTxt}–${plan.endTxt} · bateria ${socTxt}` }
          : { l: '🔌 Bateria · ładowanie z sieci', c: warnEarly ? 'var(--orange)' : 'var(--accent)', v: `start ${this._fmtAt(plan.hStart)}`,
              s: `plan ${plan.startTxt}–${plan.endTxt} · za ${this._fmtDur(plan.hStart)} · teraz ${socTxt}` };
        st.s2 = parts.join('<br>');
      } else if (cap > 0) {
        const atFloor = soc <= FLOOR;
        const parts = [];
        if (low.s2) parts.push(low.s2);
        if (plan && plan.none && !atFloor) parts.push('Brak zaplanowanego ładowania z sieci.');
        st = { l: `⏳ Do rozładowania do ${floorTxt}`, c: atFloor ? 'var(--red)' : 'var(--orange)', v: low.v, s: low.s, s2: parts.join('<br>') };
      } else {
        st = { l: '🔋 Bateria', c: 'var(--muted)', v: '—', s: 'brak pojemności baterii', s2: '' };
      }
      const key = st.l + st.v + st.s + (st.s2 || '') + soc + st.c + floorTxt + THEME.mode + (needCap ? 'N' : manual ? 'M' + cap : '');
      if (key === this._lastEtaKey) return;
      this._lastEtaKey = key;
      const capUi = (needCap || manual)
        ? `<div class="e-cap" style="grid-column:1/-1;font-size:12px;color:var(--muted);display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
             <span>${needCap ? 'Integracja nie podała pojemności baterii (zaktualizuj sensor.py). Wpisz ją ręcznie:' : 'Pojemność wpisana ręcznie:'}</span>
             <input type="number" id="capInput" min="1" max="200" step="0.1" value="${manual ? cap : ''}" placeholder="kWh" style="width:90px;"> <span>kWh</span></div>` : '';
      const socW = Math.max(0, Math.min(100, Number(soc) || 0));
      box.innerHTML = capUi + `<div class="eta" style="grid-column:1/-1"><div class="e-l" title="${this._esc(floorTip)}">${st.l}</div><div class="e-v" style="color:${st.c}">${st.v}</div><div class="e-s">${st.s}</div>`
        + `<div style="height:6px;border-radius:3px;background:var(--line);margin-top:8px;overflow:hidden"><div style="height:100%;width:${socW}%;background:${st.c}"></div></div>`
        + `${st.s2 ? `<div class="e-s" style="margin-top:6px;opacity:.75">${st.s2}</div>` : ''}</div>`;
      const inp = box.querySelector('#capInput');
      if (inp) inp.addEventListener('change', () => {
        const v = parseFloat(String(inp.value).replace(',', '.'));
        try { if (v > 0) localStorage.setItem('bms_panel_capacity', String(v)); else localStorage.removeItem('bms_panel_capacity'); } catch (e) { /* ignoruj */ }
        this._lastEtaKey = null;
        this._renderEta();
      });
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
        return `<div class="pl-row"><div class="pl-h"><span>${icon} ${label}</span><b>${val.toFixed(1)}${max > 0 ? ' / ' + max.toFixed(1) : ''} ${unit}</b></div>
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
          return `<div class="pl-row"><div class="pl-h"><span>☀️ Moc PV teraz</span><b>${pvKw.toFixed(1)} kW${fcNow != null ? ` <small style="color:var(--muted);font-weight:500;">· prognoza ${fcNow.toFixed(1)} kW</small>` : ''}</b></div>
            <div class="pl-bar" style="position:relative;overflow:visible;"><div style="width:${pct.toFixed(0)}%;background:#ffcc00;"></div>${mark != null ? `<span title="prognoza PV na tę godzinę" style="position:absolute;top:-2px;bottom:-2px;left:${mark.toFixed(1)}%;width:2px;background:var(--text);"></span>` : ''}</div>
            <div class="pl-n" style="display:flex;justify-content:space-between;"><span>0 — ${scale} kW</span><span>${rel}</span></div></div>`;
        })() +
        (() => {
          const socNow = Math.max(0, Math.min(100, this._num('soc')));
          const unit = capK > 0 ? capK : 0;
          const kwhNow = unit * socNow / 100;
          const rsA = (this._hass.states[this._eid('sensor', 'reserve_soc')] || {}).attributes || {};
          const flr = Number(rsA.inverter_floor); const hasFl = isFinite(flr) && flr > 0 && flr < 100;
          const note = `dziś naładowano ${ch.toFixed(1)} kWh · oddano ${dis.toFixed(1)} kWh`;
          const flNote = hasFl ? ` · próg odcięcia falownika ${Math.round(flr)}%${unit > 0 ? ` (dostępne ~${Math.max(0, unit * (socNow - flr) / 100).toFixed(1)} kWh)` : ''}` : '';
          return `<div class="pl-row"><div class="pl-h"><span>🔋 W baterii teraz</span><b>${unit > 0 ? kwhNow.toFixed(1) + ' kWh · ' : ''}${socNow.toFixed(0)}%</b></div>
            <div class="pl-bar" style="position:relative;overflow:visible;"><div style="width:${socNow.toFixed(0)}%;background:#34c759;"></div>${hasFl ? `<span title="próg odcięcia falownika ${Math.round(flr)}%" style="position:absolute;top:-2px;bottom:-2px;left:${flr.toFixed(1)}%;width:2px;background:var(--red);"></span>` : ''}</div>
            <div class="pl-n">${unit > 0 ? '0 — ' + unit.toFixed(1) + ' kWh · ' : ''}${note}${flNote}</div></div>`;
        })() +
        row('🔌', 'Sieć: eksport względem importu', exp, Math.max(exp, imp), 'kWh', '#af52de', `import ${imp.toFixed(1)} kWh` + (selfSuff != null ? ` · samowystarczalność ${Math.round(selfSuff)}%` : ''));
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
  const CARD_VERSION = '0.8.8';
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

  // Zaślepki: działają do czasu załadowania modułu, potem moduł nadpisuje je pełnymi wersjami.
  const DG_STUBS = {
    _dgIsAdmin() { const u = this._hass && this._hass.user; return !!(u && u.is_admin); },
    _dgSyncTab() {
      const b = this._el('tabDiag');
      if (b) {
        b.style.display = this._dgIsAdmin() ? '' : 'none';
        // alarm z integracji widać na zakładce, zanim załaduje się moduł Diagnostyki
        const ms = this._hass && this._hass.states[this._eid('sensor', 'monitor_status')];
        const be = ms && ms.attributes && Array.isArray(ms.attributes.alarms) ? ms.attributes.alarms.length : 0;
        const want = '🛠️ Diagnostyka' + (be ? ' ⚠' : '');
        if (b.textContent !== want) b.textContent = want;
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
  const EX_BOXES = ['exPlanBox', 'exWizBox', 'exReportBox', 'exHealthBox', 'exSavBox', 'exAccBox'];
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

  if (!customElements.get('bms-panel-card')) {
    try { customElements.define('bms-panel-card', BmsPanel); }
    catch (e) { console.error('EMS PANEL: define failed', e); }
  }
  window.customCards = window.customCards || [];
  if (!window.customCards.some(c => c && c.type === 'bms-panel-card')) {
    window.customCards.push({ type: 'bms-panel-card', name: 'Centrum Energii', description: 'EMS Panel', preview: true });
  }
})();