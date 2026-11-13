/**
 * EMS Centrum Energii — moduł Diagnostyki
 * Ładowany na żądanie przez bms-panel.js (kontrakt modułu: 1). Nie dodawaj tego pliku do zasobów dashboardu ręcznie.
 */
(function () {
  'use strict';
  const install = function (BmsPanel, shared) {
    const TC = shared.TC;
    const BMS_INFO = { card: shared.version || '', url: shared.urlVersion || '' };
  // <<DIAG-BEGIN>>
  // =====================================================================
  //  ZAKŁADKA DIAGNOSTYKA (instalator): konfiguracja falownika, strefy
  //  czasowe, wykresy 1h–365d, alarmy, kopie/profile, dziennik, rejestry.
  //  Hasło to blokada przed przypadkową zmianą — realną barierą jest
  //  konto administratora HA (zakładka widoczna tylko dla adminów).
  // =====================================================================
  const DG_PW_SHA = '16e2f18f0de673c43007f0d722f1e82b8b29f574d590f2f479f61d56c958c71f';
  const DG_SALT = 'bms-komp-dec:';
  const DG_UNLOCK_MS = 15 * 60 * 1000;
  const DG_MEM = {};
  // Dziennik zmian, kopie, profile, prefiks, kontrole po zapisie i alarmy są przechowywane w Home Assistant
  // (usługi bms_komp_dec.diag_store_*), a nie tylko w localStorage jednej przeglądarki. localStorage zostaje
  // lokalnym buforem i źródłem jednorazowej migracji starych danych. DG_LS ma to samo, synchroniczne API co wcześniej.
  const DG_KEYMAP = { bms_diag_log: 'log', bms_diag_auto: 'auto', bms_diag_profiles: 'profiles', bms_diag_prefix: 'prefix', bms_diag_watch: 'watch', bms_diag_alarms: 'alarms' };
  const DG_ST = { ready: false, err: '', dirty: {}, timer: null, card: null, loadP: null, migrated: 0, retryAt: 0 };
  const DG_LS = {
    get(k, d) {
      if (k in DG_MEM) { try { return JSON.parse(DG_MEM[k]); } catch (e) { /* uszkodzone — spróbuj bufora */ } }
      try { const v = localStorage.getItem(k); if (v != null) return JSON.parse(v); } catch (e) { /* brak dostępu */ }
      return d;
    },
    set(k, v) {
      const j = JSON.stringify(v); DG_MEM[k] = j;
      try { localStorage.setItem(k, j); } catch (e) { /* tylko pamięć i HA */ }
      const hk = DG_KEYMAP[k]; if (hk) { DG_ST.dirty[hk] = v; dgStoreSchedule(600); }
      return true;
    },
  };
  const dgCall = (card, service, data, resp) => card._hass.callWS({ type: 'call_service', domain: 'bms_komp_dec', service, service_data: data || {}, return_response: !!resp });
  const dgErrText = (e) => String((e && (e.message || e.code)) || e || 'błąd').slice(0, 160);
  function dgStoreSchedule(ms) {
    if (DG_ST.timer) return;
    DG_ST.timer = setTimeout(() => { DG_ST.timer = null; dgStoreFlush(); }, ms);
  }
  async function dgStoreFlush() {
    const card = DG_ST.card;
    if (!card || !card._hass || !DG_ST.ready) return;            // przed wczytaniem zmiany czekają w „dirty”
    for (const hk of Object.keys(DG_ST.dirty)) {
      const val = DG_ST.dirty[hk];
      try { await dgCall(card, 'diag_store_set', { key: hk, value: val }); if (DG_ST.dirty[hk] === val) delete DG_ST.dirty[hk]; DG_ST.err = ''; }
      catch (e) { DG_ST.err = dgErrText(e); dgStoreSchedule(15000); break; }
    }
    if (card._dgStoreNoteRefresh) card._dgStoreNoteRefresh();
  }
  function dgStoreLoad(card) {
    DG_ST.card = card;
    if (DG_ST.ready) return Promise.resolve(true);
    if (DG_ST.loadP) return DG_ST.loadP;
    DG_ST.loadP = (async () => {
      try {
        const res = await dgCall(card, 'diag_store_get_all', {}, true);
        const data = (res && res.response && res.response.data) || {};
        for (const [lk, hk] of Object.entries(DG_KEYMAP)) {
          if (hk in DG_ST.dirty) continue;                          // zmienione lokalnie w trakcie wczytywania — wygrywa
          const rec = data[hk];
          if (rec && rec.value !== undefined && rec.value !== null) {
            const j = JSON.stringify(rec.value); DG_MEM[lk] = j;
            try { localStorage.setItem(lk, j); } catch (e) { /* bufor */ }
          } else {
            // HA nie ma jeszcze tego klucza — jednorazowo przenosimy to, co było w tej przeglądarce
            let local = null; try { local = JSON.parse(localStorage.getItem(lk)); } catch (e) { local = null; }
            const empty = local == null || local === '' || (Array.isArray(local) && !local.length) || (typeof local === 'object' && !Array.isArray(local) && !Object.keys(local).length);
            if (!empty) { DG_ST.dirty[hk] = local; DG_ST.migrated++; }
          }
        }
        DG_ST.ready = true; DG_ST.err = '';
        dgStoreSchedule(300);
        return true;
      } catch (e) {
        DG_ST.err = dgErrText(e); DG_ST.loadP = null; return false;
      }
    })();
    return DG_ST.loadP;
  }
  function dgStoreNote() {
    const pend = Object.keys(DG_ST.dirty).length;
    if (DG_ST.ready && !DG_ST.err && !pend) return `<div class="dg-muted" style="margin:6px 2px;">☁ Dziennik, kopie i profile są zapisywane w Home Assistant${DG_ST.migrated ? ` (przeniesiono ${DG_ST.migrated} z tej przeglądarki)` : ''}.</div>`;
    if (DG_ST.ready && !DG_ST.err) return '<div class="dg-muted" style="margin:6px 2px;">☁ Zapisuję w Home Assistant…</div>';
    return `<div class="dg-alarm" style="margin:6px 0;">⚠ Dane Diagnostyki są teraz tylko w tej przeglądarce${DG_ST.err ? ' — ' + dgEsc(DG_ST.err) : ''}. Dziennik i kopie nie przetrwają czyszczenia danych witryny; próbuję ponownie automatycznie.</div>`;
  }
  const dgEsc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const dgSleep = (ms) => new Promise(r => setTimeout(r, ms));

  // SHA-256 (czysty JS — działa także bez bezpiecznego kontekstu HTTPS)
  function dgSha256(str) {
    const K = [0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
    const bytes = Array.from(new TextEncoder().encode(str));
    const l = bytes.length * 8;
    bytes.push(0x80);
    while (bytes.length % 64 !== 56) bytes.push(0);
    for (let i = 7; i >= 0; i--) bytes.push(i >= 4 ? 0 : (l >>> (i * 8)) & 0xff);
    const H = [0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
    const rotr = (x, n) => (x >>> n) | (x << (32 - n));
    for (let o = 0; o < bytes.length; o += 64) {
      const w = new Array(64);
      for (let i = 0; i < 16; i++) w[i] = (bytes[o + i * 4] << 24) | (bytes[o + i * 4 + 1] << 16) | (bytes[o + i * 4 + 2] << 8) | bytes[o + i * 4 + 3];
      for (let i = 16; i < 64; i++) {
        const s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >>> 3);
        const s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >>> 10);
        w[i] = (w[i - 16] + s0 + w[i - 7] + s1) | 0;
      }
      let [a, b, c, d, e, f, g, h] = H;
      for (let i = 0; i < 64; i++) {
        const S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
        const ch = (e & f) ^ (~e & g);
        const t1 = (h + S1 + ch + K[i] + w[i]) | 0;
        const S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
        const mj = (a & b) ^ (a & c) ^ (b & c);
        const t2 = (S0 + mj) | 0;
        h = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0;
      }
      H[0] = (H[0] + a) | 0; H[1] = (H[1] + b) | 0; H[2] = (H[2] + c) | 0; H[3] = (H[3] + d) | 0;
      H[4] = (H[4] + e) | 0; H[5] = (H[5] + f) | 0; H[6] = (H[6] + g) | 0; H[7] = (H[7] + h) | 0;
    }
    return H.map(x => (x >>> 0).toString(16).padStart(8, '0')).join('');
  }

  // Grupy konfiguracji
  const DG_GROUPS = [
    ['mode',   '⚙️ Tryb pracy i eksport'],
    ['battery','🔋 Bateria'],
    ['gridch', '🔌 Ładowanie z sieci'],
    ['gen',    '🛢️ Generator'],
    ['grid',   '🌐 Sieć: limity i moc'],
    ['prot',   '🛡️ Zabezpieczenia sieci'],
    ['smart',  '💡 SmartLoad'],
    ['sys',    '🧰 System'],
    ['other',  '📦 Pozostałe'],
  ];
  // r: ryzyko 0 = niskie, 1 = średnie, 2 = wysokie (może uszkodzić baterię/instalację)
  const DG_DEFS = {
    // --- tryb pracy
    work_mode: { n: 'Tryb pracy', g: 'mode', r: 1, h: 'Selling First = sprzedaje nadwyżkę do sieci; Zero Export To Load/CT = nie oddaje do sieci.' },
    energy_pattern: { n: 'Priorytet energii', g: 'mode', r: 1, h: 'Battery First: PV najpierw ładuje baterię. Load First: PV najpierw zasila dom.' },
    time_of_use: { n: 'Strefy czasowe (Time of Use)', g: 'mode', r: 1, v: 1, h: 'Czy harmonogram programów 1–6 jest aktywny i w jakie dni (Week = cały tydzień).', rec: 'Programy działają tylko przy włączonej opcji Time Of Use (instrukcja Deye).' },
    io_mode: { n: 'Wejście/wyjście (IO)', g: 'mode', r: 1, h: 'Do czego służy dodatkowe złącze: Generator / SmartLoad / mikroinwerter.' },
    ac_coupling: { n: 'Sprzężenie AC', g: 'mode', r: 1, h: 'Współpraca z zewnętrznym falownikiem PV po stronie AC.' },
    grid_frequency: { n: 'Częstotliwość sieci', g: 'mode', r: 2, h: 'Znamionowa częstotliwość: 50 Hz dla Polski.' },
    grid_voltage: { n: 'Typ sieci (napięcie)', g: 'mode', r: 2, h: 'Znamionowe napięcie sieci ustawione w falowniku. W Polsce: 230 V (jedna faza) lub 230/400 V (trzy fazy) — wybór zależy od modelu falownika.' },
    export_surplus: { n: 'Eksport nadwyżki', g: 'mode', r: 1, h: 'Pozwala oddawać nadwyżkę PV do sieci.' },
    zero_export_power: { n: 'Moc zerowego eksportu', g: 'mode', r: 1, v: 1, soft: 1000, h: 'Moc na wyjściu do sieci utrzymywana w trybach Zero Export To Load / To CT (W).', rec: 'Zalecane 20–100 W (instrukcja Deye). Nie wpisuj wartości ujemnych — rejestr jest bez znaku: −20 zapisuje się jako ≈65 516 W i praktycznie wyłącza ograniczenie eksportu.', negMsg: 'Rejestr „Zero Export Power” jest bez znaku — wartość ujemna zapisałaby się jako ≈65 5xx W i wyłączyła ograniczenie eksportu. Wpisz 0 lub dodatnią (zalecane 20–100 W).' },
    export_asymmetry: { n: 'Eksport asymetryczny', g: 'mode', r: 1, h: 'Pozwala eksportować różną moc w różnych fazach.' },
    microinverter_export_cut_off: { n: 'Odcięcie eksportu mikroinwertera', g: 'mode', r: 1, h: 'Ogranicza mikroinwertery przy zerowym eksporcie.' },
    off_grid: { n: 'Praca wyspowa (Off-grid)', g: 'mode', r: 2, h: 'Odłącza falownik od sieci — pracuje tylko z PV i baterii.' },
    mppt_multi_point_scanning: { n: 'Skanowanie MPPT (multi-point)', g: 'mode', r: 0, h: 'Szuka punktu mocy przy zacienieniu paneli.' },
    charging_signal: { n: 'Sygnał ładowania', g: 'battery', r: 1, h: 'Sposób sygnalizacji ładowania do BMS baterii.' },
    // --- bateria
    battery_control_mode: { n: 'Tryb sterowania baterią', g: 'battery', r: 2, h: 'Lithium = sterowanie przez BMS (CAN/RS485). Zmiana bez znajomości baterii jest ryzykowna.' },
    battery_operation_mode: { n: 'Kryterium rozładowania', g: 'battery', r: 1, h: 'Capacity = progi w % SOC. Voltage = progi napięciowe.' },
    battery_bms_type: { n: 'Typ BMS baterii', g: 'battery', r: 2, h: 'Protokół komunikacji z BMS (np. PYLON).' },
    battery_capacity: { n: 'Pojemność baterii', g: 'battery', r: 2, h: 'Pojemność w Ah, od niej falownik liczy SOC (przy 51,2 V: Ah × 0,0512 = kWh).' },
    battery_empty: { n: 'Napięcie „pusta” (Empty)', g: 'battery', r: 2, h: 'Napięcie uznawane za 0% przy sterowaniu napięciowym.' },
    battery_equalization: { n: 'Napięcie wyrównawcze', g: 'battery', r: 2, h: 'Dotyczy baterii ołowiowych; dla litu zwykle bez znaczenia.' },
    battery_absorption: { n: 'Napięcie absorpcji', g: 'battery', r: 2, h: 'Napięcie ładowania końcowego.' },
    battery_float: { n: 'Napięcie podtrzymania (Float)', g: 'battery', r: 2, h: 'Napięcie podtrzymania po naładowaniu.' },
    battery_equalization_cycle: { n: 'Cykl wyrównawczy', g: 'battery', r: 1, h: 'Co ile dni wyrównanie (baterie ołowiowe).' },
    battery_equalization_time: { n: 'Czas wyrównania', g: 'battery', r: 1, h: 'Godziny trwania wyrównania (0 = wyłączone).' },
    battery_temperature_compensation: { n: 'Kompensacja temperaturowa', g: 'battery', r: 1, h: 'mV/°C/ogniwo — korekta napięcia ładowania.' },
    battery_max_charging_current: { n: 'Maks. prąd ładowania', g: 'battery', r: 2, v: 1, soft: 250, h: 'Limit prądu z PV+sieci. Ustaw wg karty katalogowej baterii (nie wyżej niż jej limit).', rec: 'Zakres zależy od mocy falownika (instrukcja Deye SG01LP1: 0–90 A dla 3,6 kW … 0–190 A dla 7,6/8 kW). Zalecenie producenta: lit ≈ pojemność [Ah] × 0,5; AGM/zalewowe × 0,2; żel wg producenta baterii.' },
    battery_max_discharging_current: { n: 'Maks. prąd rozładowania', g: 'battery', r: 2, v: 1, soft: 250, h: 'Limit prądu rozładowania — ustaw wg karty baterii.', rec: 'Zakres jak przy ładowaniu (zależy od mocy falownika). Lit ≈ pojemność [Ah] × 0,5; nie więcej niż limit producenta baterii.' },
    battery_resistance: { n: 'Rezystancja wewnętrzna', g: 'battery', r: 1, h: 'mΩ — używana do kompensacji spadku napięcia.' },
    battery_charging_efficiency: { n: 'Sprawność ładowania', g: 'battery', r: 1, h: 'Wpływa na obliczanie SOC.' },
    battery_shutdown_soc: { n: 'SOC — wyłączenie rozładowania', g: 'battery', r: 2, v: 1, h: 'Poniżej tego SOC falownik wyłącza się (ochrona przed zbyt głębokim rozładowaniem).', rec: 'Domyślnie wg instrukcji Deye: lit 10%, kwasowe 20%. Nie ustawiaj niżej niż zaleca producent baterii.' },
    battery_restart_soc: { n: 'SOC — ponowne uruchomienie', g: 'battery', r: 1, v: 1, h: 'Po wyłączeniu falownik wznawia wyjście AC, gdy SOC osiągnie tę wartość.', rec: 'Domyślnie wg instrukcji Deye: lit 40%, kwasowe 50%. Powinno być wyraźnie wyższe niż SOC wyłączenia.' },
    battery_low_soc: { n: 'SOC — alarm niskiego poziomu', g: 'battery', r: 1, v: 1, h: 'Poniżej tego SOC falownik zgłasza alarm niskiego stanu baterii.', rec: 'Domyślnie wg instrukcji Deye: lit 20%, kwasowe 35%.' },
    battery_shutdown_voltage: { n: 'Napięcie — wyłączenie', g: 'battery', r: 2, h: 'Poniżej tego napięcia falownik odcina baterię.' },
    battery_restart_voltage: { n: 'Napięcie — ponowne uruchomienie', g: 'battery', r: 1, h: 'Powyżej tego napięcia bateria wraca do pracy po wyłączeniu.' },
    battery_low_voltage: { n: 'Napięcie — alarm niskie', g: 'battery', r: 1, h: 'Próg ostrzeżenia o niskim napięciu.' },
    battery_wake_up: { n: 'Wybudzenie baterii', g: 'battery', r: 2, h: 'Wymusza wybudzenie uśpionej baterii (aktywuj tylko na chwilę).' },
    // --- ładowanie z sieci
    battery_grid_charging: { n: 'Ładowanie baterii z sieci', g: 'gridch', r: 1, h: 'Pozwala ładować baterię z sieci (np. w taniej strefie).' },
    battery_grid_charging_start: { n: 'Start ładowania z sieci — SOC', g: 'gridch', r: 1, h: 'Gdy SOC spadnie poniżej tej wartości, ładowanie z sieci włącza się.' },
    battery_grid_charging_start_voltage: { n: 'Start ładowania z sieci — napięcie', g: 'gridch', r: 1, h: 'Odpowiednik progu SOC dla sterowania napięciowego.' },
    battery_grid_charging_current: { n: 'Prąd ładowania z sieci', g: 'gridch', r: 2, h: 'Maks. prąd ładowania z sieci (moc ≈ prąd × napięcie baterii).' },
    // --- generator
    generator: { n: 'Generator (wejście)', g: 'gen', r: 1, h: 'Włącza wejście generatora.' },
    generator_operating_time: { n: 'Maks. czas pracy generatora', g: 'gen', r: 0, h: 'Godziny.' },
    generator_cooling_time: { n: 'Czas schładzania generatora', g: 'gen', r: 0, h: 'Godziny.' },
    generator_min_pv_power: { n: 'Min. moc PV przy generatorze', g: 'gen', r: 1, h: 'Poniżej tej mocy PV generator może zostać uruchomiony.' },
    battery_generator_charging: { n: 'Ładowanie baterii z generatora', g: 'gen', r: 1, h: 'Pozwala ładować baterię z generatora.' },
    battery_generator_charging_start: { n: 'Start ładowania z generatora — SOC', g: 'gen', r: 1, h: 'Próg SOC startu.' },
    battery_generator_charging_start_voltage: { n: 'Start ładowania z generatora — napięcie', g: 'gen', r: 1, h: 'Próg napięcia startu.' },
    battery_generator_charging_current: { n: 'Prąd ładowania z generatora', g: 'gen', r: 2, h: 'Maks. prąd ładowania z generatora.' },
    generator_peak_shaving: { n: 'Peak shaving generatora (moc)', g: 'gen', r: 1, h: 'Limit mocy pobieranej z generatora (W).' },
    generator_on_grid: { n: 'Generator jako sieć (On-Grid)', g: 'gen', r: 2, h: 'Generator traktowany jak źródło sieciowe.' },
    generator_grid_side: { n: 'Generator po stronie sieci', g: 'gen', r: 2, h: 'Podłączenie generatora po stronie wejścia sieci.' },
    // --- sieć
    grid_max_export_power: { n: 'Maks. moc eksportu', g: 'grid', r: 2, v: 1, h: 'Górny limit mocy oddawanej do sieci (Max Sell Power, W) — zgodnie z umową z operatorem.' },
    grid_max_import_power: { n: 'Maks. moc importu', g: 'grid', r: 2, h: 'Limit poboru z sieci (W).' },
    export_surplus_power: { n: 'Moc eksportu nadwyżki', g: 'grid', r: 1, h: 'Moc, do której oddawana jest nadwyżka (W).' },
    grid_peak_shaving: { n: 'Peak shaving sieci (moc)', g: 'grid', r: 1, v: 1, h: 'Po włączeniu ogranicza moc pobieraną z sieci do ustawionej wartości (W); obciążenie ponad nią pokrywają najpierw PV i bateria.', rec: 'Ustaw ponad typowe zapotrzebowanie domu, inaczej bateria będzie szybko pracować na pełnej mocy.' },
    pv_power: { n: 'Maks. moc PV (limit)', g: 'grid', r: 2, h: 'Ograniczenie mocy generowanej z paneli (W).' },
    grid_power_factor: { n: 'Współczynnik mocy (PF)', g: 'grid', r: 2, h: 'Tylko za zgodą operatora sieci.' },
    // --- zabezpieczenia
    grid_voltage_protection_high: { n: 'Napięcie sieci — próg górny', g: 'prot', r: 2, h: 'Powyżej tej wartości falownik odłącza się od sieci. Wartość narzucona przez operatora.' },
    grid_voltage_protection_low: { n: 'Napięcie sieci — próg dolny', g: 'prot', r: 2, h: 'Poniżej tej wartości falownik odłącza się od sieci.' },
    grid_frequency_protection_high: { n: 'Częstotliwość sieci — próg górny', g: 'prot', r: 2, h: 'Powyżej tej wartości odłączenie od sieci.' },
    grid_frequency_protection_low: { n: 'Częstotliwość sieci — próg dolny', g: 'prot', r: 2, h: 'Poniżej tej wartości odłączenie od sieci.' },
    // --- SmartLoad
    smartload_off_voltage: { n: 'SmartLoad — wyłączenie (napięcie)', g: 'smart', r: 1, h: 'Poniżej tego napięcia baterii odbiornik SmartLoad jest odłączany.' },
    smartload_off: { n: 'SmartLoad — wyłączenie (SOC)', g: 'smart', r: 1, h: 'Poniżej tego SOC SmartLoad jest odłączany.' },
    smartload_on_voltage: { n: 'SmartLoad — włączenie (napięcie)', g: 'smart', r: 1, h: 'Powyżej tego napięcia SmartLoad się włącza.' },
    smartload_on: { n: 'SmartLoad — włączenie (SOC)', g: 'smart', r: 1, h: 'Powyżej tego SOC SmartLoad się włącza.' },
    // --- system
    self_check_time: { n: 'Czas autotestu', g: 'sys', r: 0, h: 'Czas autotestu falownika (s).' },
    access_point: { n: 'Punkt dostępowy Wi-Fi (AP)', g: 'sys', r: 0, h: 'Hotspot loggera Solarman.' },
    cloud: { n: 'Chmura Solarman', g: 'sys', r: 0, h: 'Połączenie loggera z chmurą producenta.' },
    restart: { n: 'Restart falownika', g: 'sys', r: 2, h: 'Uruchamia ponownie falownik — chwilowo traci zasilanie obwód zasilany z falownika.' },
    main_power: { n: 'Falownik — włącznik główny', g: 'sys', r: 2, h: 'Wyłączenie zatrzymuje pracę falownika.' },
  };
  // Parametry, dla których wartość ujemna bywa poprawna (reszta: rejestry bez znaku — blokujemy minus)
  const DG_NEG_OK = ['battery_temperature_compensation'];
  // Ściągawka: co zwykle można zmieniać (ogólnie, niezależnie od modelu)
  const DG_CHEAT = [
    ['🟢 Zwykle bezpieczne', 'Strefy czasowe (godziny, SOC, moc programów), ładowanie z sieci włącz/wyłącz i jego progi SOC, progi SmartLoad, Moc zerowego eksportu (20–100 W), Peak shaving. Zmiana jest odwracalna i nie wpływa na ochronę baterii.'],
    ['🟡 Ostrożnie', 'Tryb pracy, priorytet energii, Maks. moc eksportu / importu, Eksport nadwyżki, prąd ładowania z sieci, SOC wyłączenia/restartu. Zmieniaj pojedynczo i obserwuj falownik kilka minut.'],
    ['🔴 Tylko instalator / zgodnie z kartą baterii', 'Tryb sterowania baterią, typ BMS, pojemność, napięcia (absorpcja, float, wyrównanie, odcięcia), maks. prądy baterii, zabezpieczenia i częstotliwość sieci, współczynnik mocy, Off-grid, restart i wyłącznik główny.'],
  ];
  const DG_DOMAINS = ['number', 'select', 'switch', 'time', 'button'];
  const DG_FAULTS = {
    F13: 'Zmiana trybu pracy', F18: 'Nadprądowy błąd sprzętowy AC', F20: 'Nadprądowy błąd sprzętowy DC',
    F23: 'Przejściowy prąd upływu (GFCI)', F24: 'Błąd izolacji DC', F26: 'Niezbalansowana szyna DC', F29: 'Błąd magistrali równoległej CAN',
    F35: 'Brak sieci AC', F41: 'Zatrzymany system równoległy', F42: 'Zbyt niskie napięcie linii AC', F46: 'Błąd baterii zapasowej',
    F47: 'Zbyt wysoka częstotliwość AC', F48: 'Zbyt niska częstotliwość AC', F56: 'Zbyt niskie napięcie szyny DC (zwykle: rozładowana bateria)',
    F63: 'Błąd ARC (łuk elektryczny)', F64: 'Zbyt wysoka temperatura radiatora',
  };
  const DG_SERIES_COLORS = ['#ffcc00', '#0a84ff', '#30d158', '#ff453a', '#bf5af2', '#ff9f0a', '#64d2ff', '#ff6482', '#a2845e', '#8e8e93'];
  const DG_RANGES = { '1h': 3600e3, '1d': 86400e3, '7d': 7 * 86400e3, '30d': 30 * 86400e3, '90d': 90 * 86400e3, '365d': 365 * 86400e3 };

  const DG_CSS = `
    .dg { display:block; }
    .dg-gate { max-width:420px; margin:24px auto; padding:22px; border-radius:18px; background:var(--card); box-shadow:var(--shadow); text-align:center; }
    .dg-gate h3 { margin:0 0 6px; font-size:18px; } .dg-gate p { margin:0 0 14px; color:var(--muted); font-size:13px; }
    .dg input[type=text], .dg input[type=password], .dg input[type=number], .dg input[type=time], .dg select, .dg input[type=search] { background:var(--input-bg); color:var(--text); border:1px solid var(--line); border-radius:10px; padding:8px 10px; font-size:14px; font-family:inherit; min-width:0; }
    .dg input.dirty, .dg select.dirty { border-color:var(--orange); box-shadow:0 0 0 2px rgba(255,159,10,.25); }
    .dg input:disabled, .dg select:disabled, .dg button:disabled { opacity:.45; cursor:not-allowed; }
    .dg-btn { background:var(--accent); color:#fff; border:none; border-radius:10px; padding:8px 14px; font-weight:600; font-size:13px; cursor:pointer; font-family:inherit; }
    .dg-btn.sec { background:var(--seg-bg); color:var(--text); } .dg-btn.red { background:var(--red); } .dg-btn.green { background:var(--green); color:#04210c; } .dg-btn.sm { padding:5px 10px; font-size:12px; }
    .dg-bar { display:flex; align-items:center; gap:8px; flex-wrap:wrap; padding:9px 12px; border-radius:12px; background:rgba(255,159,10,.12); color:var(--orange); font-size:12.5px; margin-bottom:10px; }
    .dg-bar .sp { flex:1; }
    .dg-nav { display:flex; gap:6px; overflow-x:auto; margin-bottom:12px; padding-bottom:2px; scrollbar-width:none; }
    .dg-nav::-webkit-scrollbar { display:none; }
    .dg-pill { flex:none; border:none; background:var(--surface); color:var(--text2); padding:8px 13px; border-radius:20px; font-weight:600; font-size:13px; cursor:pointer; font-family:inherit; }
    .dg-pill.on { background:var(--accent); color:#fff; }
    .dg-card { background:var(--card); border-radius:18px; padding:14px 16px; margin-bottom:12px; box-shadow:var(--shadow); }
    .dg-card h4 { margin:0 0 10px; font-size:15px; } .dg-card .sub { color:var(--muted); font-size:12px; margin:-6px 0 10px; }
    .dg-tiles { display:grid; grid-template-columns:repeat(auto-fill,minmax(210px,1fr)); gap:10px; }
    .dg-tile { background:var(--surface); border-radius:14px; padding:11px 12px; }
    .dg-tile .t { font-size:11px; color:var(--muted); text-transform:uppercase; letter-spacing:.4px; margin-bottom:5px; }
    .dg-tile .l { display:flex; justify-content:space-between; gap:8px; font-size:13px; padding:2px 0; } .dg-tile .l span:first-child { color:var(--muted); } .dg-tile .l b { font-variant-numeric:tabular-nums; text-align:right; }
    .dg-ok { color:var(--green); } .dg-warn { color:var(--orange); } .dg-bad { color:var(--red); }
    .dg-row { display:grid; grid-template-columns:minmax(0,1.5fr) 110px minmax(150px,1fr) 78px; gap:8px 12px; align-items:center; padding:9px 0; border-top:1px solid var(--line); }
    .dg-row:first-of-type { border-top:none; }
    .dg-row .nm { font-weight:600; font-size:14px; } .dg-row .nm small { display:block; font-weight:400; color:var(--muted); font-size:11.5px; line-height:1.35; margin-top:2px; }
    .dg-row .eid { font-size:10.5px; color:var(--muted2); font-family:ui-monospace,Menlo,monospace; word-break:break-all; }
    .dg-row .cur { font-variant-numeric:tabular-nums; font-weight:700; } .dg-row .ctl { display:flex; gap:6px; align-items:center; } .dg-row .ctl input, .dg-row .ctl select { flex:1; width:100%; }
    .dg-row .rng { font-size:10.5px; color:var(--muted); } .dg-risk2 .nm:after { content:' ⚠'; color:var(--orange); }
    .dg-gtitle { margin:14px 0 2px; font-size:13px; font-weight:700; color:var(--accent); text-transform:uppercase; letter-spacing:.5px; }
    .dg-tbl { width:100%; border-collapse:collapse; font-size:13px; } .dg-tbl th { text-align:left; color:var(--muted); font-weight:600; font-size:11.5px; padding:6px 8px; } .dg-tbl td { padding:7px 8px; border-top:1px solid var(--line); vertical-align:middle; }
    .dg-tbl td input, .dg-tbl td select { width:100%; } .dg-tbl .num { text-align:right; font-variant-numeric:tabular-nums; }
    .dg-tl { display:flex; height:30px; border-radius:9px; overflow:hidden; background:var(--surface); position:relative; margin:8px 0 4px; }
    .dg-tl > div { display:flex; align-items:center; justify-content:center; font-size:11px; color:#fff; white-space:nowrap; overflow:hidden; border-right:1px solid rgba(0,0,0,.25); }
    .dg-tl .now { position:absolute; top:-3px; bottom:-3px; width:2px; background:var(--text); }
    .dg-ticks { display:flex; justify-content:space-between; font-size:10.5px; color:var(--muted); }
    .dg-rangebar { display:flex; gap:4px; flex-wrap:wrap; margin-bottom:10px; } .dg-rangebar button { border:none; background:var(--seg-bg); color:var(--text2); border-radius:9px; padding:6px 12px; font-weight:600; font-size:12.5px; cursor:pointer; font-family:inherit; } .dg-rangebar button.on { background:var(--accent); color:#fff; }
    .dg-chartbox { position:relative; height:360px; } .dg-sel { max-height:240px; overflow:auto; border:1px solid var(--line); border-radius:12px; padding:6px 10px; margin-top:8px; }
    .dg-sel label { display:flex; gap:8px; align-items:center; padding:3px 0; font-size:12.5px; cursor:pointer; } .dg-sel .u { color:var(--muted); font-size:11px; margin-left:auto; } .dg-sel .gh { font-size:11px; font-weight:700; color:var(--muted); margin-top:6px; text-transform:uppercase; }
    .dg-chips { display:flex; gap:6px; flex-wrap:wrap; margin:6px 0; } .dg-chip { border:1px solid var(--line); background:transparent; color:var(--text2); border-radius:16px; padding:4px 10px; font-size:12px; cursor:pointer; font-family:inherit; }
    .dg-modal { position:fixed; inset:0; background:rgba(0,0,0,.6); z-index:9999; display:flex; align-items:center; justify-content:center; padding:16px; }
    .dg-modal > div { background:var(--card); color:var(--text); border-radius:18px; padding:18px; max-width:560px; width:100%; max-height:86vh; overflow:auto; box-shadow:0 20px 60px rgba(0,0,0,.5); }
    .dg-modal h3 { margin:0 0 10px; font-size:17px; } .dg-modal .acts { display:flex; gap:8px; justify-content:flex-end; margin-top:14px; flex-wrap:wrap; }
    .dg-diff { width:100%; border-collapse:collapse; font-size:13px; } .dg-diff td { padding:5px 6px; border-top:1px solid var(--line); } .dg-diff .from { color:var(--muted); text-decoration:line-through; } .dg-diff .to { font-weight:700; color:var(--green); }
    .dg-rec { margin-top:4px; padding:5px 8px; border-radius:8px; background:rgba(10,132,255,.10); color:var(--text2); font-size:11.5px; line-height:1.4; }
    .dg-ver { color:var(--green); font-size:10.5px; margin-left:4px; } .dg-unv { color:var(--muted2); font-size:10.5px; margin-left:4px; }
    .dg-rwarn { margin-top:4px; color:var(--orange); font-size:11.5px; }
    .dg-alarm { background:rgba(255,69,58,.14); border:1px solid var(--red); border-radius:14px; padding:10px 12px; margin-bottom:10px; font-size:13px; }
    .dg-alarm .a { padding:6px 0; border-top:1px solid rgba(255,69,58,.3); } .dg-alarm .a:first-child { border-top:none; } .dg-alarm .acts { display:flex; gap:6px; margin-top:6px; flex-wrap:wrap; }
    .dg-cheat summary { cursor:pointer; font-weight:700; font-size:14px; } .dg-cheat .it { margin-top:8px; font-size:12.5px; line-height:1.45; } .dg-cheat .it b { display:block; }
    .dg-redbox { background:rgba(255,69,58,.12); color:var(--red); border-radius:10px; padding:8px 10px; font-size:12.5px; margin-top:10px; }
    .dg-toast { position:sticky; bottom:8px; margin-top:8px; padding:10px 14px; border-radius:12px; font-size:13px; font-weight:600; display:none; background:var(--card); box-shadow:var(--shadow); border-left:4px solid var(--green); }
    .dg-toast.bad { border-left-color:var(--red); } .dg-toast.show { display:block; }
    .dg-muted { color:var(--muted); font-size:12px; } .dg-mono { font-family:ui-monospace,Menlo,monospace; }
    .dg-tbl.stack td[data-l]:before { content:attr(data-l); display:none; font-size:10.5px; color:var(--muted); }
    @media (max-width:700px) { .dg-tbl.stack td[data-l]:before { display:block; } .dg-row { grid-template-columns:1fr auto; } .dg-row .ctl { grid-column:1 / -1; } .dg-row .rng { grid-column:1 / -1; } .dg-chartbox { height:300px; } .dg-tbl.stack thead { display:none; } .dg-tbl.stack td { display:block; border:none; padding:3px 8px; } .dg-tbl.stack tr { display:block; border-top:1px solid var(--line); padding:6px 0; } }
  `;

  Object.assign(BmsPanel.prototype, {
    // ---------- dostęp, stan ----------
    _dgS() {
      if (!this._dg) this._dg = {
        sec: 'overview', until: 0, fails: 0, lockedUntil: 0, mounted: false, busy: false,
        cfgQ: '', cfgG: '', senQ: '', alQ: '',
        ch: { range: '1d', sel: [], compare: false, q: '', info: '', series: null, chart: null, req: 0 },
        file: null,
      };
      return this._dg;
    },
    _dgLS() { return DG_LS; },
    _dgIsAdmin() { const u = this._hass && this._hass.user; return !!(u && u.is_admin); },
    _dgUnlocked() { return Date.now() < this._dgS().until; },
    _dgSyncTab() {
      if (DG_ST.card && !DG_ST.ready && Date.now() - DG_ST.retryAt > 30000) { DG_ST.retryAt = Date.now(); dgStoreLoad(this); }
      if (DG_ST.ready && DG_ST.card && Object.keys(DG_ST.dirty).length && !DG_ST.timer) dgStoreSchedule(2000);
      const b = this._el('tabDiag');
      if (b) { b.style.display = this._dgIsAdmin() ? '' : 'none'; const ms = this._hass.states[this._eid('sensor', 'monitor_status')]; const be = ms && ms.attributes && Array.isArray(ms.attributes.alarms) ? ms.attributes.alarms.length : 0; const bad = (DG_LS.get('bms_diag_alarms', []).length || be) ? ' ⚠' : ''; const want = 'Diagnostyka' + bad; const lb = b.querySelector('.tl'); if (lb && lb.textContent !== want) lb.textContent = want; b.classList.toggle('warn', !!bad); }
      const s = this._dgS();
      const nw = Date.now(); if (nw - (s._wcAt || 0) > 5000) { s._wcAt = nw; try { this._dgWatchCheck(); } catch (e) { console.warn('EMS diag watch', e); } }
      if (s.until && !this._dgUnlocked() && this._activeTab === 'diag' && this._el('dgBody')) { s.until = 0; this._dgRender(); }
    },
    // Urządzenia Solarman wykryte w rejestrze encji HA (niezależnie od nazw encji)
    _dgDevices() {
      const reg = this._hass && this._hass.entities; if (!reg) return [];
      if (this._dgDevCache && this._dgDevCache.reg === reg) return this._dgDevCache.list;
      const byDev = {};
      Object.keys(reg).forEach(eid => {
        const e = reg[eid]; if (!e || e.platform !== 'solarman' || !e.device_id) return;
        (byDev[e.device_id] = byDev[e.device_id] || []).push(eid);
      });
      const list = Object.keys(byDev).map(dev => {
        const ids = byDev[dev]; const objs = ids.map(i => i.slice(i.indexOf('.') + 1).split('_'));
        let k = 0; while (objs.every(o => o.length > k + 0 && o[k] === objs[0][k]) && k < objs[0].length) k++;
        const prefix = objs[0].slice(0, k).join('_');
        const cfg = ids.filter(i => DG_DOMAINS.includes(i.slice(0, i.indexOf('.')))).length;
        return { dev, prefix, n: ids.length, cfg };
      }).sort((x, y) => (y.cfg - x.cfg) || (y.n - x.n));
      this._dgDevCache = { reg, list };
      return list;
    },
    _dgPrefix() {
      const ov = DG_LS.get('bms_diag_prefix', '');
      if (ov) return ov;
      const dv = this._dgDevices(); if (dv.length && dv[0].cfg > 0) return dv[0].prefix;
      if (this._dgPrefixAuto) return this._dgPrefixAuto;
      const ids = Object.keys((this._hass && this._hass.states) || {});
      const hit = ids.find(k => /^time\.[a-z0-9_]+_program_1_time$/.test(k));
      let p = 'inverter';
      if (hit) { p = hit.slice(5, -'_program_1_time'.length); this._dgPrefixAuto = p; }
      return p;
    },
    _dgPrefixSource() {
      if (DG_LS.get('bms_diag_prefix', '')) return 'ustawiony ręcznie';
      const dv = this._dgDevices(); if (dv.length && dv[0].cfg > 0) return 'wykryty z integracji Solarman';
      return 'zgadnięty po nazwach encji';
    },
    _dgKey(eid) {
      const prefix = this._dgPrefix();
      const obj = eid.slice(eid.indexOf('.') + 1);
      if (!prefix) { const r = this._hass.entities && this._hass.entities[eid]; return r && r.platform === 'solarman' ? obj : null; }
      if (obj === prefix) return 'main_power';
      if (obj.startsWith(prefix + '_')) return obj.slice(prefix.length + 1);
      return null;
    },
    _dgRisk(key) {
      const d = DG_DEFS[key || '']; if (d) return d.r;
      if (/^program_\d+_/.test(key || '')) return 1;
      return 2;   // parametr spoza słownika — traktuj jak ryzykowny
    },
    _dgGuessGroup(key) {
      const k = key || '';
      if (/smartload|smart_load/.test(k)) return 'smart';
      if (/protect|ovp|uvp|ofp|ufp/.test(k)) return 'prot';
      if (/generator|\bgen_|diesel/.test(k)) return 'gen';
      if (/grid.*charg|charg.*grid/.test(k)) return 'gridch';
      if (/batter|soc|charg|discharg|bms|float|absorp|equaliz/.test(k)) return 'battery';
      if (/grid|export|import|feed|power_limit|peak/.test(k)) return 'grid';
      if (/mode|pattern|priority|work|time_of_use|schedule/.test(k)) return 'mode';
      if (/restart|reset|cloud|wifi|wlan|access|self_check/.test(k)) return 'sys';
      return 'other';
    },
    _dgName(eid, st) {
      const key = this._dgKey(eid);
      const d = key && DG_DEFS[key];
      if (d) return d.n;
      const fn = st && st.attributes && st.attributes.friendly_name;
      return String(fn || eid).replace(/^inverter\s+/i, '');
    },
    _dgCfgEntities() {
      const states = this._hass.states; const out = [];
      Object.keys(states).forEach(eid => {
        const dom = eid.slice(0, eid.indexOf('.'));
        if (!DG_DOMAINS.includes(dom)) return;
        const key = this._dgKey(eid); if (key == null) return;
        if (/^program_\d+_/.test(key)) return;
        const st = states[eid]; const def = DG_DEFS[key] || null;
        out.push({ eid, dom, key, st, def, name: this._dgName(eid, st), g: def ? def.g : this._dgGuessGroup(key), r: this._dgRisk(key), ord: def ? Object.keys(DG_DEFS).indexOf(key) : 9999 });
      });
      out.sort((a, b) => (a.ord - b.ord) || a.name.localeCompare(b.name, 'pl'));
      return out;
    },
    _dgSensors() {
      const states = this._hass.states; const prefix = this._dgPrefix(); const out = [];
      Object.keys(states).forEach(eid => {
        const dom = eid.slice(0, eid.indexOf('.'));
        if (dom !== 'sensor' && dom !== 'binary_sensor') return;
        const obj = eid.slice(eid.indexOf('.') + 1);
        const reg = this._hass.entities && this._hass.entities[eid];
        const own = prefix ? obj.startsWith(prefix + '_') : !!(reg && reg.platform === 'solarman');
        if (!(own || obj.startsWith('bms_'))) return;
        const st = states[eid]; const a = st.attributes || {};
        out.push({ eid, dom, key: own ? (prefix ? obj.slice(prefix.length + 1) : obj) : obj, st, unit: a.unit_of_measurement || '', name: String(a.friendly_name || eid).replace(/^inverter\s+/i, '') });
      });
      out.sort((a, b) => a.name.localeCompare(b.name, 'pl'));
      return out;
    },
    _dgVal(eid) { const s = this._hass.states[eid]; return s ? s.state : ''; },
    _dgFmt(v) {
      if (v == null || v === '' || v === 'unknown' || v === 'unavailable') return v === 'unavailable' ? 'niedostępne' : '—';
      const n = Number(v);
      if (!isNaN(n) && String(v).trim() !== '') return String(Math.round(n * 1000) / 1000).replace('.', ',');
      return String(v);
    },
    _dgSame(a, b) {
      const na = Number(a), nb = Number(b);
      if (!isNaN(na) && !isNaN(nb) && String(a).trim() !== '' && String(b).trim() !== '') return Math.abs(na - nb) < 1e-4;
      if (/^\d\d:\d\d/.test(String(a)) && /^\d\d:\d\d/.test(String(b))) return String(a).slice(0, 5) === String(b).slice(0, 5);
      return String(a).toLowerCase() === String(b).toLowerCase();
    },

    // ---------- UI: powłoka ----------
    _dgVerLine() {
      const same = !BMS_INFO.url || BMS_INFO.url === BMS_INFO.card || BMS_INFO.url.indexOf(BMS_INFO.card + '.') === 0;
      const warn = same ? '' : ' <b class="dg-bad">⚠ uruchomiona integracja ma inną wersję niż pliki karty — zrestartuj Home Assistanta i odśwież stronę (Ctrl+F5)</b>';
      return `Karta ${BMS_INFO.card || '?'} · integracja ${BMS_INFO.url || '?'}${warn}`;
    },
    _dgOpen() {
      const s = this._dgS();
      if (!s.mounted) this._dgMount();
      this._dgRender();
      dgStoreLoad(this).then((ok) => {
        if (ok && this._activeTab === 'diag') { this._dgRenderAlarmBox(); if (this._dgUnlocked()) this._dgRenderSection(); }
        this._dgStoreNoteRefresh();
      });
    },
    _dgStoreNoteRefresh() { const n = this._el('dgStoreNote'); if (n) n.innerHTML = dgStoreNote(); },
    _dgMount() {
      const s = this._dgS(); const root = this._el('diagRoot'); if (!root) return;
      s.mounted = true;
      root.textContent = '';                      // zdejmuje napis „Ładowanie modułu…” z rdzenia
      const st = document.createElement('style'); st.textContent = DG_CSS; root.appendChild(st);
      const host = document.createElement('div'); host.className = 'dg'; host.id = 'dgHost'; root.appendChild(host);
      host.addEventListener('click', (e) => { const t = e.target.closest('[data-act]'); if (t) this._dgAct(t.dataset.act, t, e); });
      host.addEventListener('input', (e) => this._dgOnInput(e));
      host.addEventListener('change', (e) => this._dgOnInput(e, true));
      host.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && e.target.id === 'dgPw') this._dgAct('unlock', e.target, e);
        else if (e.key === 'Enter' && e.target.dataset && e.target.dataset.modeNum !== undefined) this._dgModesSave(e.target.dataset.modeNum);
      });
    },
    _dgRender() {
      const s = this._dgS(); const host = this._el('dgHost'); if (!host) return;
      if (!this._dgIsAdmin()) { host.innerHTML = '<div class="dg-gate"><h3>🛠️ Diagnostyka</h3><p>Ta zakładka jest dostępna tylko dla administratorów Home Assistant.</p></div>'; return; }
      if (!this._dgUnlocked()) {
        host.innerHTML = `<div class="dg-gate"><h3>🔒 Diagnostyka — tryb instalatora</h3><p>Konfiguracja falownika, strefy czasowe, alarmy i wykresy serwisowe. Podaj hasło, aby odblokować na 15 minut.</p>
          <input type="password" id="dgPw" placeholder="Hasło" autocomplete="off" style="width:100%;margin-bottom:10px;" />
          <button class="dg-btn" data-act="unlock" style="width:100%;">Odblokuj</button><div id="dgGateMsg" class="dg-muted" style="margin-top:10px;min-height:16px;"></div><div class="dg-muted" id="dgVer" style="margin-top:14px;font-size:11px;">${this._dgVerLine()}</div></div>`;
        return;
      }
      const secs = [['overview', '📡 Przegląd'], ['selftest', '🩺 Autotest'], ['wizard', '🧭 Kreator instalacji'], ['config', '⚙️ Konfiguracja'], ['tou', '🕒 Strefy czasowe'], ['charts', '📈 Wykresy'], ['alarms', '🚨 Alarmy'], ['modes', '🛡️ Tryby'], ['notify', '🔔 Powiadomienia'], ['backup', '💾 Kopie i profile'], ['log', '📜 Dziennik zmian'], ['adv', '🧪 Zaawansowane']];
      host.innerHTML = `<div class="dg-bar"><span>🔓 Tryb instalatora aktywny · wygasa za <b id="dgLeft">–</b></span><span class="sp"></span><button class="dg-btn sec sm" data-act="extend">Przedłuż</button><button class="dg-btn sec sm" data-act="lock">Zablokuj</button></div>
        <div class="dg-nav">${secs.map(([k, l]) => `<button class="dg-pill ${s.sec === k ? 'on' : ''}" data-act="sec" data-sec="${k}">${l}</button>`).join('')}</div>
        <div id="dgStoreNote">${dgStoreNote()}</div><div id="dgAlarmBox">${this._dgAlarmHtml()}</div><div id="dgBody"></div><div class="dg-muted" id="dgVer" style="margin:14px 0 4px;font-size:11px;">${this._dgVerLine()}</div><div id="dgToast" class="dg-toast"></div>`;
      this._dgRenderSection();
      this._dgTickBar();
    },
    _dgRenderSection() {
      const s = this._dgS(); const body = this._el('dgBody'); if (!body) return;
      if (!this._dgUnlocked()) { this._dgRender(); return; }
      const fn = this['_dgSec_' + s.sec];
      body.innerHTML = fn ? fn.call(this) : '';
      const after = this['_dgAfter_' + s.sec]; if (after) after.call(this);
    },
    _dgTickBar() {
      const el = this._el('dgLeft'); if (!el) return;
      const ms = Math.max(0, this._dgS().until - Date.now()); const m = Math.floor(ms / 60000), sec = Math.floor(ms % 60000 / 1000);
      el.textContent = `${m}:${String(sec).padStart(2, '0')}`;
    },
    _dgToast(msg, bad) {
      const t = this._el('dgToast'); if (!t) return;
      t.textContent = msg; t.className = 'dg-toast show' + (bad ? ' bad' : '');
      clearTimeout(this._dgToastT); this._dgToastT = setTimeout(() => { t.className = 'dg-toast'; }, 9000);
    },

    // ---------- akcje ----------
    _dgAct(act, t, e) {
      const s = this._dgS();
      switch (act) {
        case 'unlock': {
          const msg = this._el('dgGateMsg'); const inp = this._el('dgPw');
          if (Date.now() < s.lockedUntil) { if (msg) msg.textContent = `Za dużo prób — odczekaj ${Math.ceil((s.lockedUntil - Date.now()) / 1000)} s.`; return; }
          const pw = inp ? inp.value : '';
          if (dgSha256(DG_SALT + pw) === DG_PW_SHA) { s.until = Date.now() + DG_UNLOCK_MS; s.fails = 0; this._dgRender(); }
          else { s.fails++; if (s.fails >= 3) { s.lockedUntil = Date.now() + 30000; s.fails = 0; } if (msg) { msg.textContent = '❌ Nieprawidłowe hasło.'; msg.className = 'dg-muted dg-bad'; } if (inp) inp.value = ''; }
          break; }
        case 'lock': s.until = 0; this._dgDestroyChart(); this._dgRender(); break;
        case 'extend': s.until = Date.now() + DG_UNLOCK_MS; this._dgTickBar(); break;
        case 'sec': s.sec = t.dataset.sec; this._dgDestroyChart(); this._dgRender(); break;
        case 'save-row': this._dgSaveDirty(t.closest('[data-scope]')); break;
        case 'save-scope': this._dgSaveDirty(this._el('dgBody').querySelector(`[data-scope="${t.dataset.scope}"]`) || this._el('dgBody')); break;
        case 'reset-scope': this._dgSectionRefresh(); break;
        case 'toggle': this._dgToggle(t.dataset.eid); break;
        case 'mode-sw': this._dgModesToggle(t.dataset.k); break;
        case 'nt-save': this._dgNtSave(); break;
        case 'nt-test': this._dgNtTest(); break;
        case 'nt-defaults': this._dgNtDefaults(); break;
        case 'nt-reload': this._dgNtLoad(true); break;
        case 'st-run': this._dgStRun(); break;
        case 'st-copy': this._dgStCopy(); break;
        case 'nt-all': this._dgNtAll(t.dataset.g, t.dataset.v === '1'); break;
        case 'mode-save': this._dgModesSave(t.dataset.k); break;
        case 'press': this._dgPress(t.dataset.eid); break;
        case 'clear-load-hist': this._dgClearLoadHist(); break;
        case 'reset-pv-learn': this._dgResetPvLearn(); break;
        case 'cfg-g': s.cfgG = t.dataset.g === s.cfgG ? '' : t.dataset.g; this._dgFilterCfg(); break;
        case 'range': s.ch.range = t.dataset.r; this._dgRenderSection(); break;
        case 'preset': this._dgPreset(t.dataset.p); break;
        case 'chart-go': this._dgChartDraw(); break;
        case 'chart-csv': this._dgChartCsv(); break;
        case 'cmp': s.ch.compare = !!t.checked; this._dgChartDraw(); break;
        case 'export': this._dgExport(); break;
        case 'import-pick': { const f = this._el('dgFile'); if (f) f.click(); break; }
        case 'profile-save': this._dgProfileSave(); break;
        case 'profile-load': this._dgProfileLoad(t.dataset.name, t.dataset.kind); break;
        case 'profile-del': this._dgProfileDel(t.dataset.name); break;
        case 'alarm-restore': this._dgAlarmRestore(Number(t.dataset.i)); break;
        case 'alarm-dismiss': { const al = DG_LS.get('bms_diag_alarms', []); al.splice(Number(t.dataset.i), 1); DG_LS.set('bms_diag_alarms', al); this._dgRenderAlarmBox(); this._dgSyncTab(); break; }
        case 'log-undo': this._dgLogUndo(Number(t.dataset.i)); break;
        case 'log-clear': if (confirm('Wyczyścić dziennik zmian (jest zapisany w Home Assistant)?')) { DG_LS.set('bms_diag_log', []); this._dgRenderSection(); } break;
        case 'alarm-hist': this._dgAlarmHistory(); break;
        case 'mb-read': this._dgModbus('read'); break;
        case 'mb-write': this._dgModbus('write'); break;
        case 'prefix-save': { const v = (this._el('dgPrefix').value || '').trim(); DG_LS.set('bms_diag_prefix', v); this._dgPrefixAuto = null; this._dgToast(v ? `Prefiks encji ustawiony: ${v}` : 'Prefiks: automatyczny'); this._dgRenderSection(); break; }
        default: break;
      }
    },
    _dgSectionRefresh() { this._dgRenderSection(); },
    _dgOnInput(e, isChange) {
      const t = e.target; const s = this._dgS();
      if (t.dataset && t.dataset.nk !== undefined) { this._dgNtField(t); return; }
      if (t.dataset && t.dataset.modeNum !== undefined) { t.classList.toggle('dirty', String(t.value).trim() !== String(t.dataset.orig || '').trim()); return; }
      if (t.dataset && t.dataset.eid && t.dataset.orig !== undefined) {
        const dirty = !this._dgSame(t.value, t.dataset.orig);
        t.classList.toggle('dirty', dirty);
        if (t.closest && t.closest('#dgTou')) this._dgTouDraw();
        return;
      }
      if (t.id === 'dgCfgQ') { s.cfgQ = t.value; this._dgRefreshCfgList(); }
      else if (t.id === 'dgSenQ') { s.senQ = t.value; this._dgRefreshSensors(); }
      else if (t.id === 'dgAlQ') { s.alQ = t.value; }
      else if (t.id === 'dgChQ') { s.ch.q = t.value; this._dgRefreshSeriesPicker(); }
      else if (t.id === 'dgCmp') { s.ch.compare = t.checked; this._dgChartDraw(); }
      else if (t.dataset && t.dataset.sel !== undefined && isChange) {
        const set = new Set(s.ch.sel); if (t.checked) set.add(t.dataset.sel); else set.delete(t.dataset.sel); s.ch.sel = [...set]; this._dgChartDraw();
      } else if (t.id === 'dgFile' && isChange) this._dgImportFile(t.files && t.files[0]);
    },

    // ---------- modal ----------
    _dgModal(title, bodyHtml, buttons, need) {
      return new Promise(resolve => {
        const host = this._el('dgHost') || this.shadowRoot; const m = document.createElement('div'); m.className = 'dg-modal';
        m.innerHTML = `<div role="dialog" aria-modal="true"><h3>${title}</h3>${bodyHtml}${need ? `<label style="display:flex;gap:8px;margin-top:12px;font-size:13px;align-items:flex-start;"><input type="checkbox" id="dgNeed" style="margin-top:2px;"/> <span>${need}</span></label>` : ''}<div class="acts">${buttons.map(b => `<button class="dg-btn ${b.cls || ''}" data-id="${b.id}">${b.label}</button>`).join('')}</div></div>`;
        host.appendChild(m);
        const done = (id) => { m.remove(); resolve(id); };
        const okBtns = need ? [...m.querySelectorAll('button')].filter(b => b.dataset.id === 'ok') : [];
        if (need) { okBtns.forEach(b => b.disabled = true); m.querySelector('#dgNeed').addEventListener('change', (ev) => okBtns.forEach(b => b.disabled = !ev.target.checked)); }
        m.addEventListener('click', (ev) => { const b = ev.target.closest('button[data-id]'); if (b && !b.disabled) done(b.dataset.id); else if (ev.target === m) done('cancel'); });
      });
    },
    async _dgConfirmChanges(changes, title) {
      const hi = changes.some(c => c.r >= 2 || (c.warn && c.warn.length));
      const rows = changes.map(c => `<tr><td>${dgEsc(c.name)}${c.r >= 2 ? ' <span class="dg-warn">⚠</span>' : ''}</td><td class="from">${dgEsc(this._dgFmt(c.from))}</td><td>→</td><td class="to">${dgEsc(this._dgFmt(c.to))}</td></tr>`).join('');
      const ws = []; changes.forEach(c => (c.warn || []).forEach(w => ws.push(`<b>${dgEsc(c.name)}:</b> ${dgEsc(w)}`)));
      const warn = (changes.some(c => c.r >= 2) ? '<div class="dg-redbox">⚠ Zmiana parametrów oznaczonych ⚠ wpływa na bezpieczeństwo baterii, sieci lub pracy falownika. Upewnij się, że wartości zgadzają się z dokumentacją baterii/operatora.</div>' : '')
        + (ws.length ? `<div class="dg-redbox">${ws.join('<br>')}</div>` : '');
      const id = await this._dgModal(title || 'Potwierdź zmiany', `<table class="dg-diff">${rows}</table>${warn}`, [{ id: 'cancel', label: 'Anuluj', cls: 'sec' }, { id: 'ok', label: `Zapisz do falownika (${changes.length})`, cls: hi ? 'red' : '' }], hi ? 'Rozumiem ryzyko i potwierdzam zapis.' : '');
      return id === 'ok';
    },

    // ---------- reguły bezpieczeństwa wartości ----------
    // Zwraca { err?: string, warn: string[] } — err blokuje zapis, warn wymaga świadomego potwierdzenia.
    _dgCheckValue(eid, value) {
      const out = { warn: [] };
      if (!eid.startsWith('number.')) return out;
      const n = typeof value === 'number' ? value : parseFloat(String(value).replace(',', '.'));
      if (!isFinite(n)) { out.err = 'Wpisz liczbę.'; return out; }
      const st = this._hass.states[eid]; const a = (st && st.attributes) || {};
      const key = this._dgKey(eid) || ''; const def = DG_DEFS[key] || null; const unit = String(a.unit_of_measurement || '');
      const negOk = DG_NEG_OK.includes(key) || /°|mv/i.test(unit);
      const minAttr = a.min != null && a.min !== '' ? Number(a.min) : null;
      if (n < 0 && !negOk) {
        if (def || !(minAttr !== null && minAttr < 0)) {
          out.err = (def && def.negMsg) || 'Wartość ujemna jest zablokowana — rejestry falownika są zwykle bez znaku (np. −20 zapisze się jako ≈65 516). Wpisz 0 lub wartość dodatnią.';
          return out;
        }
        out.warn.push('Wartość ujemna w parametrze, którego panel nie rozpoznaje. Rejestr może być bez znaku — sprawdź w dokumentacji i po zapisie obserwuj kontrolę odczytu.');
      }
      if (unit === '%' && (n < 0 || n > 100)) { out.err = 'Wartość w % musi mieścić się w zakresie 0–100.'; return out; }
      if (def && def.soft && n > def.soft) out.warn.push(`Wartość ${this._dgFmt(n)} ${unit} jest nietypowo duża (typowo do ${def.soft} ${unit}). Sprawdź dokumentację.`);
      const cur = parseFloat(String(st && st.state).replace(',', '.'));
      if (isFinite(cur) && cur > 0 && n >= cur * 10 && n - cur >= 100) out.warn.push(`Nowa wartość jest ${Math.round(n / cur)}× większa niż obecna (${this._dgFmt(cur)} → ${this._dgFmt(n)}).`);
      if (n > 65535) out.warn.push('Wartość przekracza 65 535 — typowy zakres rejestru 16-bitowego.');
      return out;
    },
    // Odczyt, który wygląda na błąd rejestru (np. 65 515 W po zapisie −20)
    _dgSuspect(eid) {
      if (!eid.startsWith('number.')) return '';
      const st = this._hass.states[eid]; if (!st) return ''; const n = parseFloat(st.state); if (!isFinite(n)) return '';
      const a = st.attributes || {}; const key = this._dgKey(eid) || ''; const def = DG_DEFS[key] || null;
      if (a.min != null && a.min !== '' && n < Number(a.min)) return `odczyt ${this._dgFmt(n)} poniżej zakresu encji (min ${a.min})`;
      if (a.max != null && a.max !== '' && n > Number(a.max)) return `odczyt ${this._dgFmt(n)} powyżej zakresu encji (maks. ${a.max})`;
      if (def && def.soft && n > def.soft * 5) return `odczyt ${this._dgFmt(n)} jest podejrzanie duży (typowo do ${def.soft}) — możliwy błąd znaku rejestru`;
      return '';
    },

    // ---------- kontrola po zapisie (60 s, 3 min, 6 min) i alarmy ----------
    _dgWatchAdd(c, from) {
      if (c.eid.startsWith('button.')) return;
      const rec = { eid: c.eid, name: c.name, to: c.to, prev: from, ts: Date.now(), done: 0 };
      const w = DG_LS.get('bms_diag_watch', []).filter(x => x.eid !== c.eid);
      w.push(rec);
      DG_LS.set('bms_diag_watch', w.slice(-30));
      // Kontrolę po zapisie prowadzi też integracja w HA (działa, gdy karta jest zamknięta, i wysyła powiadomienie).
      // Karta zostaje awaryjnym źródłem kontroli, gdy usługa jest niedostępna.
      const numeric = !isNaN(Number(c.to)) && String(c.to).trim() !== '';
      dgCall(this, 'watch_write', { entity_id: c.eid, expected: numeric ? Number(c.to) : String(c.to), label: c.name, tolerance: 0.01,
        previous: (from === '' || from == null) ? undefined : (isNaN(Number(from)) ? String(from) : Number(from)), source: 'Diagnostyka' }, true)
        .then((res) => {
          const id = res && res.response && res.response.item && res.response.item.id;
          if (!id) return;
          const cur = DG_LS.get('bms_diag_watch', []); const r = cur.find(x => x.eid === rec.eid && x.ts === rec.ts);
          if (r) { r.srv = id; DG_LS.set('bms_diag_watch', cur); }
        })
        .catch((err) => { rec.srvErr = dgErrText(err); this._dgToast('ℹ Kontrola po zapisie działa tylko przy otwartej karcie (usługa w HA niedostępna: ' + rec.srvErr + ').', true); });
    },
    _dgBackendWatches() {
      const st = this._hass && this._hass.states[this._eid('sensor', 'monitor_status')];
      const w = st && st.attributes && st.attributes.watches;
      return Array.isArray(w) ? w : null;
    },
    _dgWatchCheck() {
      if (!this._hass) return;
      const w = DG_LS.get('bms_diag_watch', []); if (!w.length) return;
      const now = Date.now(); const TH = [60e3, 180e3, 360e3]; const keep = []; let alarmed = false;
      const log = DG_LS.get('bms_diag_log', []);
      const srv = this._dgBackendWatches();
      w.forEach(e => {
        // użytkownik zmienił parametr ponownie — ta kontrola jest nieaktualna
        if (log.some(r => r.eid === e.eid && r.ts > e.ts + 500)) return;
        // kontrola prowadzona przez integrację: korzystamy z jej wyniku (karta nie musi być otwarta przez 6 minut)
        const it = e.srv && srv ? srv.find(x => x.id === e.srv) : null;
        if (it && it.status === 'ok') { this._dgMarkLog(e, 'ok'); return; }
        if (it && it.status === 'drift') {
          const last = (it.checks || []).slice(-1)[0] || {};
          const al = DG_LS.get('bms_diag_alarms', []).filter(x => x.eid !== e.eid);
          al.unshift({ ts: now, eid: e.eid, name: e.name, wrote: e.to, read: last.value, prev: e.prev });
          DG_LS.set('bms_diag_alarms', al.slice(0, 10)); alarmed = true;
          this._dgMarkLog(e, 'drift'); return;
        }
        if (it && it.status === 'pending') { keep.push(e); return; }
        const due = TH.filter((t, i) => i >= e.done && now - e.ts >= t).length;
        if (!due) { keep.push(e); return; }
        const st = this._hass.states[e.eid]; const cur = st ? st.state : '';
        if (!st || cur === 'unavailable' || cur === 'unknown') { if (now - e.ts < 15 * 60e3) keep.push(e); return; }
        if (!this._dgSame(cur, e.to)) {
          const al = DG_LS.get('bms_diag_alarms', []).filter(x => x.eid !== e.eid);
          al.unshift({ ts: now, eid: e.eid, name: e.name, wrote: e.to, read: cur, prev: e.prev });
          DG_LS.set('bms_diag_alarms', al.slice(0, 10)); alarmed = true;
          this._dgMarkLog(e, 'drift'); return;
        }
        e.done += due;
        if (e.done >= TH.length) this._dgMarkLog(e, 'ok'); else keep.push(e);
      });
      DG_LS.set('bms_diag_watch', keep);
      if (alarmed) { this._dgRenderAlarmBox(); this._dgSyncTab(); this._dgToast('⚠ Falownik zmienił wartość po zapisie — szczegóły u góry zakładki.', true); }
    },
    _dgMarkLog(e, v) {
      const log = DG_LS.get('bms_diag_log', []); const r = log.find(x => x.eid === e.eid && Math.abs(x.ts - e.ts) < 120e3);
      if (r) { r.ver = v; DG_LS.set('bms_diag_log', log); }
    },
    _dgAlarmHtml() {
      const al = DG_LS.get('bms_diag_alarms', []); if (!al.length) return '';
      const rows = al.map((a, i) => `<div class="a">⚠ <b>${dgEsc(a.name)}</b>: zapisano <b>${dgEsc(this._dgFmt(a.wrote))}</b>, a falownik raportuje <b class="dg-bad">${dgEsc(this._dgFmt(a.read))}</b> (${new Date(a.ts).toLocaleTimeString('pl-PL')}). Poprzednia wartość: ${dgEsc(this._dgFmt(a.prev))}.
        <div class="acts"><button class="dg-btn red sm" data-act="alarm-restore" data-i="${i}">Przywróć ${dgEsc(this._dgFmt(a.prev))}</button><button class="dg-btn sec sm" data-act="alarm-dismiss" data-i="${i}">Zamknij</button></div></div>`).join('');
      return `<div class="dg-alarm"><b>Kontrola po zapisie wykryła rozbieżność</b><div class="dg-muted" style="margin:2px 0 4px;">Wartość zmieniła się po zapisie (rejestr falownika, automatyka lub ktoś inny). Sprawdź i w razie potrzeby przywróć poprzednią.</div>${rows}</div>`;
    },
    _dgRenderAlarmBox() { const b = this._el('dgAlarmBox'); if (b) b.innerHTML = this._dgAlarmHtml(); },
    async _dgAlarmRestore(i) {
      const al = DG_LS.get('bms_diag_alarms', []); const a = al[i]; if (!a) return;
      const st = this._hass.states[a.eid]; if (!st) { this._dgToast('Encja już nie istnieje.', true); return; }
      const chk = this._dgCheckValue(a.eid, a.prev);
      if (chk.err || a.prev === '' || a.prev === 'unknown' || a.prev === 'unavailable') { this._dgToast('❌ Nie można przywrócić: ' + (chk.err || 'brak poprzedniej wartości') + ' Ustaw wartość ręcznie.', true); return; }
      const ch = [{ eid: a.eid, name: a.name, from: st.state, to: a.prev, r: 2, warn: chk.warn }];
      if (!(await this._dgConfirmChanges(ch, 'Przywróć poprzednią wartość'))) return;
      await this._dgApply(ch, 'przywrócenie po alarmie');
      const rest = DG_LS.get('bms_diag_alarms', []).filter(x => x.eid !== a.eid); DG_LS.set('bms_diag_alarms', rest); this._dgRenderAlarmBox();
    },

    // ---------- zapis ----------
    _dgNormTime(v) { const m = String(v).match(/^(\d{1,2}):(\d{2})/); return m ? `${m[1].padStart(2, '0')}:${m[2]}:00` : v; },
    async _dgWrite(eid, to) {
      const dom = eid.slice(0, eid.indexOf('.')); const h = this._hass;
      if (dom === 'number') return h.callService('number', 'set_value', { entity_id: eid, value: parseFloat(String(to).replace(',', '.')) });
      if (dom === 'select') return h.callService('select', 'select_option', { entity_id: eid, option: to });
      if (dom === 'switch') return h.callService('switch', to === 'on' ? 'turn_on' : 'turn_off', { entity_id: eid });
      if (dom === 'time') return h.callService('time', 'set_value', { entity_id: eid, time: this._dgNormTime(to) });
      if (dom === 'button') return h.callService('button', 'press', { entity_id: eid });
      throw new Error('Nieobsługiwana domena: ' + dom);
    },
    async _dgWaitFor(eid, to, ms) {
      const t0 = Date.now();
      while (Date.now() - t0 < ms) { if (this._dgSame(this._dgVal(eid), to)) return true; await dgSleep(500); }
      return false;
    },
    _dgSnapshot() {
      const out = {}; const st = this._hass.states;
      this._dgCfgEntities().concat(this._dgTouEntities()).forEach(c => {
        if (c.dom === 'button') return; const v = st[c.eid] && st[c.eid].state;
        if (v == null || v === 'unavailable' || v === 'unknown') return; out[c.eid] = v;
      });
      return out;
    },
    _dgAutoBackup(label) {
      const arr = DG_LS.get('bms_diag_auto', []); arr.unshift({ ts: Date.now(), label: label || 'zmiana', values: this._dgSnapshot() });
      DG_LS.set('bms_diag_auto', arr.slice(0, 8));
    },
    _dgLogAdd(rec) {
      const arr = DG_LS.get('bms_diag_log', []); const u = this._hass.user;
      arr.unshift(Object.assign({ ts: Date.now(), user: u ? u.name : '' }, rec)); DG_LS.set('bms_diag_log', arr.slice(0, 300));
    },
    async _dgApply(changes, label) {
      const s = this._dgS(); if (s.busy) { this._dgToast('Trwa inny zapis — poczekaj.', true); return []; }
      s.busy = true; const res = [];
      try {
        this._dgAutoBackup(label);
        const order = { number: 1, select: 2, time: 3, switch: 4, button: 5 };
        const list = changes.slice().sort((a, b) => order[a.eid.split('.')[0]] - order[b.eid.split('.')[0]]);
        for (let i = 0; i < list.length; i++) {
          const c = list[i]; const from = this._dgVal(c.eid);
          this._dgToast(`Zapisuję ${i + 1}/${list.length}: ${c.name}…`);
          try {
            await this._dgWrite(c.eid, c.to);
            const ok = c.eid.startsWith('button.') ? true : await this._dgWaitFor(c.eid, c.to, 15000);
            this._dgLogAdd({ eid: c.eid, name: c.name, from, to: c.to, ok, label, ver: ok && !c.eid.startsWith('button.') ? 'pending' : undefined });
            if (ok) this._dgWatchAdd(c, from);
            res.push({ ok, c });
          } catch (e) {
            this._dgLogAdd({ eid: c.eid, name: c.name, from, to: c.to, ok: false, err: String(e && e.message || e), label });
            res.push({ ok: false, c, err: e }); break;
          }
        }
      } finally { s.busy = false; }
      const bad = res.filter(r => !r.ok);
      if (!res.length) return res;
      if (!bad.length) this._dgToast(`✅ Zapisano ${res.length} ${res.length === 1 ? 'parametr' : 'parametry'} — HA widzi nową wartość. Kontrola odczytu z falownika po 1, 3 i 6 min (alarm, jeśli wartość się zmieni).`);
      else this._dgToast(`⚠ ${res.length - bad.length}/${res.length} potwierdzone. Brak potwierdzenia: ${bad.map(b => b.c.name).join(', ')}. Odczyt może odświeżyć się za kilkadziesiąt sekund — sprawdź ponownie.`, true);
      this._dgRenderSection();
      return res;
    },
    _dgCollectDirty(scope) {
      const out = [];
      (scope || this._el('dgBody')).querySelectorAll('[data-eid][data-orig]').forEach(inp => {
        if (inp.disabled) return; const orig = inp.dataset.orig; let v = inp.value;
        if (this._dgSame(v, orig)) return;
        const eid = inp.dataset.eid; const st = this._hass.states[eid]; const a = (st && st.attributes) || {}; let warn = [];
        if (eid.startsWith('number.')) {
          const n = parseFloat(String(v).replace(',', '.'));
          if (isNaN(n)) { out.push({ eid, err: 'Wpisz liczbę.' }); return; }
          if (a.min != null && n < Number(a.min)) { out.push({ eid, err: `Min. ${a.min}` }); return; }
          if (a.max != null && n > Number(a.max)) { out.push({ eid, err: `Maks. ${a.max}` }); return; }
          const step = Number(a.step);
          if (step > 0) { const base = a.min != null ? Number(a.min) : 0; const q = (n - base) / step; if (Math.abs(q - Math.round(q)) > 1e-6) { out.push({ eid, err: `Krok ${a.step}` }); return; } }
          const chk = this._dgCheckValue(eid, n);
          if (chk.err) { out.push({ eid, err: chk.err }); return; }
          v = n; warn = chk.warn;
        }
        const key = this._dgKey(eid) || '';
        out.push({ eid, name: this._dgName(eid, st), from: orig, to: v, r: this._dgRisk(key), warn });
      });
      return out;
    },
    async _dgSaveDirty(scope) {
      const all = this._dgCollectDirty(scope);
      const errs = all.filter(x => x.err); const changes = all.filter(x => !x.err);
      if (errs.length) { this._dgToast('❌ ' + errs.map(e => `${this._dgName(e.eid, this._hass.states[e.eid])}: ${e.err}`).join(' · '), true); return; }
      if (!changes.length) { this._dgToast('Brak zmian do zapisania.'); return; }
      if (!(await this._dgConfirmChanges(changes))) return;
      await this._dgApply(changes, 'ręczna zmiana');
    },
    async _dgToggle(eid) {
      const st = this._hass.states[eid]; if (!st || st.state === 'unavailable') return;
      const to = st.state === 'on' ? 'off' : 'on'; const key = this._dgKey(eid) || '';
      const ch = [{ eid, name: this._dgName(eid, st), from: st.state === 'on' ? 'włączone' : 'wyłączone', to: to, r: this._dgRisk(key) }];
      const shown = [{ ...ch[0], to: to === 'on' ? 'włączone' : 'wyłączone' }];
      if (!(await this._dgConfirmChanges(shown))) return;
      await this._dgApply(ch, 'przełącznik');
    },
    async _dgClearLoadHist() {
      const eid = this._eid('button', 'wyczysc_historie_zuzycia'); const st = this._hass.states[eid];
      if (!st || st.state === 'unavailable') { this._dgToast('Przycisk niedostępny — zaktualizuj integrację EMS komp-dec.', true); return; }
      const id = await this._dgModal('Wyczyścić historię zużycia?',
        '<p class="dg-muted">Skasuje zebrane sumy dzienne, profile godzinowe, historię prognoz i sezonowość. Zbieranie zacznie się od zera: prognoza zużycia pojawi się po 5 pełnych dniach, profil godzinowy po 3. Do tego czasu planer pracuje bez prognozy zużycia. <b>Operacji nie da się cofnąć.</b></p>',
        [{ id: 'cancel', label: 'Anuluj', cls: 'sec' }, { id: 'ok', label: 'Wyczyść historię', cls: 'red' }], 'Rozumiem, że historia zużycia zostanie trwale skasowana.');
      if (id !== 'ok') return;
      await this._dgApply([{ eid, name: 'Wyczyść historię zużycia', to: 'press' }], 'czyszczenie historii zużycia');
    },
    async _dgResetPvLearn() {
      const eid = this._eid('button', 'wyzeruj_korekte_pv'); const st = this._hass.states[eid];
      if (!st || st.state === 'unavailable') { this._dgToast('Przycisk niedostępny — zaktualizuj integrację EMS komp-dec.', true); return; }
      const id = await this._dgModal('Wyzerować naukę korekty prognozy PV?',
        '<p class="dg-muted">Skasuje zapamiętane prognozy PV z poprzednich dni, z których liczony jest współczynnik korekty. Korekta wróci do ×1 i zacznie uczyć się od nowa (potrzeba ok. 5 dni). Użyj po zmianie ustawień źródła prognozy (np. Solcast przełączony z wariantu pesymistycznego na środkowy) — inaczej stara korekta zawyżałaby nową prognozę. Produkcja z poprzednich dni zostaje.</p>',
        [{ id: 'cancel', label: 'Anuluj', cls: 'sec' }, { id: 'ok', label: 'Wyzeruj naukę', cls: 'red' }], 'Rozumiem, że korekta prognozy PV zacznie się uczyć od zera.');
      if (id !== 'ok') return;
      await this._dgApply([{ eid, name: 'Wyzeruj naukę korekty prognozy PV', to: 'press' }], 'zerowanie nauki korekty PV');
    },
    // karta „Prognoza PV”: używane źródło, porównanie źródeł, wariant encji Solcast, zerowanie nauki korekty
    _dgPvCard() {
      const a = (this._rsAttrs && this._rsAttrs()) || {};
      const f = (v) => (typeof v === 'number' && isFinite(v)) ? v.toFixed(1).replace('.', ',') + ' kWh' : '—';
      const d0 = Array.isArray(a.pv_daily) ? a.pv_daily[0] : null;
      const src = Array.isArray(a.pv_sources) ? a.pv_sources : [];
      const rows = src.map((s) => `<tr><td>${dgEsc(s.name)}${s.name === a.pv_forecast_source ? ' <span class="dg-muted">(używane)</span>' : ''}</td><td>${f(s.today)}</td><td>${f(s.tomorrow)}</td></tr>`).join('');
      const variant = a.pv_entity_variant
        ? `<div class="dg-warn" id="dgPvVariant">⚠️ Encja Solcast pokazuje wariant ${a.pv_entity_variant === 'estimate10' ? 'pesymistyczny' : 'optymistyczny'} (${dgEsc(a.pv_entity_variant)}). EMS liczy sumę dnia z prognozy środkowej (dane godzinowe), ale w integracji Solcast warto ustawić zwykły „estimate”.</div>` : '';
      const corr = d0 && typeof d0.factor === 'number' ? `Dziś: surowa ${f(d0.raw)} · korekta ×${d0.factor.toFixed(2).replace('.', ',')} z ${d0.n || 0} dni → ${f(d0.kwh)}.` : 'Korekta: brak danych.';
      return `<div class="dg-card" id="dgPvCard"><h4>Prognoza PV</h4><div class="sub">Źródło używane przez plan: <b>${dgEsc(a.pv_forecast_source || 'brak')}</b>. ${corr}</div>
        ${variant}
        ${rows ? `<table class="dg-tbl" id="dgPvSrc"><thead><tr><th>Źródło (bez korekty)</th><th>Dziś</th><th>Jutro</th></tr></thead><tbody>${rows}</tbody></table>
          ${src.length > 1 ? '' : '<div class="sub">Dodaj drugą integrację prognozy (Solcast albo Forecast.Solar), aby porównać źródła.</div>'}` : ''}
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px;"><button class="dg-btn red" data-act="reset-pv-learn">♻️ Wyzeruj naukę korekty PV…</button></div></div>`;
    },
    async _dgPress(eid) {
      const st = this._hass.states[eid]; if (!st || st.state === 'unavailable') return;
      const key = this._dgKey(eid) || ''; const def = DG_DEFS[key];
      const id = await this._dgModal(`${dgEsc(this._dgName(eid, st))}`, `<p class="dg-muted">${dgEsc(def ? def.h : '')}</p>`, [{ id: 'cancel', label: 'Anuluj', cls: 'sec' }, { id: 'ok', label: 'Wykonaj', cls: 'red' }], 'Rozumiem skutki wykonania tej operacji.');
      if (id !== 'ok') return;
      await this._dgApply([{ eid, name: this._dgName(eid, st), to: 'press' }], 'przycisk');
    },
  });

  Object.assign(BmsPanel.prototype, {
    // ======================= PRZEGLĄD =======================
    _dgPick(sens, re) {
      const rx = new RegExp(re);
      return sens.find(x => rx.test(x.key) && x.st.state !== 'unavailable' && x.st.state !== 'unknown' && x.st.state !== '' && !isNaN(Number(x.st.state)));
    },
    _dgLiveTiles() {
      const sens = this._dgSensors(); const cfg = this._dgCfgEntities();
      const line = (label, x) => `<div class="l"><span>${label}</span><b>${dgEsc(this._dgFmt(x.st.state))}${x.unit ? ' ' + dgEsc(x.unit) : ''}</b></div>`;
      const defs = [
        ['⚡ Moc', [['PV', '^(pv_power|pv_total_power|total_pv_power|total_dc_power)$'], ['Dom', '^(load_power|load_total_power|total_load_power|total_consumption_power)$'], ['Sieć (+import / −eksport)', '^(grid_power|total_grid_power|external_ct_power)$'], ['Bateria (+rozł. / −ład.)', '^battery_power$']]],
        ['☀️ Panele PV', [['PV1 moc', '^pv1_power$'], ['PV1 napięcie', '^pv1_voltage$'], ['PV1 prąd', '^pv1_current$'], ['PV2 moc', '^pv2_power$'], ['PV2 napięcie', '^pv2_voltage$'], ['PV2 prąd', '^pv2_current$'], ['PV3 moc', '^pv3_power$'], ['PV4 moc', '^pv4_power$']]],
        ['🔋 Bateria', [['SOC', '^(battery|battery_soc|soc)$'], ['Napięcie', '^battery_voltage$'], ['Prąd', '^battery_current$'], ['Temperatura', '^battery_temperature$']]],
        ['🌐 Sieć', [['Napięcie L1', '^(grid_voltage_l1|grid_voltage|ac_voltage_l1|grid_l1_voltage)$'], ['Napięcie L2', '^(grid_voltage_l2|ac_voltage_l2|grid_l2_voltage)$'], ['Napięcie L3', '^(grid_voltage_l3|ac_voltage_l3|grid_l3_voltage)$'], ['Częstotliwość', '^(grid_frequency|ac_frequency|frequency)$']]],
      ];
      let html = '';
      // komunikacja
      const real = sens.filter(x => x.key && !x.eid.includes('sensor.bms_'));
      const unav = real.filter(x => x.st.state === 'unavailable').length;
      let newest = 0; real.forEach(x => { const t = Date.parse(x.st.last_updated || ''); if (t > newest) newest = t; });
      const age = newest ? Math.round((Date.now() - newest) / 1000) : null;
      const cls = age == null || unav > real.length / 2 ? 'dg-bad' : age < 150 ? 'dg-ok' : age < 600 ? 'dg-warn' : 'dg-bad';
      html += `<div class="dg-tile"><div class="t">📶 Komunikacja</div><div class="l"><span>Ostatni odczyt</span><b class="${cls}">${age == null ? 'brak' : age < 90 ? age + ' s temu' : Math.round(age / 60) + ' min temu'}</b></div><div class="l"><span>Encje niedostępne</span><b class="${unav ? 'dg-warn' : 'dg-ok'}">${unav} z ${real.length}</b></div></div>`;
      // tryb pracy
      const sel = ['work_mode', 'energy_pattern', 'time_of_use', 'battery_control_mode', 'battery_operation_mode'].map(k => cfg.find(c => c.key === k)).filter(Boolean);
      if (sel.length) html += `<div class="dg-tile"><div class="t">🎛️ Tryb falownika</div>${sel.map(c => `<div class="l"><span>${dgEsc(c.name)}</span><b>${dgEsc(c.st.state)}</b></div>`).join('')}</div>`;
      defs.forEach(([title, lines]) => {
        const got = lines.map(([l, re]) => { const x = this._dgPick(sens, re); return x ? line(l, x) : ''; }).join('');
        if (got) html += `<div class="dg-tile"><div class="t">${title}</div>${got}</div>`;
      });
      const temps = sens.filter(x => /temperature/.test(x.key) && !/^battery_temperature$/.test(x.key) && x.st.state !== 'unavailable' && !isNaN(Number(x.st.state))).slice(0, 5);
      if (temps.length) html += `<div class="dg-tile"><div class="t">🌡️ Temperatury</div>${temps.map(x => line(dgEsc(x.name), x)).join('')}</div>`;
      const alr = this._dgAlarmEntities().filter(a => this._dgAlarmActive(a));
      html += `<div class="dg-tile"><div class="t">🚨 Alarmy</div><div class="l"><span>Aktywne</span><b class="${alr.length ? 'dg-bad' : 'dg-ok'}">${alr.length ? alr.length : 'brak'}</b></div>${alr.slice(0, 3).map(a => `<div class="l"><span>${dgEsc(a.name)}</span><b>${dgEsc(this._dgFmt(a.st.state))}</b></div>`).join('')}</div>`;
      return html;
    },
    _dgSensorTable() {
      const s = this._dgS(); const q = (s.senQ || '').toLowerCase().trim(); const now = Date.now();
      let rows = this._dgSensors().filter(x => !q || (x.name + ' ' + x.eid).toLowerCase().includes(q));
      const total = rows.length; rows = rows.slice(0, 300);
      const age = (x) => { const t = Date.parse(x.st.last_updated || ''); if (!t) return '—'; const d = Math.round((now - t) / 1000); return d < 90 ? d + ' s' : d < 5400 ? Math.round(d / 60) + ' min' : Math.round(d / 3600) + ' h'; };
      return `<table class="dg-tbl stack"><thead><tr><th>Odczyt</th><th class="num">Wartość</th><th class="num">Zmiana</th></tr></thead><tbody>${rows.map(x => `<tr><td>${dgEsc(x.name)}<div class="dg-muted dg-mono" style="font-size:10.5px">${dgEsc(x.eid)}</div></td><td class="num"><b>${dgEsc(this._dgFmt(x.st.state))}</b> ${dgEsc(x.unit)}</td><td class="num dg-muted">${age(x)}</td></tr>`).join('') || '<tr><td colspan="3" class="dg-muted">Brak odczytów pasujących do filtra.</td></tr>'}</tbody></table>${total > 300 ? `<div class="dg-muted">Pokazano 300 z ${total} — zawęź wyszukiwanie.</div>` : ''}`;
    },
    _dgSec_overview() {
      const s = this._dgS();
      return `<div class="dg-card"><h4>Stan falownika na żywo</h4><div class="sub">Prefiks encji: <b>${dgEsc(this._dgPrefix() || '—')}</b> · ${dgEsc(this._dgPrefixSource())} (zmiana: Zaawansowane)</div><div class="dg-tiles" id="dgLive">${this._dgLiveTiles()}</div></div>
        <div class="dg-card"><h4>Wszystkie odczyty</h4><input type="search" id="dgSenQ" placeholder="Szukaj odczytu…" value="${dgEsc(s.senQ)}" style="width:100%;margin-bottom:8px;" /><div id="dgSenList">${this._dgSensorTable()}</div></div>`;
    },
    _dgRefreshSensors() { const el = this._el('dgSenList'); if (el) el.innerHTML = this._dgSensorTable(); },

    // ======================= KONFIGURACJA =======================
    _dgInputHtml(c) {
      const st = c.st; const a = st.attributes || {}; const v = st.state; const un = st.state === 'unavailable';
      const dis = un ? 'disabled' : '';
      if (c.dom === 'number') {
        const val = (v === 'unknown' || un) ? '' : v;
        return `<input type="number" ${a.min != null ? `min="${dgEsc(a.min)}"` : ''} ${a.max != null ? `max="${dgEsc(a.max)}"` : ''} step="${a.step ? dgEsc(a.step) : 'any'}" value="${dgEsc(val)}" data-eid="${c.eid}" data-orig="${dgEsc(val)}" ${dis} />`;
      }
      if (c.dom === 'select') {
        const opts = a.options || []; if (v && !opts.includes(v)) opts.push(v);
        return `<select data-eid="${c.eid}" data-orig="${dgEsc(v)}" ${dis}>${opts.map(o => `<option value="${dgEsc(o)}" ${o === v ? 'selected' : ''}>${dgEsc(o)}</option>`).join('')}</select>`;
      }
      if (c.dom === 'time') {
        const val = String(v).slice(0, 5); return `<input type="time" value="${/^\d\d:\d\d$/.test(val) ? val : ''}" data-eid="${c.eid}" data-orig="${/^\d\d:\d\d$/.test(val) ? val : ''}" ${dis} />`;
      }
      if (c.dom === 'switch') return `<button class="dg-btn sm ${v === 'on' ? 'green' : 'sec'}" data-act="toggle" data-eid="${c.eid}" ${dis}>${v === 'on' ? 'WŁĄCZONE' : 'WYŁĄCZONE'}</button>`;
      return '';
    },
    _dgGuessHint(key) {
      const k = key || '';
      if (/soc/.test(k)) return 'Próg w % SOC baterii.';
      if (/current/.test(k)) return 'Limit prądu (A) — ustaw wg karty baterii/instrukcji falownika.';
      if (/voltage|volt/.test(k)) return 'Próg napięcia (V).';
      if (/power|peak|limit/.test(k)) return 'Limit mocy (W).';
      if (/time|hour|cycle/.test(k)) return 'Parametr czasowy.';
      return '';
    },
    _dgRowHtml(c) {
      const a = c.st.attributes || {}; const un = a.unit_of_measurement || ''; const un2 = c.st.state === 'unavailable';
      const rng = c.dom === 'number' && (a.min != null || a.max != null) ? ` · zakres ${dgEsc(a.min)}–${dgEsc(a.max)}${un ? ' ' + dgEsc(un) : ''}` : '';
      const curTxt = c.dom === 'button' ? '' : this._dgFmt(c.st.state) + (un && !un2 && c.st.state !== 'unknown' ? ' ' + un : '');
      const save = c.dom === 'button' ? `<button class="dg-btn sm red" data-act="press" data-eid="${c.eid}" ${un2 ? 'disabled' : ''}>Wykonaj</button>` : (c.dom === 'switch' ? '' : `<button class="dg-btn sm" data-act="save-row" ${un2 ? 'disabled' : ''}>Zapisz</button>`);
      const d = c.def; const RL = ['ryzyko niskie', 'ryzyko średnie', 'ryzyko wysokie'];
      const hint = d ? d.h : ('Parametr nierozpoznany przez panel (inny model lub wersja integracji). ' + this._dgGuessHint(c.key) + ' Panel nie zna jego bezpiecznego zakresu — stosuje tylko zakres z encji. Zmieniaj wyłącznie wg dokumentacji falownika.');
      const tag = d ? (d.v ? '<span class="dg-ver" title="Opis potwierdzony w instrukcji Deye (seria SG01LP1) — u innych modeli sprawdź własną instrukcję">✓ wg instrukcji</span>' : '<span class="dg-unv" title="Opis ogólny — zakresy i skutki zależą od modelu falownika">opis ogólny</span>') : '';
      const susp = c.dom === 'number' ? this._dgSuspect(c.eid) : '';
      return `<div class="dg-row dg-risk${c.r}" data-scope="row" data-g="${c.g}" data-q="${dgEsc((c.name + ' ' + c.eid + ' ' + (d ? d.h + ' ' + (d.rec || '') : '')).toLowerCase())}">
        <div class="nm">${dgEsc(c.name)}<small>${dgEsc(hint)}${rng} · ${RL[c.r] || RL[2]}${tag}</small>${d && d.rec ? `<div class="dg-rec">💡 ${dgEsc(d.rec)}</div>` : ''}<div class="dg-rwarn" data-susp="${c.eid}" style="${susp ? '' : 'display:none'}">${susp ? '⚠ ' + dgEsc(susp) : ''}</div><div class="eid">${dgEsc(c.eid)}</div></div>
        <div class="cur" data-cur="${c.eid}">${dgEsc(curTxt)}</div><div class="ctl">${this._dgInputHtml(c)}</div><div>${save}</div></div>`;
    },
    _dgSec_config() {
      const s = this._dgS(); const list = this._dgCfgEntities();
      if (!list.length) return `<div class="dg-card"><h4>Konfiguracja falownika</h4><p class="dg-muted">Nie znaleziono encji konfiguracji z prefiksem <b>${dgEsc(this._dgPrefix())}</b> (number/select/switch/time). Zmień prefiks w zakładce Zaawansowane.</p></div>`;
      const chips = DG_GROUPS.filter(([k]) => list.some(c => c.g === k)).map(([k, l]) => `<button class="dg-chip" data-act="cfg-g" data-g="${k}" style="${s.cfgG === k ? 'background:var(--accent);color:#fff;' : ''}">${l}</button>`).join('');
      const groups = DG_GROUPS.map(([k, l]) => { const rows = list.filter(c => c.g === k); if (!rows.length) return ''; return `<div class="dg-gwrap" data-g="${k}"><div class="dg-gtitle">${l}</div>${rows.map(c => this._dgRowHtml(c)).join('')}</div>`; }).join('');
      const cheat = `<details class="dg-card dg-cheat"><summary>📖 Co można ustawiać — ściągawka</summary>${DG_CHEAT.map(([t, x]) => `<div class="it"><b>${t}</b>${dgEsc(x)}</div>`).join('')}
        <div class="it"><b>ℹ️ Różne falowniki</b>Lista parametrów, nazwy i zakresy pochodzą z definicji integracji Solarman dla danego modelu (jednofazowe, trójfazowe niskonapięciowe i wysokonapięciowe mają różne zestawy). Panel pokazuje zakres z encji i nie pozwala wyjść poza niego, blokuje wartości ujemne i ostrzega przed nietypowymi skokami. Parametry, których nie rozpoznaje, traktuje jako ryzykowne. Oznaczenie <span class="dg-ver">✓ wg instrukcji</span> = opis potwierdzony w instrukcji Deye (seria SG01LP1); „opis ogólny” = sprawdź w instrukcji swojego modelu.</div>
        <div class="it"><b>🔁 Kontrola po zapisie</b>Po każdej zmianie panel sprawdza odczyt z falownika po 1, 3 i 6 minutach. Jeśli wartość się zmieni, zobaczysz czerwony alarm z przyciskiem przywrócenia.</div></details>`;
      return cheat + `<div class="dg-card"><h4>Konfiguracja falownika</h4><div class="sub">${list.length} parametrów wykrytych automatycznie. Każda zmiana: potwierdzenie „było → będzie”, wpis do dziennika, automatyczna kopia poprzednich wartości i kontrola odczytu po zapisie. Parametry oznaczone ⚠ wpływają na bezpieczeństwo.</div>
        <input type="search" id="dgCfgQ" placeholder="Szukaj parametru (np. prąd, SOC, generator…)" value="${dgEsc(s.cfgQ)}" style="width:100%;" /><div class="dg-chips">${chips}</div></div>
        <div class="dg-card" id="dgCfgList" data-scope="cfg">${groups}<div class="dg-muted" id="dgCfgNone" style="display:none;">Brak parametrów pasujących do filtra.</div></div>`;
    },
    _dgAfter_config() { this._dgFilterCfg(); },
    _dgRefreshCfgList() { this._dgFilterCfg(); },
    _dgFilterCfg() {
      const s = this._dgS(); const q = (s.cfgQ || '').toLowerCase().trim(); const root = this._el('dgCfgList'); if (!root) return; let shown = 0;
      root.querySelectorAll('.dg-gwrap').forEach(w => {
        let any = 0;
        w.querySelectorAll('.dg-row').forEach(r => { const ok = (!q || r.dataset.q.includes(q)) && (!s.cfgG || r.dataset.g === s.cfgG); r.style.display = ok ? '' : 'none'; if (ok) any++; });
        w.style.display = any ? '' : 'none'; shown += any;
      });
      const none = this._el('dgCfgNone'); if (none) none.style.display = shown ? 'none' : '';
      this.shadowRoot.querySelectorAll('[data-act="cfg-g"]').forEach(b => { const on = b.dataset.g === s.cfgG; b.style.background = on ? 'var(--accent)' : ''; b.style.color = on ? '#fff' : ''; });
    },

    // ======================= STREFY CZASOWE =======================
    _dgTouEntities() {
      const out = []; const st = this._hass.states; const p = this._dgPrefix();
      for (let n = 1; n <= 6; n++) {
        [['time', 'time'], ['number', 'power'], ['number', 'voltage'], ['number', 'soc'], ['select', 'charging']].forEach(([dom, f]) => {
          const eid = `${dom}.${p ? p + "_" : ""}program_${n}_${f}`; if (st[eid]) out.push({ eid, dom, n, f, st: st[eid] });
        });
      }
      return out;
    },
    _dgTouColor(opt) {
      const o = String(opt || '').toLowerCase();
      if (!o || /disab/.test(o)) return '#636366';
      if (/grid/.test(o) && /gen/.test(o)) return '#bf5af2';
      if (/grid/.test(o)) return '#30d158';
      if (/gen/.test(o)) return '#0a84ff';
      return '#ff9f0a';
    },
    _dgTouRead() {
      const root = this._el('dgTou'); const p = this._dgPrefix(); const rows = [];
      for (let n = 1; n <= 6; n++) {
        const get = (dom, f) => {
          const eid = `${dom}.${p ? p + "_" : ""}program_${n}_${f}`;
          const inp = root && root.querySelector(`[data-eid="${eid}"]`);
          if (inp) return inp.value; const st = this._hass.states[eid]; return st ? st.state : '';
        };
        const t = String(get('time', 'time')).match(/^(\d{1,2}):(\d{2})/);
        rows.push({ n, min: t ? (+t[1]) * 60 + (+t[2]) : null, power: get('number', 'power'), soc: get('number', 'soc'), volt: get('number', 'voltage'), ch: get('select', 'charging') });
      }
      return rows;
    },
    _dgTimelineHtml() {
      const rows = this._dgTouRead().filter(r => r.min != null); if (rows.length < 2) return '<div class="dg-muted">Brak danych programów.</div>';
      const segs = [];
      rows.forEach((r, i) => {
        const nxt = rows[(i + 1) % rows.length]; let from = r.min, to = nxt.min; if (to <= from) to += 1440;
        if (to > 1440) { segs.push({ from, to: 1440, r }); segs.push({ from: 0, to: to - 1440, r }); } else segs.push({ from, to, r });
      });
      segs.sort((a, b) => a.from - b.from);
      const now = new Date(); const nm = now.getHours() * 60 + now.getMinutes();
      const html = segs.map(g => { const w = (g.to - g.from) / 14.4; return `<div style="width:${w}%;background:${this._dgTouColor(g.r.ch)}" title="P${g.r.n}: ${dgEsc(g.r.ch)} · SOC ${dgEsc(g.r.soc)}% · ${dgEsc(g.r.power)} W">${w > 15 ? `P${g.r.n} · ${dgEsc(g.r.soc)}%` : (w > 6 ? 'P' + g.r.n : '')}</div>`; }).join('');
      return `<div class="dg-tl">${html}<div class="now" style="left:${nm / 14.4}%" title="teraz"></div></div><div class="dg-ticks"><span>0:00</span><span>6:00</span><span>12:00</span><span>18:00</span><span>24:00</span></div>
        <div class="dg-muted" style="margin-top:6px;"><span style="color:#30d158">■</span> z sieci &nbsp; <span style="color:#0a84ff">■</span> z generatora &nbsp; <span style="color:#bf5af2">■</span> sieć + generator &nbsp; <span style="color:#636366">■</span> bez ładowania &nbsp; │ biała linia = teraz</div>`;
    },
    _dgTouWarnHtml() {
      const rows = this._dgTouRead(); const w = [];
      for (let i = 0; i < rows.length - 1; i++) { if (rows[i].min != null && rows[i + 1].min != null && rows[i + 1].min <= rows[i].min) w.push(`Program ${rows[i + 1].n} startuje o ${String(Math.floor(rows[i + 1].min / 60)).padStart(2, '0')}:${String(rows[i + 1].min % 60).padStart(2, '0')} — nie później niż program ${rows[i].n}. Czasy powinny rosnąć 1→6.`); }
      return w.length ? `<div class="dg-redbox" style="background:rgba(255,159,10,.14);color:var(--orange)">⚠ ${w.map(dgEsc).join('<br>⚠ ')}</div>` : '';
    },
    _dgSec_tou() {
      const ents = this._dgTouEntities(); const p = this._dgPrefix();
      if (!ents.length) return '<div class="dg-card"><h4>Strefy czasowe</h4><p class="dg-muted">Nie znaleziono encji programów (program_1…6) dla prefiksu ' + dgEsc(p) + '.</p></div>';
      const tou = this._hass.states[`select.${p ? p + "_" : ""}time_of_use`];
      const ctl = (dom, n, f) => { const e = ents.find(x => x.dom === dom && x.n === n && x.f === f); return e ? this._dgInputHtml({ eid: e.eid, dom, st: e.st }) : '—'; };
      const rows = [1, 2, 3, 4, 5, 6].map(n => `<tr><td><b>P${n}</b></td><td data-l="Start">${ctl('time', n, 'time')}</td><td data-l="Moc [W]">${ctl('number', n, 'power')}</td><td data-l="Napięcie [V]">${ctl('number', n, 'voltage')}</td><td data-l="SOC docelowy [%]">${ctl('number', n, 'soc')}</td><td data-l="Ładowanie">${ctl('select', n, 'charging')}</td></tr>`).join('');
      return `<div class="dg-card"><h4>Doba w programach</h4><div class="sub">Program N obowiązuje od swojej godziny do startu następnego (po P6 wraca P1). Kolor = źródło ładowania, napis = docelowy SOC.${tou ? ` Harmonogram: <b>${dgEsc(tou.state)}</b>.` : ''}</div><div id="dgTl">${this._dgTimelineHtml()}</div><div id="dgTouWarn">${this._dgTouWarnHtml()}</div></div>
        <div class="dg-card" id="dgTou" data-scope="tou"><h4>Edytor programów 1–6</h4><table class="dg-tbl stack"><thead><tr><th></th><th>Start</th><th>Moc [W]</th><th>Napięcie [V]</th><th>SOC [%]</th><th>Ładowanie</th></tr></thead><tbody>${rows}</tbody></table>
        <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap;"><button class="dg-btn" data-act="save-scope" data-scope="tou">Zapisz zmiany</button><button class="dg-btn sec" data-act="reset-scope">Cofnij edycję</button></div>
        <div class="dg-muted" style="margin-top:8px;">Pola zmienione i niezapisane są podświetlone na pomarańczowo; oś doby pokazuje podgląd przed zapisem.</div></div>`;
    },
    _dgTouDraw() { const a = this._el('dgTl'), b = this._el('dgTouWarn'); if (a) a.innerHTML = this._dgTimelineHtml(); if (b) b.innerHTML = this._dgTouWarnHtml(); },

    // ======================= ALARMY =======================
    _dgAlarmEntities() {
      return this._dgSensors().filter(x => /fault|alarm|warning|error|alert|protect|problem|status/.test(x.key) || (x.dom === 'binary_sensor' && /problem|safety|tamper/.test((x.st.attributes || {}).device_class || '')));
    },
    _dgAlarmActive(a) {
      const v = String(a.st.state).toLowerCase();
      if (['unknown', 'unavailable', '', '0', '0.0', 'off', 'ok', 'normal', 'none', 'no_fault', 'no fault', 'standby', 'waiting', 'on-grid', 'on grid', 'selling', 'stand-by', 'self-test', 'running', 'grid'].includes(v)) return false;
      if (/status|state/.test(a.key) && !/fault|alarm|warn|error/.test(a.key)) return false;
      return true;
    },
    _dgFaultText(v) {
      const codes = String(v).match(/F\d{2}/gi) || []; const out = codes.map(c => DG_FAULTS[c.toUpperCase()] ? `${c.toUpperCase()}: ${DG_FAULTS[c.toUpperCase()]}` : c.toUpperCase());
      return out.join('; ');
    },
    _dgAlarmRows() {
      const list = this._dgAlarmEntities();
      if (!list.length) return '<p class="dg-muted">Nie znaleziono czujników alarmów/błędów dla tego falownika.</p>';
      return `<table class="dg-tbl stack"><thead><tr><th>Czujnik</th><th>Stan</th><th>Opis</th></tr></thead><tbody>${list.map(a => { const act = this._dgAlarmActive(a); return `<tr><td>${dgEsc(a.name)}<div class="dg-muted dg-mono" style="font-size:10.5px">${dgEsc(a.eid)}</div></td><td class="${act ? 'dg-bad' : 'dg-ok'}"><b>${dgEsc(this._dgFmt(a.st.state))}</b> ${dgEsc(a.unit)}</td><td class="dg-muted">${dgEsc(this._dgFaultText(a.st.state)) || (act ? 'aktywny — sprawdź instrukcję falownika' : 'OK')}</td></tr>`; }).join('')}</tbody></table>`;
    },
    _dgSec_alarms() {
      const faults = Object.entries(DG_FAULTS).map(([c, t]) => `<b>${c}</b> ${dgEsc(t)}`).join(' · ');
      return `<div class="dg-card"><h4>Alarmy i błędy — na żywo</h4><div id="dgAlLive">${this._dgAlarmRows()}</div></div>
        <div class="dg-card"><h4>Historia alarmów (30 dni)</h4><div class="sub">Zmiany stanu czujników alarmów z historii Home Assistant.</div><button class="dg-btn sec" data-act="alarm-hist">Pobierz historię</button><div id="dgAlHist" style="margin-top:10px;"></div></div>
        <div class="dg-card"><h4>Kody błędów Deye (skrót)</h4><div class="dg-muted" style="line-height:1.7">${faults}<br><br>Opisy dotyczą hybryd <b>niskonapięciowych</b> Deye (SG01LP1 / SG03LP1 / SG04LP3 / SG05LP1) wg instrukcji producenta. W innych modelach znaczenie bywa inne — np. w wysokonapięciowych HP3: F42 = niezgodne wersje oprogramowania w układzie równoległym, F46 = zbyt niskie napięcie AC, F56 = zbyt niskie napięcie baterii 1; w falownikach sieciowych F29 = przełącznik obciążenia AC. Zawsze sprawdź instrukcję swojego modelu.</div></div>`;
    },
    async _dgAlarmHistory() {
      const box = this._el('dgAlHist'); if (!box) return; box.textContent = 'Pobieranie…';
      const ents = this._dgAlarmEntities().map(a => a.eid); if (!ents.length) { box.textContent = 'Brak czujników alarmów.'; return; }
      try {
        const end = new Date(), start = new Date(end.getTime() - 30 * 86400e3);
        const res = await this._hass.callWS({ type: 'history/history_during_period', start_time: start.toISOString(), end_time: end.toISOString(), entity_ids: ents, minimal_response: true, no_attributes: true, significant_changes_only: false, include_start_time_state: false });
        const ev = [];
        Object.keys(res || {}).forEach(eid => { let prev = null; (res[eid] || []).forEach(it => { const v = it.s !== undefined ? it.s : it.state; const ts = (typeof it.lu === 'number' ? it.lu * 1000 : Date.parse(it.last_updated || it.last_changed)); if (v !== prev) ev.push({ ts, eid, v }); prev = v; }); });
        ev.sort((a, b) => b.ts - a.ts);
        box.innerHTML = ev.length ? `<table class="dg-tbl stack"><thead><tr><th>Czas</th><th>Czujnik</th><th>Stan</th></tr></thead><tbody>${ev.slice(0, 150).map(e => `<tr><td>${new Date(e.ts).toLocaleString('pl-PL')}</td><td>${dgEsc(this._dgName(e.eid, this._hass.states[e.eid]))}</td><td><b>${dgEsc(e.v)}</b> <span class="dg-muted">${dgEsc(this._dgFaultText(e.v))}</span></td></tr>`).join('')}</tbody></table>` : '<span class="dg-ok">Brak zmian stanu alarmów w ostatnich 30 dniach.</span>';
      } catch (err) { box.innerHTML = `<span class="dg-bad">Nie udało się pobrać historii: ${dgEsc(err && err.message || err)}</span>`; }
    },
  });

  Object.assign(BmsPanel.prototype, {
    // ======================= WYKRESY =======================
    _dgDestroyChart() { const ch = this._dgS().ch; if (ch.chart) { try { ch.chart.destroy(); } catch (e) { /* ignore */ } ch.chart = null; } },
    _dgSeriesCands() {
      const out = this._dgSensors().filter(x => x.st.state !== '' && !isNaN(Number(x.st.state)) && x.st.state !== 'unknown' && x.st.state !== 'unavailable' && x.unit);
      const sens = out; const pv = this._dgPick(sens, '^(pv_power|pv_total_power|total_pv_power|total_dc_power)$'); const ld = this._dgPick(sens, '^(load_power|load_total_power|total_load_power|total_consumption_power)$');
      const list = out.map(x => ({ id: x.eid, name: x.name, unit: x.unit, eid: x.eid }));
      if (pv && ld) list.unshift({ id: 'derived:surplus', name: 'Nadwyżka PV − dom (obliczone)', unit: 'kW', derived: true, pv: pv.eid, ld: ld.eid });
      return list;
    },
    _dgUnitGroup(u) { return ({ W: 'Moc', kW: 'Moc', V: 'Napięcia', A: 'Prądy', '%': 'Procenty (SOC itp.)', '°C': 'Temperatury', Hz: 'Częstotliwość', kWh: 'Energia', Wh: 'Energia', Ah: 'Pojemność' })[u] || 'Inne'; },
    _dgSeriesPickerHtml() {
      const s = this._dgS(); const q = (s.ch.q || '').toLowerCase().trim(); const sel = new Set(s.ch.sel);
      const groups = {};
      this._dgSeriesCands().filter(c => !q || (c.name + ' ' + c.id).toLowerCase().includes(q) || sel.has(c.id)).forEach(c => { const g = c.derived ? 'Obliczone' : this._dgUnitGroup(c.unit); (groups[g] = groups[g] || []).push(c); });
      const keys = Object.keys(groups); if (!keys.length) return '<div class="dg-muted">Brak pasujących czujników liczbowych.</div>';
      return keys.map(g => `<div class="gh">${dgEsc(g)}</div>${groups[g].slice(0, 120).map(c => `<label><input type="checkbox" data-sel="${dgEsc(c.id)}" ${sel.has(c.id) ? 'checked' : ''}/> <span>${dgEsc(c.name)}</span><span class="u">${dgEsc(c.unit)}</span></label>`).join('')}`).join('');
    },
    _dgRefreshSeriesPicker() { const el = this._el('dgChSel'); if (el) el.innerHTML = this._dgSeriesPickerHtml(); },
    _dgSec_charts() {
      const s = this._dgS(); const ch = s.ch;
      const presets = [['power', 'Moce (PV, dom, sieć, bateria)'], ['battery', 'Bateria (SOC, V, A, °C)'], ['pv', 'Panele PV (string)'], ['grid', 'Sieć (V, Hz)'], ['temps', 'Temperatury']].map(([k, l]) => `<button class="dg-chip" data-act="preset" data-p="${k}">${l}</button>`).join('');
      return `<div class="dg-card"><h4>Wykresy diagnostyczne</h4>
        <div class="dg-rangebar">${Object.keys(DG_RANGES).map(r => `<button class="${ch.range === r ? 'on' : ''}" data-act="range" data-r="${r}">${r}</button>`).join('')}</div>
        <div class="dg-chips">${presets}</div>
        <div class="dg-chartbox"><canvas id="dgChart"></canvas></div>
        <div id="dgChInfo" class="dg-muted" style="margin-top:6px;">${dgEsc(ch.info)}</div>
        <div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin-top:8px;"><label style="font-size:13px;display:flex;gap:6px;align-items:center;cursor:pointer;"><input type="checkbox" id="dgCmp" ${ch.compare ? 'checked' : ''}/> Porównaj z poprzednim okresem</label><button class="dg-btn sec sm" data-act="chart-go">Odśwież</button><button class="dg-btn sec sm" data-act="chart-csv">Eksport CSV</button></div>
        <div id="dgChSum" style="margin-top:10px;"></div></div>
        <div class="dg-card"><h4>Serie na wykresie</h4><div class="sub">Zaznacz dowolne czujniki. Różne jednostki dostają osobne osie. Do 7 dni dane z historii (pełna rozdzielczość), dłużej — ze statystyk długoterminowych HA (godzinowe/dzienne).</div><input type="search" id="dgChQ" placeholder="Szukaj czujnika…" value="${dgEsc(ch.q)}" style="width:100%;" /><div class="dg-sel" id="dgChSel">${this._dgSeriesPickerHtml()}</div></div>`;
    },
    _dgAfter_charts() {
      const ch = this._dgS().ch;
      if (!ch.sel.length) this._dgPreset('default', true);
      this._dgRefreshSeriesPicker(); this._dgChartDraw();
    },
    _dgPreset(p, silent) {
      const sens = this._dgSensors(); const ch = this._dgS().ch;
      const P = (re) => { const x = this._dgPick(sens, re); return x ? x.eid : null; };
      const all = (re) => sens.filter(x => new RegExp(re).test(x.key) && !isNaN(Number(x.st.state)) && x.st.state !== '' && x.st.state !== 'unavailable').map(x => x.eid);
      let ids = [];
      if (p === 'default' || p === 'power') ids = [P('^(pv_power|pv_total_power|total_pv_power|total_dc_power)$'), P('^(load_power|load_total_power|total_load_power|total_consumption_power)$'), P('^(grid_power|total_grid_power|external_ct_power)$'), P('^battery_power$')];
      if (p === 'default') ids = ids.slice(0, 2).concat([P('^(battery|battery_soc|soc)$')]);
      if (p === 'battery') ids = [P('^(battery|battery_soc|soc)$'), P('^battery_voltage$'), P('^battery_current$'), P('^battery_temperature$')];
      if (p === 'pv') ids = all('^pv[1-4]_(power|voltage|current)$').slice(0, 8);
      if (p === 'grid') ids = all('^(grid_voltage.*|grid_frequency|ac_voltage.*|ac_frequency|frequency|.*_l[123]_voltage)$').slice(0, 6);
      if (p === 'temps') ids = all('temperature').slice(0, 6);
      ids = ids.filter(Boolean);
      if (!ids.length) { if (!silent) this._dgToast('Nie znaleziono pasujących czujników dla tego zestawu.', true); return; }
      ch.sel = ids;
      if (!silent) { this._dgRefreshSeriesPicker(); this._dgChartDraw(); }
    },
    _dgParseHist(arr) {
      return (arr || []).map(it => {
        const ts = typeof it.lc === 'number' ? it.lc * 1000 : typeof it.lu === 'number' ? it.lu * 1000 : Date.parse(it.last_changed || it.last_updated);
        const v = parseFloat(it.s !== undefined ? it.s : it.state); return isNaN(v) || isNaN(ts) ? null : { x: ts, y: v };
      }).filter(Boolean);
    },
    _dgBucket(points, start, end, step) {
      const b = new Map();
      points.forEach(p => { if (p.x > end) return; const k = Math.floor(Math.max(p.x, start) / step) * step; const e = b.get(k) || { s: 0, n: 0 }; e.s += p.y; e.n++; b.set(k, e); });
      return [...b.entries()].sort((a, c) => a[0] - c[0]).map(([x, e]) => ({ x, y: e.s / e.n }));
    },
    async _dgFetch(eids, start, end) {
      const range = this._dgS().ch.range; const out = {}; const src = new Set(); const h = this._hass;
      if (['30d', '90d', '365d'].includes(range)) {
        try {
          const res = await h.callWS({ type: 'recorder/statistics_during_period', start_time: new Date(start).toISOString(), end_time: new Date(end).toISOString(), statistic_ids: eids, period: range === '365d' ? 'day' : 'hour', types: ['mean', 'change', 'max', 'state'] });
          Object.keys(res || {}).forEach(eid => {
            const pts = (res[eid] || []).map(it => { let t = typeof it.start === 'number' ? it.start : Date.parse(it.start); if (t < 1e11) t *= 1000; const v = it.mean != null ? it.mean : (it.change != null ? it.change : (it.state != null ? it.state : it.max)); return v == null || isNaN(t) ? null : { x: t, y: Number(v) }; }).filter(Boolean);
            if (pts.length) { out[eid] = pts; src.add('statystyki'); }
          });
        } catch (e) { /* spadamy do historii */ }
      }
      const missing = eids.filter(e => !(out[e] && out[e].length));
      if (missing.length) {
        const step = Math.max(10e3, Math.round((end - start) / 500));
        const res = await h.callWS({ type: 'history/history_during_period', start_time: new Date(start).toISOString(), end_time: new Date(end).toISOString(), entity_ids: missing, minimal_response: true, no_attributes: true, significant_changes_only: false, include_start_time_state: true });
        missing.forEach(eid => { const pts = this._dgBucket(this._dgParseHist((res || {})[eid]), start, end, step); if (pts.length) { out[eid] = pts; src.add('historia'); } });
      }
      eids.forEach(eid => { const st = h.states[eid]; if (st && st.attributes && st.attributes.unit_of_measurement === 'W' && out[eid]) out[eid] = out[eid].map(p => ({ x: p.x, y: p.y / 1000 })); });
      return { data: out, src: [...src] };
    },
    async _dgChartDraw() {
      const s = this._dgS(); const ch = s.ch; const canvas = this._el('dgChart'); if (!canvas) return;
      const info = (t) => { ch.info = t; const e = this._el('dgChInfo'); if (e) e.textContent = t; };
      if (!this._chartReady()) { info('⏳ Chart.js jeszcze się ładuje… (jeśli to trwa: wgraj pliki do frontend/vendor/ lub sprawdź dostęp do CDN)'); ch.wait = (ch.wait || 0) + 1; if (ch.wait < 30) setTimeout(() => { if (this._activeTab === 'diag' && s.sec === 'charts') this._dgChartDraw(); }, 1500); return; }
      ch.wait = 0; const token = ++ch.req; const cands = this._dgSeriesCands(); const byId = Object.fromEntries(cands.map(c => [c.id, c]));
      const sel = ch.sel.filter(id => byId[id]);
      if (!sel.length) { this._dgDestroyChart(); info('Zaznacz co najmniej jedną serię poniżej.'); return; }
      info('⏳ Pobieranie danych…');
      const need = new Set(); sel.forEach(id => { const c = byId[id]; if (c.derived) { need.add(c.pv); need.add(c.ld); } else need.add(id); });
      const end = Date.now(), span = DG_RANGES[ch.range], start = end - span;
      let main, cmp = null;
      try {
        main = await this._dgFetch([...need], start, end);
        if (ch.compare) cmp = await this._dgFetch([...need].slice(0, 6), start - span, end - span);
      } catch (e) { if (token === ch.req) info('❌ Błąd pobierania danych: ' + (e && e.message || e)); return; }
      if (token !== ch.req) return;
      const derive = (c, d) => { const pv = d.data[c.pv] || [], ld = new Map((d.data[c.ld] || []).map(p => [p.x, p.y])); return pv.filter(p => ld.has(p.x)).map(p => ({ x: p.x, y: p.y - ld.get(p.x) })); };
      const seriesData = (c, d) => c.derived ? derive(c, d) : (d.data[c.id] || []);
      const units = []; const axisOf = (u) => { let i = units.indexOf(u); if (i < 0) { if (units.length >= 4) return 'y3'; units.push(u); i = units.length - 1; } return 'y' + i; };
      const datasets = []; const rows = [];
      sel.forEach((id, i) => {
        const c = byId[id]; const unit = c.unit === 'W' ? 'kW' : c.unit; const color = DG_SERIES_COLORS[i % DG_SERIES_COLORS.length]; const ax = axisOf(unit); const pts = seriesData(c, main);
        datasets.push({ label: `${c.name} [${unit}]`, data: pts, borderColor: color, backgroundColor: color + '33', yAxisID: ax, pointRadius: 0, borderWidth: 1.8, tension: 0.2, spanGaps: true, _unit: unit });
        rows.push({ name: c.name, unit, pts });
        if (cmp) { const p2 = seriesData(c, cmp).map(p => ({ x: p.x + span, y: p.y })); if (p2.length) datasets.push({ label: `${c.name} (poprzedni okres)`, data: p2, borderColor: color, borderDash: [5, 4], yAxisID: ax, pointRadius: 0, borderWidth: 1.2, tension: 0.2, spanGaps: true, _unit: unit }); }
      });
      ch.series = rows.map(r => ({ name: r.name, unit: r.unit, pts: r.pts }));
      this._dgDestroyChart();
      const scales = { x: { type: 'time', min: start, max: end, ticks: { color: TC('muted'), maxRotation: 0 }, grid: { color: TC('grid') } } };
      units.forEach((u, i) => { scales['y' + i] = { type: 'linear', position: i % 2 ? 'right' : 'left', title: { display: true, text: u, color: TC('muted') }, ticks: { color: TC('muted') }, grid: { color: TC('grid'), drawOnChartArea: i === 0 } }; });
      if (datasets.some(d => d.yAxisID === 'y3') && !scales.y3) scales.y3 = { type: 'linear', position: 'right', title: { display: true, text: 'inne', color: TC('muted') }, ticks: { color: TC('muted') }, grid: { drawOnChartArea: false } };
      try {
        ch.chart = new window.Chart(canvas, { type: 'line', data: { datasets }, options: { responsive: true, maintainAspectRatio: false, animation: false, parsing: false, interaction: { mode: 'nearest', axis: 'x', intersect: false }, scales, plugins: { legend: { position: 'bottom', labels: { color: TC('text2'), boxWidth: 12, usePointStyle: true } }, tooltip: { callbacks: { label: (c) => `${c.dataset.label.replace(/ \[.*\]$/, '')}: ${Number(c.parsed.y).toFixed(2)} ${c.dataset._unit || ''}` } } } } });
      } catch (e) { info('❌ Błąd wykresu: ' + (e && e.message || e)); return; }
      ch.last = Date.now();
      const missingN = sel.filter(id => !byId[id].derived && !(main.data[id] && main.data[id].length)).length;
      info(`Zakres ${ch.range} · źródło: ${main.src.join(' + ') || 'brak danych'}${missingN ? ` · ${missingN} serii bez danych w tym okresie` : ''}${ch.compare ? ' · linia przerywana = poprzedni okres' : ''}`);
      const fmt = (v) => (Math.round(v * 100) / 100).toString().replace('.', ',');
      const sum = rows.filter(r => r.pts.length).map(r => { const ys = r.pts.map(p => p.y); const mn = Math.min(...ys), mx = Math.max(...ys), av = ys.reduce((a, b) => a + b, 0) / ys.length; const inc = /kWh|Wh/.test(r.unit) ? fmt(ys[ys.length - 1] - ys[0]) : '—'; return `<tr><td>${dgEsc(r.name)}</td><td class="num">${fmt(mn)}</td><td class="num">${fmt(av)}</td><td class="num">${fmt(mx)}</td><td class="num">${fmt(ys[ys.length - 1])}</td><td class="num">${inc}</td><td>${dgEsc(r.unit)}</td></tr>`; }).join('');
      const sb = this._el('dgChSum'); if (sb) sb.innerHTML = sum ? `<div style="overflow-x:auto"><table class="dg-tbl"><thead><tr><th>Seria</th><th class="num">min</th><th class="num">średnia</th><th class="num">maks.</th><th class="num">ostatnia</th><th class="num">przyrost</th><th>jedn.</th></tr></thead><tbody>${sum}</tbody></table></div>` : '';
    },
    _dgChartCsv() {
      const ch = this._dgS().ch; if (!ch.series || !ch.series.length) { this._dgToast('Najpierw narysuj wykres.', true); return; }
      const lines = ['seria;jednostka;czas;wartosc'];
      ch.series.forEach(r => r.pts.forEach(p => lines.push(`${r.name.replace(/;/g, ',')};${r.unit};${new Date(p.x).toISOString()};${String(p.y).replace('.', ',')}`)));
      this._dgDownload(`bms_diag_${ch.range}_${new Date().toISOString().slice(0, 10)}.csv`, '﻿' + lines.join('\n'), 'text/csv;charset=utf-8');
    },
    _dgDownload(name, text, type) {
      const blob = new Blob([text], { type }); const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name;
      this.shadowRoot.appendChild(a); a.click(); setTimeout(() => { a.remove(); URL.revokeObjectURL(a.href); }, 500);
    },

    // ======================= KOPIE I PROFILE =======================
    _dgSec_backup() {
      const prof = DG_LS.get('bms_diag_profiles', {}); const auto = DG_LS.get('bms_diag_auto', []);
      const pr = Object.keys(prof).map(n => `<tr><td><b>${dgEsc(n)}</b><div class="dg-muted">${new Date(prof[n].ts).toLocaleString('pl-PL')} · ${Object.keys(prof[n].values).length} parametrów</div></td><td style="text-align:right;white-space:nowrap;"><button class="dg-btn sm" data-act="profile-load" data-name="${dgEsc(n)}" data-kind="profile">Wczytaj</button> <button class="dg-btn sm sec" data-act="profile-del" data-name="${dgEsc(n)}">Usuń</button></td></tr>`).join('');
      const au = auto.map((a, i) => `<tr><td>${new Date(a.ts).toLocaleString('pl-PL')}<div class="dg-muted">przed: ${dgEsc(a.label)} · ${Object.keys(a.values).length} parametrów</div></td><td style="text-align:right;"><button class="dg-btn sm sec" data-act="profile-load" data-name="${i}" data-kind="auto">Przywróć</button></td></tr>`).join('');
      return `<div class="dg-card"><h4>Kopia zapasowa konfiguracji</h4><div class="sub">Zapisuje wszystkie parametry (liczby, listy, przełączniki, godziny programów) do pliku. Import pokazuje różnice i pozwala zastosować je jednym kliknięciem.</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;"><button class="dg-btn" data-act="export">⬇ Pobierz plik JSON</button><button class="dg-btn sec" data-act="import-pick">⬆ Wczytaj plik…</button><input type="file" id="dgFile" accept=".json,application/json" style="display:none" /></div></div>
        <div class="dg-card"><h4>Profile (np. zima, lato, awaria)</h4><div class="sub">Zapisane w tej przeglądarce. Do przeniesienia na inne urządzenie użyj pliku JSON.</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px;"><input type="text" id="dgProfName" placeholder="Nazwa profilu" style="flex:1;min-width:160px;" /><button class="dg-btn" data-act="profile-save">Zapisz bieżącą konfigurację</button></div>
        <table class="dg-tbl"><tbody>${pr || '<tr><td class="dg-muted">Brak profili.</td></tr>'}</tbody></table></div>
        <div class="dg-card"><h4>Automatyczne kopie przed zmianami</h4><div class="sub">Przed każdym zapisem robiona jest kopia poprzednich wartości (ostatnie 8).</div><table class="dg-tbl"><tbody>${au || '<tr><td class="dg-muted">Brak kopii.</td></tr>'}</tbody></table></div>`;
    },
    _dgExport() {
      const values = this._dgSnapshot(); const d = new Date();
      const doc = { format: 'bms-deye-config', version: 1, created: d.toISOString(), prefix: this._dgPrefix(), count: Object.keys(values).length, values };
      this._dgDownload(`bms_deye_config_${d.toISOString().slice(0, 16).replace(/[-:T]/g, '')}.json`, JSON.stringify(doc, null, 2), 'application/json');
      this._dgToast(`Zapisano plik z ${doc.count} parametrami.`);
    },
    async _dgImportFile(file) {
      if (!file) return;
      try { const doc = JSON.parse(await file.text()); if (!doc || typeof doc.values !== 'object') throw new Error('To nie jest plik konfiguracji EMS.'); await this._dgApplyValues(doc.values, `Import: ${file.name}`); }
      catch (e) { this._dgToast('❌ ' + (e && e.message || e), true); }
      const f = this._el('dgFile'); if (f) f.value = '';
    },
    async _dgApplyValues(values, title) {
      const st = this._hass.states; const changes = []; const skipped = [];
      Object.keys(values).forEach(eid => {
        const cur = st[eid]; if (!cur || cur.state === 'unavailable') return; if (eid.startsWith('button.')) return;
        if (this._dgSame(cur.state, values[eid])) return;
        const key = this._dgKey(eid) || '';
        const to = values[eid]; if (to === '' || to === 'unknown' || to === 'unavailable') return;
        const chk = this._dgCheckValue(eid, to);
        if (chk.err) { skipped.push(`${this._dgName(eid, cur)} (${this._dgFmt(to)}): ${chk.err}`); return; }
        changes.push({ eid, name: this._dgName(eid, cur), from: cur.state, to, r: this._dgRisk(key), warn: chk.warn });
      });
      if (skipped.length) this._dgToast(`⚠ Pominięto ${skipped.length} wartości niezgodne z zasadami bezpieczeństwa: ${skipped.slice(0, 3).join(' · ')}${skipped.length > 3 ? '…' : ''}`, true);
      if (!changes.length) { if (!skipped.length) this._dgToast('✅ Konfiguracja jest identyczna — nic do zmiany.'); return; }
      if (!(await this._dgConfirmChanges(changes, `${dgEsc(title)} — ${changes.length} różnic`))) return;
      await this._dgApply(changes, title);
    },
    async _dgProfileSave() {
      const inp = this._el('dgProfName'); const name = (inp && inp.value || '').trim(); if (!name) { this._dgToast('Podaj nazwę profilu.', true); return; }
      const prof = DG_LS.get('bms_diag_profiles', {}); prof[name] = { ts: Date.now(), values: this._dgSnapshot() };
      if (!DG_LS.set('bms_diag_profiles', prof)) { this._dgToast('❌ Nie udało się zapisać (brak miejsca w przeglądarce).', true); return; }
      this._dgToast(`Zapisano profil „${name}”.`); this._dgRenderSection();
    },
    async _dgProfileLoad(name, kind) {
      if (kind === 'auto') { const a = DG_LS.get('bms_diag_auto', [])[Number(name)]; if (a) await this._dgApplyValues(a.values, `Przywracanie kopii z ${new Date(a.ts).toLocaleString('pl-PL')}`); return; }
      const p = DG_LS.get('bms_diag_profiles', {})[name]; if (p) await this._dgApplyValues(p.values, `Profil „${name}”`);
    },
    _dgProfileDel(name) { if (!confirm(`Usunąć profil „${name}”?`)) return; const p = DG_LS.get('bms_diag_profiles', {}); delete p[name]; DG_LS.set('bms_diag_profiles', p); this._dgRenderSection(); },

    // ======================= TRYBY I POWIADOMIENIA =======================
    // Przeniesione ze strony EMS: tryb burzowy, urlopowy, powiadomienia i test auto-stosowania. To encje samej integracji (bms_*),
    // nie parametry falownika, więc zapis nie trafia do dziennika zmian falownika ani do kontroli odczytu.
    _dgModesDef() {
      return {
        sw: [
          ['storm_mode', '⛈', 'Tryb burzowy', 'Rezerwa 100%: bateria ładuje się w tanim oknie i nie sprzedaje. Wyłącza się sam po ustawionym czasie.'],
          ['vacation_mode', '🏖', 'Tryb urlopowy', 'Plan zakłada stałe, minimalne zużycie domu zamiast średniej z historii.'],
          ['notifications_enabled', '🔔', 'Powiadomienia', 'Niski SOC, alarm falownika, zmiana parametru po zapisie, brak cen RCE, brak łączności.'],
          ['tabs_top', '⬆️', 'Pasek zakładek na górze', 'Domyślnie pasek zakładek (same ikony) jest przyklejony do dołu ekranu. Włącz, aby wrócić do paska na górze — u wszystkich użytkowników.'],
          ['hide_devices_tab', '🙈', 'Ukryj zakładkę Urządzenia', 'Chowa całą zakładkę „Urządzenia” w panelu u wszystkich użytkowników (dane i sterowanie urządzeń działają dalej).'],
          ['auto_enable_sets', '🔛', 'Auto-włączanie zestawów', 'Gdy plan przewiduje okno (ładowanie z sieci albo sprzedaż), EMS sam włącza przełącznik zestawu — inaczej okno by nie wystartowało. Wyłącz, jeśli wolisz włączać zestawy ręcznie.'],
          ['auto_apply_dry_run', '🧪', 'Auto-stosowanie: tylko podgląd', 'Automat liczy zmiany i zapisuje je w dzienniku, ale niczego nie wysyła do falownika.'],
        ],
        num: [
          ['storm_mode_hours', 'Tryb burzowy: czas trwania', 'h', 1, 'Po tym czasie tryb burzowy wyłącza się sam.'],
          ['vacation_load_w', 'Tryb urlopowy: zużycie domu', 'W', 10, 'Stałe zużycie domu, które plan zakłada zamiast średniej z historii.'],
        ],
      };
    },
    _dgSec_modes() {
      const d = this._dgModesDef();
      const sw = d.sw.map(([k, ic, name, hint]) => {
        const eid = this._eid('switch', k); const st = this._st(eid, 'unavailable'); const on = st === 'on'; const dis = st === 'unavailable' || st === 'unknown';
        return `<div class="dg-row" data-scope="mode"><div class="nm">${ic} ${dgEsc(name)}<small>${dgEsc(hint)}</small><div class="eid">${dgEsc(eid)}</div></div>
          <div class="cur" data-mode-cur="${k}">${dis ? 'niedostępne' : (on ? 'włączone' : 'wyłączone')}</div>
          <div class="ctl"><button class="dg-btn sm ${on ? 'green' : 'sec'}" data-act="mode-sw" data-k="${k}" ${dis ? 'disabled' : ''}>${on ? 'WŁĄCZONE' : 'WYŁĄCZONE'}</button></div><div></div></div>`;
      }).join('');
      const nums = d.num.map(([k, name, unit, step, hint]) => {
        const eid = this._eid('number', k); const st = this._hass.states[eid]; const a = (st && st.attributes) || {}; const v = this._st(eid, ''); const dis = v === '';
        const rng = a.min != null || a.max != null ? ` · zakres ${dgEsc(a.min)}–${dgEsc(a.max)} ${unit}` : '';
        return `<div class="dg-row" data-scope="mode"><div class="nm">${dgEsc(name)}<small>${dgEsc(hint)}${rng}</small><div class="eid">${dgEsc(eid)}</div></div>
          <div class="cur" data-mode-cur="${k}">${dis ? 'niedostępne' : dgEsc(this._dgFmt(v)) + ' ' + unit}</div>
          <div class="ctl"><input type="number" step="${a.step || step}" ${a.min != null ? `min="${dgEsc(a.min)}"` : ''} ${a.max != null ? `max="${dgEsc(a.max)}"` : ''} data-mode-num="${k}" data-orig="${dgEsc(v)}" value="${dgEsc(v)}" ${dis ? 'disabled' : ''} /></div>
          <div><button class="dg-btn sm" data-act="mode-save" data-k="${k}" ${dis ? 'disabled' : ''}>Zapisz</button></div></div>`;
      }).join('');
      return `<div class="dg-card"><h4>Tryby i powiadomienia</h4><div class="sub">Tryb burzowy ładuje baterię do 100% i nie sprzedaje — przydatny przed burzą lub planowaną awarią sieci. Tryb urlopowy obniża prognozę zużycia, więc plan nie rezerwuje energii „na zapas”. Aktywny tryb widać też w pasku statusu na stronie głównej.</div>${sw}${nums}</div>`;
    },
    _dgModesToggle(k) {
      const eid = this._eid('switch', k); const on = this._st(eid) === 'on';
      this._hass.callService('switch', on ? 'turn_off' : 'turn_on', { entity_id: eid })
        .then(() => this._dgToast(`✅ ${on ? 'Wyłączono' : 'Włączono'}`))
        .catch(e => this._dgToast(`❌ ${e && e.message ? e.message : e}`, true));
    },
    _dgModesSave(k) {
      const inp = this._el('dgBody') && this._el('dgBody').querySelector(`input[data-mode-num="${k}"]`); if (!inp || inp.disabled) return;
      const v = parseFloat(String(inp.value).replace(',', '.'));
      if (!isFinite(v)) { this._dgToast('❌ Podaj liczbę.', true); return; }
      const eid = this._eid('number', k); const a = (this._hass.states[eid] && this._hass.states[eid].attributes) || {};
      if (a.min != null && v < Number(a.min)) { this._dgToast(`❌ Najmniejsza dozwolona wartość: ${a.min}.`, true); return; }
      if (a.max != null && v > Number(a.max)) { this._dgToast(`❌ Największa dozwolona wartość: ${a.max}.`, true); return; }
      this._hass.callService('number', 'set_value', { entity_id: eid, value: v })
        .then(() => { inp.dataset.orig = String(v); inp.classList.remove('dirty'); this._dgToast('✅ Zapisano'); })
        .catch(e => this._dgToast(`❌ ${e && e.message ? e.message : e}`, true));
    },
    // odświeżanie bez przebudowy (żeby nie kasować tego, co właśnie wpisujesz)
    _dgModesSync() {
      const body = this._el('dgBody'); if (!body) return; const d = this._dgModesDef();
      d.sw.forEach(([k]) => {
        const st = this._st(this._eid('switch', k), 'unavailable'); const on = st === 'on'; const dis = st === 'unavailable' || st === 'unknown';
        const b = body.querySelector(`[data-act="mode-sw"][data-k="${k}"]`); if (b) { b.textContent = on ? 'WŁĄCZONE' : 'WYŁĄCZONE'; b.classList.toggle('green', on); b.classList.toggle('sec', !on); b.disabled = dis; }
        const c = body.querySelector(`[data-mode-cur="${k}"]`); if (c) c.textContent = dis ? 'niedostępne' : (on ? 'włączone' : 'wyłączone');
      });
      d.num.forEach(([k, , unit]) => {
        const v = this._st(this._eid('number', k), '');
        const c = body.querySelector(`[data-mode-cur="${k}"]`); if (c) c.textContent = v === '' ? 'niedostępne' : this._dgFmt(v) + ' ' + unit;
        const inp = body.querySelector(`input[data-mode-num="${k}"]`);
        if (inp) {
          inp.disabled = v === '';                                   // niedostępność encji obowiązuje zawsze
          if (inp !== this.shadowRoot.activeElement && !inp.classList.contains('dirty')) { if (inp.value !== v) inp.value = v; inp.dataset.orig = v; }   // edytowanego pola nie nadpisujemy
        }
        const sv = body.querySelector(`[data-act="mode-save"][data-k="${k}"]`); if (sv) sv.disabled = v === '';
      });
    },

    // ======================= KREATOR INSTALACJI (moduł dodatków) =======================
    _dgSec_wizard() {
      return `<div class="dg-card"><h4>🧭 Kreator instalacji i test bez zapisu</h4><div id="exWizBox"><div class="dg-muted">Ładowanie…</div></div></div>`;
    },
    _dgAfter_wizard() { if (typeof this._exEnsure === 'function') this._exEnsure(); },

    // ======================= AUTOTEST (tylko odczyt) =======================
    _dgSec_selftest() { return `<div id="dgSt">${this._dgStHtml()}</div>`; },
    _dgAfter_selftest() { const st = this._dgStState(); if (!st.data && !st.loading && !st.err) this._dgStRun(); },
    _dgStState() { const s = this._dgS(); if (!s.st) s.st = { data: null, loading: false, err: '', copied: '' }; return s.st; },
    _dgStPaint() { const box = this._el('dgSt'); if (box && this._dgS().sec === 'selftest') box.innerHTML = this._dgStHtml(); },
    async _dgStRun() {
      const st = this._dgStState(); if (st.loading) return;
      st.loading = true; st.err = ''; st.copied = ''; this._dgStPaint();
      try { const r = await dgCall(this, 'self_test', {}, true); st.data = (r && (r.response || r)) || null; }
      catch (e) { st.err = (e && e.message) ? e.message : String(e); }
      st.loading = false; this._dgStPaint();
    },
    _dgStText() {
      const d = this._dgStState().data; if (!d) return '';
      const ic = { ok: 'OK', warn: 'UWAGA', error: 'BŁĄD' };
      const sm = d.summary || {};
      const lines = [`EMS komp-dec ${d.version || '?'} — autotest ${d.time || ''}`, `Wynik: ${sm.errors || 0} błędów, ${sm.warnings || 0} ostrzeżeń, ${sm.ok || 0} OK`];
      (d.groups || []).forEach((g) => {
        lines.push('', `== ${g.name}`);
        (g.checks || []).forEach((c) => { lines.push(`[${ic[c.status] || c.status}] ${c.title}: ${c.detail}${c.fix && c.status !== 'ok' ? ` → ${c.fix}` : ''}`); });
      });
      const bad = (d.commands || []).filter((c) => !c.ok);
      if (bad.length) { lines.push('', '== Komendy (podgląd)'); bad.forEach((c) => lines.push(`[BŁĄD] ${c.label}: ${c.error || ''}`)); }
      lines.push('', this._dgVerLine().replace(/<[^>]+>/g, '').replace(/&[a-z]+;/g, ' ').trim());
      return lines.join('\n');
    },
    async _dgStCopy() {
      const st = this._dgStState(); const txt = this._dgStText(); if (!txt) return;
      let ok = false;
      try { if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(txt); ok = true; } } catch (e) { ok = false; }
      if (!ok) {
        const ta = this._el('dgStTxt');
        if (ta) { ta.style.display = 'block'; ta.focus(); ta.select(); try { ok = document.execCommand('copy'); } catch (e) { ok = false; } }
      }
      st.copied = ok ? '✅ Skopiowano raport — wklej go w wiadomości.' : 'Zaznacz tekst poniżej i skopiuj go ręcznie.';
      const m = this._el('dgStMsg'); if (m) m.textContent = st.copied;
      if (!ok) { const ta = this._el('dgStTxt'); if (ta) ta.style.display = 'block'; }
    },
    _dgStHtml() {
      const st = this._dgStState();
      const head = `<div class="dg-card"><h4>🩺 Autotest</h4><div class="sub">Sprawdza na żywo falownik, prognozę PV, ceny, wykrywanie zaniku sieci, urządzenia i plan. Tylko odczyt — niczego nie zmienia w falowniku ani w ustawieniach.</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;"><button class="dg-btn" data-act="st-run" ${st.loading ? 'disabled' : ''}>${st.loading ? 'Sprawdzam…' : '▶ Uruchom ponownie'}</button>
        <button class="dg-btn sec" data-act="st-copy" ${st.data ? '' : 'disabled'}>📋 Kopiuj raport</button><span class="dg-muted" id="dgStMsg">${dgEsc(st.copied || '')}</span></div></div>`;
      if (st.err) return head + `<div class="dg-card"><div class="dg-bad">Nie udało się uruchomić autotestu: ${dgEsc(st.err)}</div><div class="dg-muted" style="margin-top:6px;">Wymaga integracji 0.8.5 lub nowszej i konta administratora.</div></div>`;
      if (!st.data) return head + '<div class="dg-card"><div class="dg-muted">Sprawdzam…</div></div>';
      const d = st.data; const sm = d.summary || {};
      const ic = { ok: '✅', warn: '⚠️', error: '❌' };
      const sum = `<div class="dg-card"><b class="${sm.errors ? 'dg-bad' : (sm.warnings ? 'dg-warn' : 'dg-ok')}">${sm.errors ? `❌ ${sm.errors} ${sm.errors === 1 ? 'błąd' : 'błędy/błędów'}` : (sm.warnings ? '⚠️ działa, ale są uwagi' : '✅ wszystko w porządku')}</b>
        <span class="dg-muted"> · ostrzeżeń ${sm.warnings || 0} · OK ${sm.ok || 0} · ${dgEsc(String(d.time || '').replace('T', ' '))}</span></div>`;
      const groups = (d.groups || []).map((g) => {
        const nb = (g.checks || []).filter((c) => c.status !== 'ok').length;
        return `<details class="dg-card" ${nb ? 'open' : ''}><summary style="cursor:pointer;font-weight:600;">${dgEsc(g.name)} <span class="dg-muted" style="font-weight:400;">· ${nb ? `${nb} do sprawdzenia` : 'OK'}</span></summary>
          ${(g.checks || []).map((c) => `<div style="display:flex;gap:8px;padding:7px 0;border-bottom:1px solid var(--line);font-size:12px;line-height:1.45;">
            <span style="flex:none;">${ic[c.status] || '•'}</span><div><b>${dgEsc(c.title)}</b><div>${dgEsc(c.detail)}</div>${c.fix && c.status !== 'ok' ? `<div class="dg-muted">${dgEsc(c.fix)}</div>` : ''}</div></div>`).join('')}</details>`;
      }).join('');
      return head + sum + groups + `<textarea id="dgStTxt" readonly style="display:none;width:100%;height:220px;font-size:11px;margin-top:8px;">${dgEsc(this._dgStText())}</textarea>`;
    },

    // ======================= POWIADOMIENIA (konfigurator) =======================
    _dgSec_notify() {
      return `<div id="dgNt">${this._dgNtHtml()}</div>`;
    },
    _dgAfter_notify() { const s = this._dgS(); if (!s.nt || (!s.nt.data && !s.nt.loading)) this._dgNtLoad(); },
    _dgNtState() { const s = this._dgS(); if (!s.nt) s.nt = { data: null, draft: null, loading: false, err: '', dirty: false }; return s.nt; },
    async _dgNtLoad(force) {
      const nt = this._dgNtState();
      if (nt.dirty && force && !confirm('Odrzucić niezapisane zmiany i wczytać ustawienia z Home Assistant?')) return;
      nt.loading = true; nt.err = ''; this._dgNtPaint();
      try {
        const r = await dgCall(this, 'notify_settings_get', {}, true);
        const d = (r && (r.response || r)) || {};
        nt.data = d; nt.draft = JSON.parse(JSON.stringify(d.settings || { kinds: {}, sched: {} })); nt.dirty = false;
      } catch (e) { nt.err = (e && e.message) ? e.message : String(e); }
      nt.loading = false; this._dgNtPaint();
    },
    _dgNtPaint() { const box = this._el('dgNt'); if (box && this._dgS().sec === 'notify') box.innerHTML = this._dgNtHtml(); },
    _dgNtCdLabel(m) { return ({ 0: 'każde (bez limitu)', 5: 'co 5 min', 15: 'co 15 min', 30: 'co 30 min', 60: 'co 1 h', 180: 'co 3 h', 360: 'co 6 h', 720: 'co 12 h', 1200: 'co 20 h', 1440: 'co 1 dzień', 10080: 'co 7 dni' })[m] || `co ${m} min`; },
    _dgNtHtml() {
      const nt = this._dgNtState();
      if (nt.loading && !nt.data) return '<div class="dg-card"><div class="dg-muted">Wczytuję ustawienia powiadomień…</div></div>';
      if (nt.err && !nt.data) return `<div class="dg-card"><h4>🔔 Powiadomienia</h4><div class="dg-bad">Nie udało się wczytać: ${dgEsc(nt.err)}</div><div class="dg-muted" style="margin:6px 0 10px;">Wymaga integracji 0.8.1 lub nowszej i konta administratora.</div><button class="dg-btn sec sm" data-act="nt-reload">Spróbuj ponownie</button></div>`;
      if (!nt.data) return '<div class="dg-card"><div class="dg-muted">…</div></div>';
      const d = nt.data, dr = nt.draft, k = dr.kinds || {}, sc = dr.sched || {};
      const svc = d.notify_service;
      const head = `<div class="dg-card"><h4>🔔 Powiadomienia</h4>
        <div class="sub">Wybierz, co ma przychodzić, gdzie (telefon albo tylko Home Assistant) i jak często najwyżej. Ustawienia zapisują się w integracji — działają także przy zamkniętej karcie.</div>
        <div class="dg-muted" style="margin-bottom:8px;">Telefon: ${svc ? `<b>${dgEsc(svc)}</b>` : '<span class="dg-bad">nie ustawiono usługi notify — powiadomienia trafiają tylko do HA</span> (EMS komp-dec → Konfiguruj → usługa powiadomień)'} · główny wyłącznik: <b>${d.enabled === false ? 'WYŁĄCZONY' : 'włączony'}</b></div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
          <button class="dg-btn sm" data-act="nt-save" ${nt.dirty ? '' : 'disabled'}>💾 Zapisz${nt.dirty ? ' zmiany' : ''}</button>
          <button class="dg-btn sec sm" data-act="nt-test">📲 Wyślij testowe</button>
          <button class="dg-btn sec sm" data-act="nt-defaults">↺ Domyślne</button>
          <button class="dg-btn sec sm" data-act="nt-reload">⟳ Wczytaj</button>
          <span class="dg-muted" id="dgNtMsg">${nt.dirty ? '⚠ niezapisane zmiany' : ''}</span></div></div>`;
      const q = sc.quiet || {}, dd = sc.daily || {}, ww = sc.weekly || {}, mm = sc.monthly || {};
      const days = ['poniedziałek', 'wtorek', 'środa', 'czwartek', 'piątek', 'sobota', 'niedziela'];
      const sched = `<div class="dg-card"><h4>🌙 Cisza nocna i godziny podsumowań</h4>
        <div class="sub">W ciszy nocnej powiadomienia trafiają tylko do HA — na telefon przychodzą wyłącznie rodzaje z zaznaczonym „w ciszy”.</div>
        <div class="dg-row"><div class="nm">Cisza nocna<small>okno może przechodzić przez północ</small></div><div class="cur"><label><input type="checkbox" data-nk="_sched" data-nf="quiet.on" ${q.on ? 'checked' : ''}/> włączona</label></div>
          <div class="ctl"><input type="time" data-nk="_sched" data-nf="quiet.start" value="${dgEsc(q.start || '22:00')}"/>–<input type="time" data-nk="_sched" data-nf="quiet.end" value="${dgEsc(q.end || '07:00')}"/></div><div></div></div>
        <div class="dg-row"><div class="nm">Podsumowanie dnia<small>włącz je niżej, w grupie „Podsumowania”</small></div><div class="cur">o godzinie</div><div class="ctl"><input type="time" data-nk="_sched" data-nf="daily.time" value="${dgEsc(dd.time || '21:00')}"/></div><div></div></div>
        <div class="dg-row"><div class="nm">Podsumowanie tygodnia</div><div class="cur">dzień i godzina</div><div class="ctl"><select data-nk="_sched" data-nf="weekly.weekday">${days.map((n, i) => `<option value="${i}" ${Number(ww.weekday) === i ? 'selected' : ''}>${n}</option>`).join('')}</select><input type="time" data-nk="_sched" data-nf="weekly.time" value="${dgEsc(ww.time || '20:00')}"/></div><div></div></div>
        <div class="dg-row"><div class="nm">Raport miesięczny<small>za poprzedni miesiąc</small></div><div class="cur">dzień i godzina</div><div class="ctl"><select data-nk="_sched" data-nf="monthly.day">${Array.from({ length: 28 }, (_, i) => `<option value="${i + 1}" ${Number(mm.day) === i + 1 ? 'selected' : ''}>${i + 1}.</option>`).join('')}</select><input type="time" data-nk="_sched" data-nf="monthly.time" value="${dgEsc(mm.time || '08:00')}"/></div><div></div></div></div>`;
      const cds = Array.isArray(d.cooldowns) ? d.cooldowns : [0, 5, 15, 30, 60, 180, 360, 720, 1200, 1440, 10080];
      const groups = (Array.isArray(d.groups) ? d.groups : []).map((g) => {
        const items = (d.catalog || []).filter((c) => c.group === g);
        if (!items.length) return '';
        const rows = items.map((c) => {
          const v = k[c.key] || c.default || {};
          const thr = c.thr ? `<label class="dg-muted" style="white-space:nowrap;">${dgEsc(c.thr.label)} <input type="number" style="width:84px;" step="${dgEsc(c.thr.step)}" min="${dgEsc(c.thr.min)}" max="${dgEsc(c.thr.max)}" data-nk="${dgEsc(c.key)}" data-nf="thr" value="${dgEsc(v.thr != null ? v.thr : c.thr.default)}"/> ${dgEsc(c.thr.unit)}</label>` : '';
          return `<div class="dg-row" data-nt-row="${dgEsc(c.key)}" style="${v.on ? '' : 'opacity:.6;'}"><div class="nm"><label style="cursor:pointer;"><input type="checkbox" data-nk="${dgEsc(c.key)}" data-nf="on" ${v.on ? 'checked' : ''}/> ${dgEsc(c.name)}</label><small>${dgEsc(c.desc)}</small></div>
            <div class="cur"><select data-nk="${dgEsc(c.key)}" data-nf="phone"><option value="1" ${v.phone ? 'selected' : ''}>📱 telefon + HA</option><option value="0" ${v.phone ? '' : 'selected'}>🏠 tylko HA</option></select></div>
            <div class="ctl" style="flex-wrap:wrap;"><select data-nk="${dgEsc(c.key)}" data-nf="cooldown" title="najkrócej co">${cds.map((m) => `<option value="${m}" ${Number(v.cooldown) === m ? 'selected' : ''}>${dgEsc(this._dgNtCdLabel(m))}</option>`).join('')}</select>${thr}</div>
            <div><label class="dg-muted" title="wysyłaj na telefon także w ciszy nocnej" style="white-space:nowrap;"><input type="checkbox" data-nk="${dgEsc(c.key)}" data-nf="quiet_ok" ${v.quiet_ok ? 'checked' : ''}/> w ciszy</label></div></div>`;
        }).join('');
        const on = items.filter((c) => (k[c.key] || c.default || {}).on).length;
        return `<div class="dg-card"><h4>${dgEsc(g)} <span class="dg-muted" style="font-weight:400;font-size:12px;">(${on}/${items.length} włączonych)</span>
          <span style="float:right;"><button class="dg-btn sec sm" data-act="nt-all" data-g="${dgEsc(g)}" data-v="1">wszystkie</button> <button class="dg-btn sec sm" data-act="nt-all" data-g="${dgEsc(g)}" data-v="0">żadne</button></span></h4>${rows}</div>`;
      }).join('');
      return head + sched + groups;
    },
    _dgNtField(t) {
      const nt = this._dgNtState(); if (!nt.draft) return;
      const key = t.dataset.nk, f = t.dataset.nf;
      let val = t.type === 'checkbox' ? !!t.checked : t.value;
      if (key === '_sched') {
        const [a, b] = f.split('.');
        nt.draft.sched = nt.draft.sched || {}; nt.draft.sched[a] = nt.draft.sched[a] || {};
        if (b === 'weekday' || b === 'day') val = Number(val);
        nt.draft.sched[a][b] = val;
      } else {
        nt.draft.kinds = nt.draft.kinds || {}; nt.draft.kinds[key] = nt.draft.kinds[key] || {};
        if (f === 'phone') val = val === '1';
        else if (f === 'cooldown') val = Number(val);
        else if (f === 'thr') { val = parseFloat(String(val).replace(',', '.')); if (!isFinite(val)) return; }
        nt.draft.kinds[key][f] = val;
        if (f === 'on') { const row = this._el('dgNt') && this._el('dgNt').querySelector(`[data-nt-row="${key}"]`); if (row) row.style.opacity = val ? '' : '.6'; }
      }
      nt.dirty = true;
      const m = this._el('dgNtMsg'); if (m) m.textContent = '⚠ niezapisane zmiany';
      const sv = this._el('dgNt') && this._el('dgNt').querySelector('[data-act="nt-save"]'); if (sv) { sv.disabled = false; sv.textContent = '💾 Zapisz zmiany'; }
    },
    _dgNtAll(g, on) {
      const nt = this._dgNtState(); if (!nt.data || !nt.draft) return;
      (nt.data.catalog || []).filter((c) => c.group === g).forEach((c) => { nt.draft.kinds[c.key] = Object.assign({}, nt.draft.kinds[c.key] || c.default, { on }); });
      nt.dirty = true; this._dgNtPaint();
    },
    _dgNtDefaults() {
      const nt = this._dgNtState(); if (!nt.data) return;
      if (!confirm('Przywrócić domyślne ustawienia wszystkich powiadomień? (Zapisz, aby zatwierdzić)')) return;
      const kinds = {}; (nt.data.catalog || []).forEach((c) => { kinds[c.key] = Object.assign({}, c.default, c.thr ? { thr: c.thr.default } : {}); });
      nt.draft = { kinds, sched: { quiet: { on: false, start: '22:00', end: '07:00' }, daily: { time: '21:00' }, weekly: { weekday: 6, time: '20:00' }, monthly: { day: 1, time: '08:00' } } };
      nt.dirty = true; this._dgNtPaint();
    },
    async _dgNtSave() {
      const nt = this._dgNtState(); if (!nt.draft) return;
      try {
        const r = await dgCall(this, 'notify_settings_set', { settings: nt.draft }, true);
        const d = (r && (r.response || r)) || {};
        if (d.settings) { nt.data.settings = d.settings; nt.draft = JSON.parse(JSON.stringify(d.settings)); }
        nt.dirty = false; this._dgNtPaint(); this._dgToast('✅ Zapisano ustawienia powiadomień');
      } catch (e) { this._dgToast(`❌ ${e && e.message ? e.message : e}`, true); }
    },
    async _dgNtTest() {
      try {
        const r = await dgCall(this, 'notify_test', {}, true);
        const d = (r && (r.response || r)) || {};
        this._dgToast(d.phone ? `📲 Wysłano na ${d.notify_service} i do HA — sprawdź telefon` : '🏠 Wysłano tylko do HA — nie ustawiono usługi notify (telefon)');
      } catch (e) { this._dgToast(`❌ ${e && e.message ? e.message : e}`, true); }
    },

    // ======================= DZIENNIK =======================
    _dgSec_log() {
      const log = DG_LS.get('bms_diag_log', []);
      const rows = log.slice(0, 150).map((r, i) => `<tr><td>${new Date(r.ts).toLocaleString('pl-PL')}<div class="dg-muted">${dgEsc(r.user || '')}${r.label ? ' · ' + dgEsc(r.label) : ''}</div></td><td>${dgEsc(r.name || r.eid)}<div class="dg-muted dg-mono" style="font-size:10.5px">${dgEsc(r.eid)}</div></td><td><span class="dg-muted">${dgEsc(this._dgFmt(r.from))}</span> → <b>${dgEsc(this._dgFmt(r.to))}</b></td><td class="${!r.ok || r.ver === 'drift' ? 'dg-bad' : (r.ver === 'pending' ? 'dg-warn' : 'dg-ok')}">${!r.ok ? '⚠ ' + dgEsc(r.err || 'brak potwierdzenia') : (r.ver === 'drift' ? '⚠ wartość zmieniła się po zapisie' : (r.ver === 'pending' ? '⏳ zapisane, trwa kontrola odczytu' : (r.ver === 'ok' ? '✔ kontrola odczytu OK (6 min)' : '✔ zapisane')))}</td><td>${r.ok && r.from != null && r.from !== '' && r.from !== 'unknown' && !String(r.eid).startsWith('button.') ? `<button class="dg-btn sm sec" data-act="log-undo" data-i="${i}">Przywróć</button>` : ''}</td></tr>`).join('');
      return `<div class="dg-card"><h4>Dziennik zmian</h4><div class="sub">Każdy zapis do falownika z tej zakładki (data, kto, było → jest, czy falownik potwierdził). Zapisany w tej przeglądarce (ostatnie 300).</div>
        <table class="dg-tbl stack"><thead><tr><th>Kiedy</th><th>Parametr</th><th>Zmiana</th><th>Status</th><th></th></tr></thead><tbody>${rows || '<tr><td colspan="5" class="dg-muted">Brak wpisów.</td></tr>'}</tbody></table>
        ${log.length ? '<div style="margin-top:10px;"><button class="dg-btn sec sm" data-act="log-clear">Wyczyść dziennik</button></div>' : ''}</div>`;
    },
    async _dgLogUndo(i) {
      const r = DG_LS.get('bms_diag_log', [])[i]; if (!r) return; const st = this._hass.states[r.eid]; if (!st) { this._dgToast('Encja już nie istnieje.', true); return; }
      if (r.from === '' || r.from == null || r.from === 'unknown' || r.from === 'unavailable') { this._dgToast('❌ Brak poprzedniej wartości do przywrócenia.', true); return; }
      const chk = this._dgCheckValue(r.eid, r.from); if (chk.err) { this._dgToast('❌ Nie można cofnąć: ' + chk.err, true); return; }
      const ch = [{ eid: r.eid, name: r.name || r.eid, from: st.state, to: r.from, r: this._dgRisk(this._dgKey(r.eid) || ''), warn: chk.warn }];
      if (!(await this._dgConfirmChanges(ch, 'Przywróć poprzednią wartość'))) return;
      await this._dgApply(ch, 'cofnięcie zmiany');
    },

    // ======================= ZAAWANSOWANE =======================
    async _dgDeviceId() {
      const cfg = this._dgCfgEntities()[0]; if (!cfg) return null;
      const reg = this._hass.entities && this._hass.entities[cfg.eid]; if (reg && reg.device_id) return reg.device_id;
      try { const e = await this._hass.callWS({ type: 'config/entity_registry/get', entity_id: cfg.eid }); return e && e.device_id || null; } catch (err) { return null; }
    },
    _dgSec_adv() {
      const ov = DG_LS.get('bms_diag_prefix', '');
      return `<div class="dg-card"><h4>Historia zużycia</h4><div class="sub">Dane, z których liczona jest prognoza zużycia domu. Wyczyść, jeśli zawierają nierealne dni — zbieranie rozpocznie się od zera.</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;"><button class="dg-btn red" data-act="clear-load-hist">🗑 Wyczyść historię zużycia…</button></div></div>
        ${this._dgPvCard()}
        <div class="dg-card"><h4>Prefiks encji falownika</h4><div class="sub">Aktualny: <b>${dgEsc(this._dgPrefix() || '(brak)')}</b> — ${dgEsc(this._dgPrefixSource())}.${this._dgDevices().length ? ' Wykryte urządzenia Solarman: ' + this._dgDevices().map(d => `<b>${dgEsc(d.prefix || d.dev.slice(0, 6))}</b> (${d.cfg} ustawień, ${d.n} encji)`).join(', ') + '.' : ''} Zmień tylko jeśli encje falownika mają inną nazwę (np. <span class="dg-mono">deye</span> zamiast <span class="dg-mono">inverter</span>).</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;"><input type="text" id="dgPrefix" value="${dgEsc(ov)}" placeholder="auto" style="flex:1;min-width:160px;" /><button class="dg-btn" data-act="prefix-save">Zapisz</button></div></div>
        <div class="dg-card"><h4>Rejestry Modbus (ekspert)</h4><div class="sub">Odczyt i zapis dowolnego rejestru przez usługi integracji Solarman. <b class="dg-bad">Zapis w złym rejestrze może uszkodzić falownik lub baterię.</b> Używaj tylko według dokumentacji producenta.</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;"><input type="text" id="dgMbReg" placeholder="Rejestr (np. 0x0100 lub 256)" style="width:190px;" /><input type="number" id="dgMbQty" value="1" min="1" max="60" style="width:80px;" title="liczba rejestrów (odczyt)" /><input type="text" id="dgMbVal" placeholder="Wartość (zapis)" style="width:140px;" />
        <button class="dg-btn sec" data-act="mb-read">Odczytaj</button><button class="dg-btn red" data-act="mb-write">Zapisz rejestr</button></div><pre id="dgMbOut" class="dg-mono" style="margin:10px 0 0;white-space:pre-wrap;font-size:12px;color:var(--text2);"></pre></div>`;
    },
    // Dwie popularne integracje Solarman (StephanJoubert/home_assistant_solarman oraz davidrapan/ha-solarman) mają
    // INNE nazwy usług i pól (np. read_holding_register + register + count albo read_holding_registers + address + count;
    // write_holding_register + value albo write_multiple_registers + values). Nie zgadujemy — czytamy rejestr usług HA.
    _dgMbSpec(kind, reg, qty, val) {
      const svcs = (this._hass.services && this._hass.services.solarman) || {};
      const names = Object.keys(svcs);
      if (!names.length) return { error: 'Home Assistant nie zgłasza usług integracji Solarman (domena „solarman”). Upewnij się, że integracja Solarman jest załadowana, albo użyj Narzędzi deweloperskich → Działania.' };
      const fieldsOf = (n) => Object.keys((svcs[n] && svcs[n].fields) || {});
      const has = (n, k) => fieldsOf(n).includes(k);
      const firstField = (n, cands, dflt) => cands.find(k => has(n, k)) || (fieldsOf(n).length ? null : dflt);
      let cands;
      if (kind === 'read') cands = qty > 1 ? ['read_holding_registers', 'read_multiple_holding_registers'] : ['read_holding_register', 'read_holding_registers', 'read_multiple_holding_registers'];
      else cands = ['write_holding_register', 'write_multiple_registers', 'write_multiple_holding_registers'];
      const service = cands.find(n => svcs[n]);
      if (!service) return { error: `Nie znaleziono pasującej usługi Solarman. Dostępne: ${names.join(', ')}. Odczyt: ${cands.join(' / ')} — sprawdź nazwy w Narzędziach deweloperskich → Działania.` };
      const devKey = firstField(service, ['device', 'device_id'], 'device');
      const addrKey = firstField(service, ['address', 'register'], /multiple|holding_registers$/.test(service) ? 'address' : 'register');
      if (!devKey || !addrKey) return { error: `Usługa solarman.${service} ma nieoczekiwane pola (${fieldsOf(service).join(', ') || 'brak'}) — użyj Narzędzi deweloperskich → Działania.` };
      const data = { [devKey]: null, [addrKey]: reg };
      let note = '';
      if (kind === 'read') {
        const cntKey = firstField(service, ['count', 'quantity', 'length'], 'count');
        if (qty > 1 && !cntKey) return { error: `Usługa solarman.${service} nie przyjmuje liczby rejestrów — odczytaj pojedynczo.` };
        if (cntKey && (qty > 1 || /multiple|holding_registers$/.test(service))) data[cntKey] = qty;
      } else if (has(service, 'values') || /multiple/.test(service)) {
        data[firstField(service, ['values'], 'values') || 'values'] = [val];
        note = `Zapis przez solarman.${service} (Modbus 0x10, jeden rejestr).`;
      } else {
        const vk = firstField(service, ['value'], 'value');
        if (!vk) return { error: `Usługa solarman.${service} nie ma pola „value” (są: ${fieldsOf(service).join(', ')}).` };
        data[vk] = val;
        note = `Zapis przez solarman.${service} (Modbus 0x06).`;
      }
      const sv = svcs[service] || {};
      return { service, data, devKey, ret: kind === 'read' ? (sv.response ? true : null) : false, note };
    },
    async _dgModbus(kind) {
      const out = this._el('dgMbOut'); const regRaw = (this._el('dgMbReg').value || '').trim(); if (!regRaw) { out.textContent = 'Podaj numer rejestru.'; return; }
      const reg = /^0x/i.test(regRaw) ? parseInt(regRaw, 16) : parseInt(regRaw, 10); if (isNaN(reg) || reg < 0 || reg > 65535) { out.textContent = 'Nieprawidłowy numer rejestru (0–65535).'; return; }
      const qty = Math.max(1, Math.min(60, parseInt(this._el('dgMbQty').value, 10) || 1));
      let val = null;
      if (kind !== 'read') {
        const vraw = (this._el('dgMbVal').value || '').trim(); val = /^0x/i.test(vraw) ? parseInt(vraw, 16) : parseInt(vraw, 10);
        if (isNaN(val)) { out.textContent = 'Podaj wartość do zapisu.'; return; }
        if (val < 0 || val > 65535) { out.textContent = 'Wartość musi być w zakresie 0–65535 (rejestr 16-bitowy bez znaku).'; return; }
      }
      const spec = this._dgMbSpec(kind, reg, qty, val); if (spec.error) { out.textContent = '❌ ' + spec.error; return; }
      const dev = await this._dgDeviceId(); if (!dev) { out.textContent = 'Nie udało się ustalić urządzenia Solarman (device_id).'; return; }
      spec.data[spec.devKey] = dev;
      if (kind !== 'read') {
        const id = await this._dgModal('Zapis rejestru Modbus', `<p>Rejestr <b>${reg}</b> (0x${reg.toString(16)}) ← wartość <b>${val}</b></p><p class="sub">${dgEsc(spec.note)}</p><div class="dg-redbox">Operacja niskopoziomowa, bez walidacji zakresów i bez możliwości automatycznego cofnięcia. Zapis wartości ujemnej jako liczby bez znaku (np. 65516 zamiast −20) może wyłączyć zabezpieczenia lub uszkodzić urządzenie.</div>`, [{ id: 'cancel', label: 'Anuluj', cls: 'sec' }, { id: 'ok', label: 'Zapisz rejestr', cls: 'red' }], 'Wiem, co robię, i biorę odpowiedzialność za zmianę.');
        if (id !== 'ok') return;
        this._dgLogAdd({ eid: `modbus:${reg}`, name: `Rejestr ${reg}`, from: '', to: val, ok: true, label: 'modbus' });
      }
      out.textContent = `⏳ solarman.${spec.service}…`;
      const call = (ret) => this._hass.callWS({ type: 'call_service', domain: 'solarman', service: spec.service, service_data: spec.data, return_response: ret });
      try {
        let res;
        if (spec.ret === null) {      // nie wiadomo, czy usługa zwraca odpowiedź — próbujemy z odpowiedzią, potem bez
          try { res = await call(true); } catch (e1) { if (!/respon/i.test(String(e1 && (e1.message || e1.code) || e1))) throw e1; res = await call(false); out.dataset.noResp = '1'; }
        } else res = await call(spec.ret);
        const body = res && res.response !== undefined ? res.response : null;
        out.textContent = (body !== null ? JSON.stringify(body, null, 2) : (kind === 'read' ? 'Usługa wykonana, ale nie zwróciła wartości w odpowiedzi — odczytaj ją w Narzędziach deweloperskich → Działania (z response_variable) albo z encji.' : 'OK — zapis wysłany.')) + `\n(solarman.${spec.service})`;
      } catch (e) { out.textContent = '❌ ' + (e && e.message || JSON.stringify(e)) + `\n(solarman.${spec.service}; pola: ${Object.keys(spec.data).join(', ')})`; }
    },

    // ======================= ODŚWIEŻANIE =======================
    _dgSyncInputs() {
      const body = this._el('dgBody'); if (!body) return; const act = this.shadowRoot.activeElement; const st = this._hass.states;
      body.querySelectorAll('[data-cur]').forEach(el => {
        const s = st[el.dataset.cur]; if (!s) return; const a = s.attributes || {}; const u = a.unit_of_measurement || '';
        el.textContent = s.state === 'unavailable' ? 'niedostępne' : this._dgFmt(s.state) + (u && s.state !== 'unknown' ? ' ' + u : '');
      });
      body.querySelectorAll('[data-susp]').forEach(w => { const m = this._dgSuspect(w.dataset.susp); w.style.display = m ? '' : 'none'; w.textContent = m ? '⚠ ' + m : ''; });
      body.querySelectorAll('[data-eid][data-orig]').forEach(inp => {
        const s = st[inp.dataset.eid]; if (!s || inp === act || inp.classList.contains('dirty')) return;
        let v = s.state; if (inp.type === 'time') v = String(v).slice(0, 5); if (v === 'unknown' || v === 'unavailable') v = '';
        if (inp.value !== String(v)) { inp.value = v; } inp.dataset.orig = String(v); inp.disabled = s.state === 'unavailable';
      });
      body.querySelectorAll('button[data-act="toggle"]').forEach(b => { const s = st[b.dataset.eid]; if (!s) return; const on = s.state === 'on'; b.textContent = on ? 'WŁĄCZONE' : 'WYŁĄCZONE'; b.classList.toggle('green', on); b.classList.toggle('sec', !on); b.disabled = s.state === 'unavailable'; });
    },
    _dgTick() {
      const s = this._dgS(); if (!s.mounted || !this._dgUnlocked()) return;
      const now = Date.now(); if (s.sec !== 'modes' && now - (s._tickAt || 0) < 1000) return; s._tickAt = now;   // „Tryby” odświeżają się przy każdej zmianie stanu (tanio), reszta co 1 s
      this._dgTickBar();
      if (s.busy) return;
      if (s.sec === 'overview') { const l = this._el('dgLive'); if (l) l.innerHTML = this._dgLiveTiles(); const q = this._el('dgSenQ'); if (!(q && this.shadowRoot.activeElement === q)) this._dgRefreshSensors(); }
      else if (s.sec === 'config') this._dgSyncInputs();
      else if (s.sec === 'tou') { this._dgSyncInputs(); this._dgTouDraw(); }
      else if (s.sec === 'alarms') { const l = this._el('dgAlLive'); if (l) l.innerHTML = this._dgAlarmRows(); }
      else if (s.sec === 'modes') this._dgModesSync();
      else if (s.sec === 'charts' && s.ch.range === '1h' && now - (s.ch.last || 0) > 60000) this._dgChartDraw();
    },
  });
  // <<DIAG-END>>

  };
  install.contract = 1;
  install.version = '0.9.4.3';
  window.__bmsDiagInstall = install;
})();
