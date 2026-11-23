/**
 * EMS Centrum Energii — moduł dodatków (plan 24 h, raport, zdrowie baterii, kreator)
 * Ładowany na żądanie przez bms-panel.js (kontrakt modułu: 1). Nie dodawaj tego pliku do zasobów dashboardu ręcznie.
 */
(function () {
  'use strict';
  const install = function (BmsPanel, shared) {
    const TC = shared.TC;
    const BMS_INFO = { card: shared.version || '', url: shared.urlVersion || '' };
    // =====================================================================
    //  DODATKI: wspólne narzędzia, style i rysowanie (plan 24 h, raport, zdrowie baterii, kreator instalacji)
    //  Dane liczy integracja (sensory plan_curve / monthly_report / battery_health, usługi health_check,
    //  monthly_report, get_plan) — ten moduł tylko je wyświetla, niczego nie zapisuje do falownika.
    // =====================================================================
    const exEsc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const exNum = (v) => (v === null || v === undefined || v === '' || isNaN(Number(v))) ? null : Number(v);
    const exFmt = (v, d, unit) => { const n = exNum(v); return n === null ? '—' : n.toFixed(d == null ? 1 : d).replace('.', ',') + (unit || ''); };
    const exMoney = (v) => { const n = exNum(v); return n === null ? '—' : (n >= 0 ? '+' : '−') + Math.abs(n).toFixed(2).replace('.', ',') + ' zł'; };
    const exErr = (e) => String((e && (e.message || e.code)) || e || 'błąd').slice(0, 200);
    const exCall = (card, service, data) => card._hass.callWS({ type: 'call_service', domain: 'bms_komp_dec', service, service_data: data || {}, return_response: true });
    const exResp = (res) => (res && res.response !== undefined ? res.response : res);
    const exHH = (n) => String(((n % 24) + 24) % 24).padStart(2, '0');

    const EX_CSS = `
      .ex-sum { display:flex; flex-wrap:wrap; gap:8px; margin:0 0 10px; }
      .ex-chip { padding:4px 10px; border-radius:999px; font-size:11px; background:var(--surface); color:var(--text2); }
      .ex-chip.warn { background:rgba(255,159,10,.16); color:var(--orange); }
      .ex-chip.bad { background:rgba(255,69,58,.16); color:var(--red); }
      .ex-chip.ok { background:rgba(48,209,88,.16); color:var(--green); }
      .ex-plan { position:relative; }
      .ex-plan canvas { width:100%; height:250px; display:block; touch-action:pan-y; }
      .ex-tip { position:absolute; z-index:3; pointer-events:none; background:var(--card); color:var(--text); border:1px solid var(--line); border-radius:10px; padding:8px 10px; font-size:11px; line-height:1.5; box-shadow:0 6px 18px rgba(0,0,0,.35); white-space:nowrap; }
      .ex-leg { display:flex; flex-wrap:wrap; gap:6px 14px; font-size:11px; color:var(--muted); margin-top:8px; }
      .ex-leg i { display:inline-block; width:12px; height:8px; border-radius:2px; margin-right:5px; vertical-align:middle; }
      .ex-leg i.line { height:2px; border-radius:0; }
      .ex-leg i.dash { height:0; border-top:2px dashed var(--red); background:none; }
      .ex-lines { margin-top:10px; font-size:12px; color:var(--text2); line-height:1.6; }
      .ex-lines div { padding:2px 0; }
      .ex-prop { display:flex; justify-content:space-between; gap:10px; padding:5px 0; border-bottom:1px solid var(--line); font-size:12px; }
      .ex-prop:last-child { border-bottom:none; }
      .ex-prop .skip { color:var(--muted); }
      .ex-tiles { display:flex; gap:10px; flex-wrap:wrap; }
      .ex-tile { flex:1 1 130px; min-width:120px; background:var(--surface); border-radius:14px; padding:12px 14px; }
      .ex-tile .l { font-size:11px; color:var(--muted); text-transform:uppercase; letter-spacing:.5px; }
      .ex-tile .v { font-size:20px; font-weight:700; margin-top:4px; }
      .ex-tile .s { font-size:11px; color:var(--muted); margin-top:2px; }
      .ex-nav { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:12px; }
      .ex-nav b { font-size:15px; }
      .ex-bars { display:flex; align-items:center; gap:2px; height:80px; margin-top:12px; }
      .ex-note { font-size:11px; color:var(--muted); margin-top:10px; line-height:1.5; }
      .ex-chk { display:flex; gap:10px; padding:8px 0; border-bottom:1px solid var(--line); font-size:12px; line-height:1.45; }
      .ex-chk:last-child { border-bottom:none; }
      .ex-chk .ic { flex:none; width:18px; text-align:center; }
      .ex-chk .fix { color:var(--muted); margin-top:2px; }
      .ex-cmd { background:var(--surface); border-radius:12px; padding:8px 12px; margin-top:8px; font-size:12px; }
      .ex-cmd summary { cursor:pointer; list-style:none; display:flex; gap:8px; align-items:center; }
      .ex-cmd summary::-webkit-details-marker { display:none; }
      .ex-cmd code { font-size:11px; color:var(--muted); word-break:break-all; }
      .ex-cmd .st { padding:3px 0 3px 26px; }
    `;

    Object.assign(BmsPanel.prototype, {
      _exS() {
        if (!this._ex) this._ex = { ins: { data: null, at: 0, loading: false, err: '', period: 'last30', cbusy: false, cmsg: '' }, planOverride: null, rep: { year: null, month: null, data: null, loading: false, err: '' }, wiz: { state: 'idle', data: null, err: '' }, prof: { data: null, at: 0, loading: false, err: '', sel: null, busy: false, msg: '', name: '', icon: '', dFrom: '', dTo: '' }, keys: {} };
        return this._ex;
      },
      _exCss() {
        const root = this.shadowRoot;
        if (!root || root.getElementById('exStyle')) return;
        const st = document.createElement('style'); st.id = 'exStyle'; st.textContent = EX_CSS; root.appendChild(st);
      },
      // wywoływane co ~10 s oraz po zmianie zakładki: każdy fragment sam pilnuje, czy jest widoczny i czy dane się zmieniły
      _exRender() {
        if (!this._hass) return;
        this._exCss();
        this._safe(() => this._exPlan());
        this._safe(() => this._exLog());
        this._safe(() => this._exWiz());
        this._safe(() => this._exProf());
        this._safe(() => this._exPlus());
      },
      _exLog() {
        if (!this._tabNeeds('log')) return;
        this._exInsights();
        this._exReport();
        this._exHealth();
      },
    });

    // =====================================================================
    //  PLAN 24 h — przewidywana krzywa SOC z zaplanowanym ładowaniem z sieci i sprzedażą (liczy integracja)
    // =====================================================================
    const exRanges = (flags) => {
      const out = []; let st = -1;
      for (let i = 0; i <= flags.length; i++) {
        const on = i < flags.length && !!flags[i];
        if (on && st < 0) st = i;
        if (!on && st >= 0) { out.push([st, i]); st = -1; }
      }
      return out;
    };
    const exStartHour = (c) => {
      const m = /T(\d\d):/.exec(String(c.start || ''));
      if (m) return parseInt(m[1], 10);
      const d = new Date(c.start); return isNaN(d) ? 0 : d.getHours();
    };

    Object.assign(BmsPanel.prototype, {
      _exPlanData() {
        const s = this._exS();
        const st = this._hass.states[this._eid('sensor', 'plan_curve')];
        if (!st) return { missing: true };
        const a = st.attributes || {};
        let plan = { mode: a.mode, generated_at: a.generated_at, error: a.error, curve: a.curve, proposals: a.proposals, assumptions: a.assumptions, state: st.state };
        const ov = s.planOverride;
        if (ov && ov.generated_at && (!plan.generated_at || String(ov.generated_at) > String(plan.generated_at))) plan = Object.assign({ state: '' }, ov);
        return { plan };
      },

      _exPlan() {
        const box = this._el('exPlanBox');
        if (!box || (!this._tabNeeds('ems') && !this._tabNeeds('charts'))) return;
        const s = this._exS();
        if (!box.dataset.exBound) {
          box.dataset.exBound = '1';
          box.addEventListener('click', (ev) => {
            const b = ev.target && ev.target.closest ? ev.target.closest('[data-ex="plan-refresh"]') : null;
            if (b) this._exPlanRefresh();
          });
        }
        const d = this._exPlanData();
        const msg = (t, bad) => {
          const k = 'msg:' + t; if (s.keys.plan === k) return; s.keys.plan = k;
          box.innerHTML = `<div class="chart-empty"${bad ? ' style="color:var(--red);"' : ''}>${t}</div>`;
        };
        if (d.missing) { msg('Brak sensora planu — zaktualizuj integrację do wersji z planem 24 h i zrestartuj Home Assistant.', true); return; }
        const p = d.plan, c = p.curve;
        if (p.error) { msg('Plan niedostępny: ' + exEsc(p.error), true); return; }
        if (p.state === 'brak' && !c) { msg('Plan jeszcze nie został policzony — pojawi się w ciągu kilku minut po starcie integracji.'); return; }
        if (!c || !Array.isArray(c.soc) || !c.soc.length) { msg('Plan niedostępny — brak danych (SOC, prognoz PV lub zużycia).', true); return; }

        const key = JSON.stringify([p.generated_at, p.mode, Math.round(box.clientWidth), TC('text'), c.soc.length, c.start]);
        const cv0 = box.querySelector('canvas');
        if (s.keys.plan === key && cv0) { if (s.hover == null) return; }
        else {
          s.keys.plan = key; s.hover = null;
          box.innerHTML = this._exPlanHtml(p, c);
          const cv = box.querySelector('canvas');
          const move = (ev) => {
            const r = cv.getBoundingClientRect(); const n = c.soc.length;
            const padL = this._exPlanPad().l, padR = this._exPlanPad().r;
            const x = ev.clientX - r.left;
            const i = Math.floor((x - padL) / Math.max(1, (r.width - padL - padR) / n));
            s.hover = (i >= 0 && i < n) ? i : null;
            this._exPlanPaint(box, c);
          };
          cv.addEventListener('pointermove', move);
          cv.addEventListener('pointerdown', move);
          cv.addEventListener('pointerleave', () => { s.hover = null; this._exPlanPaint(box, c); });
        }
        this._exPlanPaint(box, c);
      },

      _exPlanPad() { return { l: 34, r: 8, t: 10 }; },

      _exPlanHtml(p, c) {
        const n = c.soc.length, h0 = exStartHour(c);
        const hm = (i) => exHH(h0 + i) + ':00';
        const gen = p.generated_at ? new Date(p.generated_at) : null;
        const genTxt = gen && !isNaN(gen) ? gen.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' }) : '—';
        const chips = [`<span class="ex-chip">Policzono ${exEsc(genTxt)}</span>`, `<span class="ex-chip">SOC teraz ${exFmt(c.soc_now, 0, '%')}</span>`];
        if (p.mode === 'storm') chips.push('<span class="ex-chip warn">⛈ tryb burzowy — cel 100%, bez sprzedaży</span>');
        else if (p.mode === 'vacation') chips.push('<span class="ex-chip">🏖 tryb urlopowy</span>');

        const soc = c.soc.map(Number), fl = (c.floor || []).map(Number);
        let mi = 0; soc.forEach((v, i) => { if (v < soc[mi]) mi = i; });
        const lines = [];
        const as = p.assumptions;
        if (as && typeof as === 'object') {
          const kwh = (v) => (exNum(v) === null ? '?' : exFmt(v, 1)) + ' kWh';
          const pvSrc = as.pv_source ? ` (${exEsc(as.pv_source)})` : '';
          const parts = [`zużycie do północy ~<b>${kwh(as.load_rest_today_kwh)}</b> (${/^tempo dnia/.test(String(as.load_today_source || '')) ? 'z dzisiejszego zużycia' : 'z profilu'})`];
          if (as.load_live && exNum(as.load_live.live_kw) !== null) parts.push(`teraz dom bierze <b>${exFmt(as.load_live.live_kw, 1)} kW</b> (oczekiwano ${exFmt(as.load_live.expected_kw, 1)}) — najbliższe godziny skorygowane`);
          if (exNum(as.load_tomorrow_kwh) !== null) parts.push(`jutro <b>${kwh(as.load_tomorrow_kwh)}</b>`);
          if (exNum(as.pv_tomorrow_kwh) !== null) parts.push(`PV jutro <b>${kwh(as.pv_tomorrow_kwh)}</b>${pvSrc}`);
          const pf = exNum(as.pv_factor);
          if (pf !== null && Math.abs(pf - 1) > 0.004) parts.push(`prognoza PV × <b>${exFmt(pf, 2)}</b> (korekta z historii)`);
          if (exNum(as.wear_cost) > 0) parts.push(`zużycie baterii <b>${exFmt(as.wear_cost, 2)} zł/kWh</b>`);
          lines.push(`<div>📋 Plan zakłada: ${parts.join(' · ')}.</div>`);
          const acc = (this._hass.states[this._eid('sensor', 'monitor_status')] || {}).attributes;
          const ac = acc && acc.accuracy;
          const accTxt = (st, what) => {
            if (!st || exNum(st.mae_pct) === null) return null;
            const b = exNum(st.bias_pct);
            return `${what} ±<b>${exFmt(st.mae_pct, 0)}%</b>${b !== null && Math.abs(b) >= 3 ? ` (zwykle ${b > 0 ? 'zawyżona' : 'zaniżona'} o ${exFmt(Math.abs(b), 0)}%)` : ''}`;
          };
          const accParts = ac ? [accTxt(ac.load, 'zużycie'), accTxt(ac.pv, 'PV')].filter(Boolean) : [];
          if (accParts.length) lines.push(`<div>🎯 Trafność prognoz (ostatnie dni: ${exFmt(Math.max((ac.load || {}).n || 0, (ac.pv || {}).n || 0), 0)}): ${accParts.join(' · ')}.</div>`);
          if (!as.pv_hourly_tomorrow) lines.push(`<div style="color:var(--red);">⚠ Brak godzinowej prognozy PV na jutro — plan liczy tak, jakby jutro nie było słońca. Wskaż encję prognozy Solcast albo Forecast.Solar w konfiguracji.</div>`);
        }
        const lowTxt = `Najniższy SOC w planie: <b>${exFmt(soc[mi], 0, '%')}</b> o ${hm(mi + 1)}`;
        const nearFloor = fl[mi] > 0 && soc[mi] <= fl[mi] + 2;
        lines.push(`<div>${nearFloor ? '⚠ ' : ''}${lowTxt}${nearFloor ? ` — blisko progu odcięcia falownika (${exFmt(fl[mi], 0, '%')}): bateria przestaje zasilać dom, falownik pobiera prąd z sieci.` : ` (próg falownika ${exFmt(fl[mi], 0, '%')}).`}</div>`);
        const gr = exRanges(c.grid || []);
        if (gr.length) {
          lines.push('<div>🔌 Ładowanie z sieci: ' + gr.map((r) => {
            const tg = (c.target || []).slice(r[0], r[1]).map(Number).filter((x) => isFinite(x) && x > 0);
            return `<b>${hm(r[0])}–${hm(r[1])}</b>${tg.length ? ` (do ${Math.round(Math.max(...tg))}%)` : ''}`;
          }).join(', ') + '</div>');
        } else lines.push('<div>🔌 Ładowanie z sieci: <b>nie jest potrzebne</b> w tym horyzoncie.</div>');
        const sr = exRanges(c.sale || []);
        if (p.mode === 'storm') lines.push('<div>💰 Sprzedaż z baterii: <b>wyłączona</b> (tryb burzowy).</div>');
        else if (sr.length) lines.push('<div>💰 Sprzedaż z baterii: ' + sr.map((r) => {
          const w = ((as && as.sale_windows) || []).find((x) => `${String(x.start).padStart(2, '0')}:00` === hm(r[0]) && exNum(x.power_w) > 0);
          return `<b>${hm(r[0])}–${hm(r[1])}</b>${w ? ` (moc obniżona do ${exFmt(exNum(w.power_w) / 1000, 1)} kW — sprzedaję tylko zapas energii)` : ''}`;
        }).join(', ') + '</div>');
        else {
          // przyczyna z planera (zestaw 1 i 2 mogą mieć różne); bez niej — stary, ogólny opis
          const why = ['bateria_sprzedaz_start', 'bateria_sprzedaz_start_2'].map((k) => (p.proposals || {})[k])
            .filter((x) => x && x.skip && x.reason).map((x) => String(x.reason).replace(/^Pomiń\s*[—-]\s*/, '').trim());
          const uniq = why.filter((x, i) => why.indexOf(x) === i);
          lines.push(uniq.length
            ? `<div>💰 Sprzedaż z baterii: <b>nie planuję</b> — ${uniq.map((x) => exEsc(x.charAt(0).toLowerCase() + x.slice(1))).join('<br>oraz ')}</div>`
            : '<div>💰 Sprzedaż z baterii: <b>brak opłacalnych godzin</b> (lub brak pełnych cen RCE).</div>');
        }
        const sell = (c.sell || []).map(exNum);
        const buy = (c.buy || []).map(exNum);
        if (sell.some((v) => v !== null)) {
          let bi = -1; sell.forEach((v, i) => { if (v !== null && (bi < 0 || v > sell[bi])) bi = i; });
          lines.push(`<div>📈 Najwyższa cena sprzedaży: <b>${exFmt(sell[bi], 2)} zł/kWh</b> o ${hm(bi)}.</div>`);
        } else lines.push('<div>📈 Brak cen RCE w horyzoncie planu — sprzedaż nie jest planowana.</div>');
        if (buy.some((v) => v !== null)) {
          let ci = -1; buy.forEach((v, i) => { if (v !== null && (ci < 0 || v < buy[ci])) ci = i; });
          lines.push(`<div>🛒 Najtańszy zakup: <b>${exFmt(buy[ci], 2)} zł/kWh</b> o ${hm(ci)}.</div>`);
        }

        const props = Object.keys(p.proposals || {}).map((k) => p.proposals[k]).filter((x) => x && !x.skip && x.proposed != null && String(x.proposed) !== String(x.current));
        const propHtml = props.length
          ? `<div class="ex-note" style="margin-top:12px;">Zmiany w harmonogramie, które plan zakłada:</div>` + props.map((x) => `<div class="ex-prop"><span>${exEsc(x.label || '')}</span><span>${exEsc(x.current || '—')} → <b>${exEsc(x.proposed)}</b></span></div>`).join('')
          : '<div class="ex-note" style="margin-top:12px;">Obecny harmonogram jest zgodny z planem — nie trzeba niczego zmieniać.</div>';
        return `
          <div class="ex-sum">${chips.join('')}</div>
          <div class="ex-plan"><canvas id="exPlanCv" role="img" aria-label="Wykres planu SOC na najbliższe ${n} godzin"></canvas><div class="ex-tip" id="exPlanTip" hidden></div></div>
          <div class="ex-leg">
            <span><i class="line" style="background:#0a84ff;"></i>SOC (plan)</span>
            <span><i class="dash"></i>próg odcięcia falownika</span>
            <span><i style="background:rgba(10,132,255,.35);"></i>ładowanie z sieci</span>
            <span><i style="background:rgba(48,209,88,.4);"></i>sprzedaż z baterii</span>
            <span><i style="background:rgba(255,159,10,.28);"></i>szczyt taryfy</span>
          </div>
          <div class="ex-lines">${lines.join('')}</div>
          ${propHtml}
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:12px;">
            <button type="button" class="btn" data-ex="plan-refresh" style="padding:8px 14px;flex-direction:row;gap:8px;"><span>🔄</span><span class="label">Przelicz teraz</span></button>
            <span id="exPlanMsg" style="font-size:11px;color:var(--muted);"></span>
          </div>
          <div class="ex-note">To prognoza, nie gwarancja: opiera się na prognozie PV, historii zużycia, cenach RCE i taryfie. Pasek pod wykresem pokazuje ceny kupna (górny) i sprzedaży (dolny) dla każdej godziny; dotknij wykresu, aby zobaczyć szczegóły.</div>`;
      },

      async _exPlanRefresh() {
        const msg = this._el('exPlanMsg'); const s = this._exS();
        if (s.planBusy) return;
        s.planBusy = true;
        if (msg) msg.textContent = 'Liczę…';
        try {
          const res = exResp(await exCall(this, 'get_plan', { force: true }));
          const plan = res && res.plan;
          if (plan && (plan.curve || plan.error)) { s.planOverride = plan; s.keys.plan = null; this._exPlan(); const m2 = this._el('exPlanMsg'); if (m2) m2.textContent = 'Plan przeliczony.'; }
          else if (msg) msg.textContent = 'Nie udało się przeliczyć planu (brak danych).';
        } catch (e) { if (msg) msg.textContent = 'Błąd: ' + exErr(e); }
        finally { s.planBusy = false; }
      },

      _exPlanPaint(box, c) {
        const cv = box.querySelector('#exPlanCv'); if (!cv) return;
        const s = this._exS();
        const dpr = window.devicePixelRatio || 1;
        const w = cv.clientWidth || 360, h = cv.clientHeight || 250;
        if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
        const ctx = cv.getContext('2d');
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, w, h);
        const n = c.soc.length, h0 = exStartHour(c);
        const pad = this._exPlanPad();
        const stripH = 11, labH = 16, gap = 5;
        const plotL = pad.l, plotR = w - pad.r, plotT = pad.t;
        const plotB = h - labH - 2 * stripH - gap - 8;
        const plotW = plotR - plotL, plotH = plotB - plotT;
        const cw = plotW / n;
        const xAt = (i) => plotL + i * cw;
        const yAt = (v) => plotT + (1 - Math.max(0, Math.min(100, v)) / 100) * plotH;
        const FONT = '-apple-system, "Segoe UI", sans-serif';

        // tło kolumn: szczyt taryfy, ładowanie z sieci, sprzedaż
        for (let i = 0; i < n; i++) {
          if (c.peak && c.peak[i]) { ctx.fillStyle = 'rgba(255,159,10,0.10)'; ctx.fillRect(xAt(i), plotT, cw, plotH); }
          if (c.grid && c.grid[i]) { ctx.fillStyle = 'rgba(10,132,255,0.22)'; ctx.fillRect(xAt(i), plotT, cw, plotH); }
          if (c.sale && c.sale[i]) { ctx.fillStyle = 'rgba(48,209,88,0.26)'; ctx.fillRect(xAt(i), plotT, cw, plotH); }
        }
        // siatka i oś SOC
        ctx.lineWidth = 1; ctx.font = '10px ' + FONT; ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
        for (let g = 0; g <= 4; g++) {
          const v = g * 25, y = yAt(v);
          ctx.strokeStyle = TC('grid'); ctx.beginPath(); ctx.moveTo(plotL, y); ctx.lineTo(plotR, y); ctx.stroke();
          ctx.fillStyle = TC('muted'); ctx.fillText(v + '%', plotL - 5, y);
        }
        // granica doby
        for (let i = 0; i < n; i++) {
          if ((h0 + i) % 24 === 0 && i > 0) {
            ctx.strokeStyle = TC('line'); ctx.setLineDash([3, 3]); ctx.beginPath(); ctx.moveTo(xAt(i), plotT); ctx.lineTo(xAt(i), plotB + labH - 4); ctx.stroke(); ctx.setLineDash([]);
            ctx.fillStyle = TC('muted'); ctx.textAlign = 'left'; ctx.textBaseline = 'top'; ctx.fillText('jutro', xAt(i) + 3, plotT + 2);
          }
        }
        // próg odcięcia falownika (schodkowo)
        const fl = (c.floor || []).map(Number);
        if (fl.length) {
          ctx.strokeStyle = '#ff453a'; ctx.lineWidth = 1.5; ctx.setLineDash([5, 4]); ctx.beginPath();
          for (let i = 0; i < n; i++) { const y = yAt(isFinite(fl[i]) ? fl[i] : 0); if (i === 0) ctx.moveTo(xAt(i), y); else ctx.lineTo(xAt(i), y); ctx.lineTo(xAt(i + 1), y); }
          ctx.stroke(); ctx.setLineDash([]);
        }
        // krzywa SOC: punkt 0 = teraz (początek pierwszej godziny planu), potem SOC na koniec każdej godziny
        const pts = [[xAt(0), yAt(Number(c.soc_now))]];
        for (let i = 0; i < n; i++) pts.push([xAt(i + 1), yAt(Number(c.soc[i]))]);
        const grad = ctx.createLinearGradient(0, plotT, 0, plotB);
        grad.addColorStop(0, 'rgba(10,132,255,0.30)'); grad.addColorStop(1, 'rgba(10,132,255,0.02)');
        ctx.beginPath(); ctx.moveTo(pts[0][0], plotB); pts.forEach((q) => ctx.lineTo(q[0], q[1])); ctx.lineTo(pts[pts.length - 1][0], plotB); ctx.closePath(); ctx.fillStyle = grad; ctx.fill();
        ctx.beginPath(); pts.forEach((q, i) => { if (i === 0) ctx.moveTo(q[0], q[1]); else ctx.lineTo(q[0], q[1]); });
        ctx.strokeStyle = '#0a84ff'; ctx.lineWidth = 2.5; ctx.lineJoin = 'round'; ctx.stroke();
        // najniższy punkt
        let mi = 0; for (let i = 1; i < n; i++) if (Number(c.soc[i]) < Number(c.soc[mi])) mi = i;
        const mp = pts[mi + 1];
        ctx.fillStyle = '#0a84ff'; ctx.beginPath(); ctx.arc(mp[0], mp[1], 3.5, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = TC('text2'); ctx.font = 'bold 10px ' + FONT; ctx.textAlign = mp[0] > plotR - 30 ? 'right' : 'center'; ctx.textBaseline = 'top';
        ctx.fillText(Math.round(Number(c.soc[mi])) + '%', mp[0], Math.min(plotB - 11, mp[1] + 5));

        // etykiety godzin
        const step = cw >= 24 ? 1 : (cw >= 12 ? 2 : 3);
        ctx.fillStyle = TC('muted'); ctx.font = '10px ' + FONT; ctx.textAlign = 'center'; ctx.textBaseline = 'top';
        for (let i = 0; i < n; i += step) ctx.fillText(exHH(h0 + i), xAt(i) + cw / 2, plotB + 4);

        // paski cen: kupno (górny), sprzedaż (dolny)
        const buy = (c.buy || []).map(exNum), sell = (c.sell || []).map(exNum);
        const maxBuy = Math.max(0.01, ...buy.filter((v) => v !== null)), maxSell = Math.max(0.01, ...sell.filter((v) => v !== null && v > 0));
        const y1 = plotB + labH, y2 = y1 + stripH + 2;
        ctx.font = '9px ' + FONT; ctx.textAlign = 'right'; ctx.textBaseline = 'middle'; ctx.fillStyle = TC('muted');
        ctx.fillText('kup.', plotL - 5, y1 + stripH / 2); ctx.fillText('sprz.', plotL - 5, y2 + stripH / 2);
        for (let i = 0; i < n; i++) {
          const b = buy[i], sv = sell[i];
          ctx.fillStyle = b === null ? 'rgba(128,128,128,0.15)' : `rgba(255,159,10,${(0.18 + 0.72 * Math.min(1, b / maxBuy)).toFixed(2)})`;
          ctx.fillRect(xAt(i) + 0.5, y1, Math.max(1, cw - 1), stripH);
          ctx.fillStyle = sv === null ? 'rgba(128,128,128,0.15)' : (sv < 0 ? 'rgba(255,69,58,0.85)' : `rgba(48,209,88,${(0.18 + 0.72 * Math.min(1, sv / maxSell)).toFixed(2)})`);
          ctx.fillRect(xAt(i) + 0.5, y2, Math.max(1, cw - 1), stripH);
        }

        // podświetlenie i podpowiedź
        const tip = box.querySelector('#exPlanTip');
        const hv = s.hover;
        if (hv != null && hv >= 0 && hv < n) {
          ctx.strokeStyle = TC('text2'); ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(xAt(hv) + cw / 2, plotT); ctx.lineTo(xAt(hv) + cw / 2, y2 + stripH); ctx.stroke();
          const q = pts[hv + 1]; ctx.fillStyle = '#fff'; ctx.strokeStyle = '#0a84ff'; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(q[0], q[1], 4, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
          if (tip) {
            const flags = [];
            if (c.grid && c.grid[hv]) { const t = exNum((c.target || [])[hv]); flags.push('🔌 ładowanie z sieci' + (t ? ` do ${Math.round(t)}%` : '')); }
            if (c.sale && c.sale[hv]) flags.push('💰 sprzedaż z baterii');
            if (c.peak && c.peak[hv]) flags.push('szczyt taryfy');
            tip.innerHTML = `<b>${exHH(h0 + hv)}:00–${exHH(h0 + hv + 1)}:00</b><br>SOC na koniec: <b>${exFmt(c.soc[hv], 0, '%')}</b> (próg ${exFmt(fl[hv], 0, '%')})<br>PV ${exFmt((c.pv || [])[hv], 1)} kWh · dom ${exFmt((c.load || [])[hv], 1)} kWh<br>kupno ${exFmt(buy[hv], 2)} · sprzedaż ${exFmt(sell[hv], 2)} zł/kWh${flags.length ? '<br>' + flags.join(' · ') : ''}`;
            tip.hidden = false;
            const tw = tip.offsetWidth || 160;
            let left = xAt(hv) + cw / 2 + 10; if (left + tw > w - 2) left = xAt(hv) + cw / 2 - tw - 10; if (left < 2) left = 2;
            tip.style.left = left + 'px'; tip.style.top = (plotT + 4) + 'px';
          }
        } else if (tip) tip.hidden = true;
      },
    });

    // =====================================================================
    //  RAPORT MIESIĘCZNY i ZDROWIE BATERII (zakładka „Zysk i log”)
    // =====================================================================
    const exPct = (v, d) => { const n = exNum(v); return n === null ? '—' : n.toFixed(d == null ? 0 : d).replace('.', ',') + '%'; };
    const exTile = (l, v, s) => `<div class="ex-tile"><div class="l">${l}</div><div class="v">${v}</div>${s ? `<div class="s">${s}</div>` : ''}</div>`;
    const EX_MONTHS = ['styczeń', 'luty', 'marzec', 'kwiecień', 'maj', 'czerwiec', 'lipiec', 'sierpień', 'wrzesień', 'październik', 'listopad', 'grudzień'];
    const exMonthTitle = (y, m) => { const n = EX_MONTHS[m - 1] || ''; return n ? n.charAt(0).toUpperCase() + n.slice(1) + ' ' + y : '…'; };
    const exMonthShift = (year, month, delta) => { const t = year * 12 + (month - 1) + delta; return [Math.floor(t / 12), (t % 12) + 1]; };

    Object.assign(BmsPanel.prototype, {
      _exReport() {
        const box = this._el('exReportBox'); if (!box) return;
        const s = this._exS(), r = s.rep;
        if (!box.dataset.exBound) {
          box.dataset.exBound = '1';
          box.addEventListener('click', (ev) => {
            const b = ev.target && ev.target.closest ? ev.target.closest('[data-ex]') : null;
            if (!b) return;
            const a = b.dataset.ex;
            if (a === 'rep-prev' || a === 'rep-next' || a === 'rep-now') this._exRepGo(a);
          });
        }
        const st = this._hass.states[this._eid('sensor', 'monthly_report')];
        const cur = st && st.attributes && st.attributes.year ? st.attributes : null;
        const rep = r.year == null ? cur : r.data;
        const key = JSON.stringify([r.year, r.month, r.loading, r.err, rep ? [rep.year, rep.month, rep.net, rep.days_with_data, rep.export_kwh, rep.import_kwh, rep.pv_kwh, rep.saving_estimate] : null, TC('text')]);
        if (box.dataset.exKey === key) return;
        box.dataset.exKey = key;
        if (!rep && !r.loading && !r.err) {
          box.innerHTML = st ? '<div class="chart-empty">Raport jeszcze się nie policzył — pojawi się po kilku minutach pracy integracji.</div>'
            : '<div class="chart-empty" style="color:var(--red);">Brak sensora raportu — zaktualizuj integrację i zrestartuj Home Assistant.</div>';
          return;
        }
        const isCur = r.year == null;
        const title = rep ? rep.title : (r.year != null ? exMonthTitle(r.year, r.month) : '…');
        const nav = `<div class="ex-nav">
          <button type="button" class="btn" data-ex="rep-prev" style="padding:6px 12px;" ${r.loading ? 'disabled' : ''} aria-label="Poprzedni miesiąc">◀</button>
          <div style="text-align:center;"><b>${exEsc(title)}</b>${rep ? `<div class="ex-note" style="margin:2px 0 0;">${rep.complete ? 'pełny miesiąc' : `dane z ${rep.days_with_data} z ${rep.days_in_month} dni`}${isCur ? ' · bieżący' : ''}</div>` : ''}</div>
          <button type="button" class="btn" data-ex="rep-next" style="padding:6px 12px;" ${r.loading || isCur ? 'disabled' : ''} aria-label="Następny miesiąc">▶</button></div>`;
        if (r.loading || !rep) { box.innerHTML = nav + `<div class="chart-empty">${r.err ? 'Błąd: ' + exEsc(r.err) : 'Ładowanie raportu…'}</div>`; return; }
        if (r.err) { box.innerHTML = nav + `<div class="chart-empty" style="color:var(--red);">Błąd: ${exEsc(r.err)}</div>`; return; }
        if (!rep.days_with_data) { box.innerHTML = nav + '<div class="chart-empty">Brak danych za ten miesiąc — bilans liczy się od chwili uruchomienia integracji.</div>'; return; }
        const col = (v) => (exNum(v) === null ? 'inherit' : (Number(v) >= 0 ? 'var(--green)' : 'var(--red)'));
        const tiles = [
          exTile('Bilans z siecią', `<span style="color:${col(rep.net)}">${exMoney(rep.net)}</span>`, `sprzedaż − zakup`),
          exTile('Sprzedaż do sieci', exMoney(rep.revenue).replace(/^\+/, ''), `${exFmt(rep.export_kwh, 1)} kWh · śr. ${exFmt(rep.avg_sell_price, 2)} zł/kWh`),
          exTile('Zakup z sieci', exMoney(rep.cost).replace(/^\+/, ''), `${exFmt(rep.import_kwh, 1)} kWh · śr. ${exFmt(rep.avg_buy_price, 2)} zł/kWh`),
        ];
        if (rep.pv_kwh != null) tiles.push(exTile('Produkcja PV', exFmt(rep.pv_kwh, 0, ' kWh'), rep.self_consumption_pct != null ? `autokonsumpcja ${exPct(rep.self_consumption_pct)}` : ''));
        if (rep.load_kwh != null) tiles.push(exTile('Zużycie domu', exFmt(rep.load_kwh, 0, ' kWh'), rep.self_sufficiency_pct != null ? `samowystarczalność ${exPct(rep.self_sufficiency_pct)}` : ''));
        if (rep.battery_charge_kwh != null) tiles.push(exTile('Bateria', `${exFmt(rep.battery_charge_kwh, 0)} / ${exFmt(rep.battery_discharge_kwh, 0)} kWh`, `ładowanie / rozładowanie${rep.cycle_efficiency_pct != null ? ` · sprawność ${exPct(rep.cycle_efficiency_pct, 0)}` : ''}`));
        if (rep.saving_estimate != null) tiles.push(exTile('Oszczędność (szacunek)', `<span style="color:${col(rep.saving_estimate)}">${exMoney(rep.saving_estimate).replace(/^\+/, '')}</span>`, 'orientacyjnie, względem braku PV i baterii'));
        const days = Array.isArray(rep.days) ? rep.days : [];
        const bars = days.length > 1 ? (typeof this._balanceSvg === 'function' ? this._balanceSvg(days, '') : '') : '';
        const best = rep.best_day ? `<div>🏆 Najlepszy dzień: <b>${exEsc(rep.best_day.date)}</b> (${exEsc(exMoney(rep.best_day.net))})</div>` : '';
        const worst = rep.worst_day && rep.days_with_data > 1 ? `<div>📉 Najsłabszy dzień: <b>${exEsc(rep.worst_day.date)}</b> (${exEsc(exMoney(rep.worst_day.net))})</div>` : '';
        const neg = Number(rep.neg_export_kwh) > 0.05 ? `<div>⚠ Energia oddana przy ujemnej cenie RCE: <b>${exFmt(rep.neg_export_kwh, 1)} kWh</b></div>` : '';
        box.innerHTML = nav + `<div class="ex-tiles">${tiles.join('')}</div>${bars}
          <div class="ex-lines">${best}${worst}${neg}</div>
          <div class="ex-note">Bilans liczony jest z mocy sieci i cen chwilowych (jak „Bilans w PLN” wyżej), więc może się różnić od rachunku. „Oszczędność” to szacunek: koszt zużytej energii po średniej cenie zakupu z tego miesiąca minus faktyczny bilans — bez opłat stałych.</div>`;
      },

      async _exRepGo(action) {
        const s = this._exS(), r = s.rep;
        if (r.loading) return;
        const st = this._hass.states[this._eid('sensor', 'monthly_report')];
        const cur = st && st.attributes && st.attributes.year ? st.attributes : null;
        const y0 = r.year != null ? r.year : ((cur && cur.year) || new Date().getFullYear());
        const m0 = r.year != null ? r.month : ((cur && cur.month) || (new Date().getMonth() + 1));
        if (action === 'rep-now') { r.year = null; r.month = null; r.data = null; r.err = ''; this._exLog(); return; }
        const [y, m] = exMonthShift(y0, m0, action === 'rep-prev' ? -1 : 1);
        const today = new Date();
        if (y > today.getFullYear() || (y === today.getFullYear() && m >= today.getMonth() + 1)) { r.year = null; r.month = null; r.data = null; r.err = ''; this._exLog(); return; }
        if (y < today.getFullYear() - 3) return;
        r.loading = true; r.err = ''; r.year = y; r.month = m; r.data = null; this._exLog();
        try {
          const res = exResp(await exCall(this, 'monthly_report', { year: y, month: m }));
          if (r.year === y && r.month === m) r.data = res && res.year ? res : null;
          if (r.year === y && r.month === m && !r.data) r.err = 'nieprawidłowa odpowiedź integracji';
        } catch (e) { r.err = exErr(e); }
        finally { r.loading = false; }
        this._exLog();
      },

      _exHealth() {
        const box = this._el('exHealthBox'); if (!box) return;
        const st = this._hass.states[this._eid('sensor', 'battery_health')];
        if (!st) { box.innerHTML = '<div class="chart-empty" style="color:var(--red);">Brak sensora zdrowia baterii — zaktualizuj integrację i zrestartuj Home Assistant.</div>'; return; }
        const a = st.attributes || {};
        const key = JSON.stringify([a.eff_7d, a.eff_30d, a.eff_90d, a.days_7d, a.days_30d, a.days_90d, a.eff_trend_pp, a.capacity_est_kwh, a.capacity_samples, a.capacity_configured_kwh, a.soh_est_pct, TC('text')]);
        if (box.dataset.exKey === key) return;
        box.dataset.exKey = key;
        const effTile = (l, e, n) => exTile(l, exPct(e, 1), e == null ? 'za mało pełnych dób' : `z ${n} ${n === 1 ? 'doby' : 'dób'}`);
        const tr = exNum(a.eff_trend_pp);
        const trend = tr === null ? exTile('Trend sprawności', '—', 'potrzeba ≥ 15 dób w 90 dniach')
          : exTile('Trend sprawności', `<span style="color:${tr >= -0.5 ? 'var(--green)' : (tr >= -2 ? 'var(--orange)' : 'var(--red)')}">${tr >= 0 ? '+' : '−'}${Math.abs(tr).toFixed(1).replace('.', ',')} pp</span>`, 'ostatnie 30 dni względem 90');
        const est = exNum(a.capacity_est_kwh), conf = exNum(a.capacity_configured_kwh), soh = exNum(a.soh_est_pct);
        const capTile = est === null
          ? exTile('Pojemność (szacunek)', '—', a.capacity_samples ? `za mało pełnych cykli (${a.capacity_samples}/3)` : 'czeka na długie ładowanie (≥ 15 pkt SOC)')
          : exTile('Pojemność (szacunek)', exFmt(est, 1, ' kWh'), `ustawiona ${exFmt(conf, 1)} kWh · ${a.capacity_samples} pomiarów`);
        const sohTile = soh === null ? '' : exTile('Stosunek do ustawionej', `${soh.toFixed(0)}%`, 'orientacyjnie, nie jest pomiarem SOH');
        let hint = '';
        if (soh !== null && (soh < 80 || soh > 115)) hint = `<div class="ex-chip warn" style="display:inline-block;margin-top:10px;">Szacunek znacznie odbiega od ustawionej pojemności (${exFmt(conf, 1)} kWh) — sprawdź, czy pojemność w konfiguracji integracji jest prawidłowa.</div>`;
        box.innerHTML = `<div class="ex-tiles">${effTile('Sprawność cyklu 7 dni', a.eff_7d, a.days_7d)}${effTile('30 dni', a.eff_30d, a.days_30d)}${effTile('90 dni', a.eff_90d, a.days_90d)}${trend}${capTile}${sohTile}</div>${hint}
          <div class="ex-note">Sprawność cyklu = energia oddana (z poprawką na zmianę SOC) ÷ energia pobrana, liczona dla dób z wyraźnym ładowaniem (≥ 2 kWh) i pełnymi danymi. Pojemność jest szacowana z odcinków ładowania (mediana ostatnich pomiarów); SOC falownika jest zaokrąglany, więc to wskazówka, a nie pomiar zdrowia baterii.</div>`;
      },
    });

    // =====================================================================
    //  OSZCZĘDNOŚCI (3 warianty) i TRAFNOŚĆ PROGNOZ — dane z usługi insights_get (co 5 min)
    // =====================================================================
    const EX_PERIODS = [['today', 'dziś'], ['last30', '30 dni'], ['month', 'ten miesiąc'], ['year', 'ten rok'], ['total', 'od początku']];
    const exDay = (iso) => { const m = /^(\d{4})-(\d\d)-(\d\d)/.exec(String(iso || '')); return m ? `${m[3]}.${m[2]}` : String(iso || ''); };
    const exPairBars = (rows, fk, ak, unit, colAct) => {
      const vals = []; rows.forEach((r) => { [r[fk], r[ak]].forEach((v) => { if (exNum(v) !== null) vals.push(Number(v)); }); });
      if (!vals.length) return '<div class="chart-empty">Brak danych.</div>';
      const mx = Math.max(...vals, 0.01);
      const cols = rows.map((r) => {
        const f = exNum(r[fk]), a = exNum(r[ak]);
        const h = (v) => (v === null ? 0 : Math.max(1, Math.round(v / mx * 100)));
        const tip = `${exDay(r.date)}: prognoza ${exFmt(f, 1)} ${unit}, wykonanie ${exFmt(a, 1)} ${unit}`;
        return `<div title="${exEsc(tip)}" style="flex:1;display:flex;align-items:flex-end;gap:1px;height:100%;min-width:0;">
          <div style="flex:1;height:${h(f)}%;background:var(--muted);opacity:.45;border-radius:2px 2px 0 0;"></div>
          <div style="flex:1;height:${h(a)}%;background:${a === null ? 'transparent' : colAct};border-radius:2px 2px 0 0;"></div></div>`;
      }).join('');
      return `<div style="display:flex;align-items:flex-end;gap:2px;height:90px;">${cols}</div>
        <div style="display:flex;justify-content:space-between;font-size:10px;color:var(--muted);margin-top:3px;"><span>${exEsc(exDay(rows[0].date))}</span><span>${exEsc(exDay(rows[rows.length - 1].date))}</span></div>`;
    };

    Object.assign(BmsPanel.prototype, {
      async _exInsLoad() {
        const s = this._exS().ins;
        if (s.loading) return;
        s.loading = true;
        try { s.data = exResp(await exCall(this, 'insights_get', {})) || {}; s.err = ''; s.at = Date.now(); }
        catch (e) { s.err = exErr(e); s.at = Date.now(); }
        finally { s.loading = false; }
        this._exInsights();
      },
      _exInsights() {
        const sb = this._el('exSavBox'), ab = this._el('exAccBox');
        if (!sb && !ab) return;
        const s = this._exS().ins;
        if (!s.loading && Date.now() - s.at > 300000) this._exInsLoad();
        [sb, ab].forEach((box) => {
          if (!box || box.dataset.exBound) return;
          box.dataset.exBound = '1';
          box.addEventListener('input', (ev) => {
            const i = ev.target && ev.target.dataset && ev.target.dataset.exf ? ev.target : null;
            if (!i) return;
            const t = s.tools || (s.tools = { out: null, exp: null, busy: '', err: '', form: {} });
            t.form[i.dataset.exf] = i.value;
          });
          box.addEventListener('click', (ev) => {
            const b = ev.target && ev.target.closest ? ev.target.closest('[data-exi]') : null;
            if (!b) return;
            if (b.dataset.exi === 'period') { s.period = b.dataset.p; this._exInsights(); }
            else if (b.dataset.exi === 'reload') { s.at = 0; this._exInsights(); }
            else if (b.dataset.exi === 'outage' || b.dataset.exi === 'expand') this._exToolsAct(b.dataset.exi);
            else if (b.dataset.exi === 'cau-apply') this._exCautionAct('pv_caution_apply');
            else if (b.dataset.exi === 'cau-revert') this._exCautionAct('pv_caution_revert');
            else if (b.dataset.exi === 'cau-dismiss') this._exCautionAct('pv_caution_dismiss');
          });
        });
        const key = JSON.stringify([s.at, s.err, s.period, !!s.data, TC('text'), s.cbusy, s.cmsg, this._dgIsAdmin(), JSON.stringify((s.data && s.data.pv_caution) || null), JSON.stringify((s.data && s.data.bill) || null), JSON.stringify(s.tools ? [s.tools.out, s.tools.exp, s.tools.busy, s.tools.err] : null), JSON.stringify((s.data && [s.data.deeds, s.data.advice, s.data.price_views]) || null)]);
        if (sb && sb.dataset.exKey !== key) { sb.dataset.exKey = key; sb.innerHTML = this._exSavHtml(); }
        if (ab && ab.dataset.exKey !== key) { ab.dataset.exKey = key; ab.innerHTML = this._exAccHtml(); }
      },
      async _exCautionAct(service) {
        const s = this._exS().ins;
        if (s.cbusy) return;
        s.cbusy = true; s.cmsg = ''; this._exInsights();
        try {
          const r = exResp(await exCall(this, service, {})) || {};
          if (r.pv_caution && typeof r.pv_caution === 'object' && s.data) s.data.pv_caution = r.pv_caution;
          if (service === 'pv_caution_apply') s.cmsg = `ok:Ostrożność prognozy PV ustawiona na ${exFmt(r.to, 0)}%. Plan przeliczy się przy najbliższej okazji; możesz to cofnąć.`;
          else if (service === 'pv_caution_revert') s.cmsg = `ok:Przywrócono ostrożność ${exFmt(r.to, 0)}%.`;
          else s.cmsg = 'ok:Propozycja odrzucona — wróci najwcześniej za 7 dni, jeśli dane nadal ją uzasadnią.';
        } catch (e) { s.cmsg = 'err:' + exErr(e); }
        s.cbusy = false;
        this._exInsights();
      },
      // Autokorekta ostrożności prognozy PV: propozycja z ocen dobowych (zatwierdza admin), cofnięcie ostatniej zmiany
      // „💰 Rachunek i cel”: prognoza bilansu do końca miesiąca, cel miesięczny, rozbicie miesiąca, skarbonka (dane z insights_get.bill)
      _exBillHtml(s) {
        const b = s.data && s.data.bill && typeof s.data.bill === 'object' ? s.data.bill : null;
        if (!b) return '';
        const n = (v) => (typeof v === 'number' && isFinite(v)) ? v : null;
        const zl = (v, sign) => { const x = n(v); return x === null ? '—' : `${sign && x >= 0 ? '+' : ''}${exFmt(x, 2)} zł`; };
        const bar = (pct, col) => { const w = Math.max(0, Math.min(100, n(pct) === null ? 0 : n(pct))); return `<div style="height:8px;border-radius:4px;background:var(--border,rgba(128,128,128,.25));overflow:hidden;margin:4px 0;"><div data-role="bar" style="height:100%;width:${w}%;background:${col};"></div></div>`; };
        const parts = [];
        const g = b.goal && typeof b.goal === 'object' ? b.goal : null;
        const col = !g ? '' : (g.status === 'ok' ? 'var(--green)' : (g.status === 'warn' ? 'var(--orange)' : 'var(--red)'));
        if (g) {
          parts.push(`<div data-role="bill-goal" data-status="${exEsc(g.status || '')}" style="margin-bottom:8px;"><div style="font-size:12px;">🎯 <b>Cel miesięczny:</b> ${exEsc(g.text || '')}</div>${bar(g.pct, col)}<div style="font-size:11px;color:var(--muted);">Wydano ${zl(g.spent)} z ${zl(g.goal)} · prognoza ${zl(g.projected_spent)} (${exFmt(g.pct, 0)}% celu)</div></div>`);
        } else {
          parts.push(`<div data-role="bill-goal" class="ex-note" style="margin-bottom:8px;">🎯 Cel miesięczny: ustaw w encji <code>number.bms_monthly_goal_pln</code> kwotę, ponad którą nie chcesz wydać na prąd w miesiącu — EMS pokaże postęp i ostrzeże, gdy tempo wskaże przekroczenie.</div>`);
        }
        const f = b.forecast && typeof b.forecast === 'object' ? b.forecast : null;
        if (f) {
          parts.push(`<div data-role="bill-forecast" style="font-size:12px;margin-bottom:8px;">📈 <b>Bilans z siecią na koniec miesiąca:</b> ${zl(f.projected, true)} <span style="color:var(--muted);">(przedział ${zl(f.low, true)} … ${zl(f.high, true)}; na razie ${zl(f.mtd, true)}, średnio ${zl(f.avg_day, true)} na dobę z ${exFmt(f.days_used, 0)} dób)</span></div>`);
        } else {
          parts.push(`<div data-role="bill-forecast" class="ex-note" style="margin-bottom:8px;">📈 Prognoza rachunku pojawi się po 3 pełnych dobach z księgi zysków.</div>`);
        }
        const br = Array.isArray(b.breakdown) ? b.breakdown.filter((r) => r && typeof r === 'object' && typeof r.k === 'string') : [];
        if (br.length) {
          parts.push(`<div data-role="bill-breakdown" style="margin-bottom:8px;"><div style="font-size:12px;font-weight:600;margin-bottom:2px;">🧾 ${exEsc(b.month_title || 'Ten miesiąc')} — z czego wychodzi rachunek</div><table style="width:100%;border-collapse:collapse;font-size:12px;">${br.map((r) => `<tr><td style="color:var(--muted);padding:2px 0;">${exEsc(r.k)}</td><td style="text-align:right;">${exEsc(r.v || '')}</td></tr>`).join('')}</table><div style="font-size:11px;color:var(--muted);">Szacunek z księgi zysków — bez opłat stałych i dystrybucyjnych.</div></div>`);
        }
        const pg = b.piggy && typeof b.piggy === 'object' ? b.piggy : null;
        if (pg && n(pg.saved) !== null) {
          const pct = n(pg.pct);
          let when = '';
          if (pg.payback_date === 'zwrócone') when = 'Instalacja już się zwróciła.';
          else if (typeof pg.payback_date === 'string' && n(pg.years_left) !== null) when = `Przy obecnym tempie zwrot ok. ${exEsc(pg.payback_date)} (za ${exFmt(pg.years_left, 1)} lat).`;
          else if (pct !== null) when = 'Data zwrotu pojawi się po 14 dobach z dodatnią oszczędnością.';
          const inv = n(pg.invest) !== null ? ` z nakładu ${zl(pg.invest)}` : ' (podaj nakład w „Symulacja roczna i zwrot z inwestycji”, żeby zobaczyć procent zwrotu)';
          parts.push(`<div data-role="bill-piggy" style="margin-bottom:12px;"><div style="font-size:12px;">🐷 <b>Skarbonka:</b> zaoszczędzono ${zl(pg.saved)}${inv} (${exFmt(pg.per_day, 2)} zł na dobę, ${exFmt(pg.days, 0)} dób)</div>${pct !== null ? bar(pct, 'var(--accent,#0a84ff)') : ''}${when ? `<div style="font-size:11px;color:var(--muted);">${when}</div>` : ''}</div>`);
        }
        return `<div data-role="bill" style="margin-bottom:14px;"><div style="font-size:12px;font-weight:600;margin-bottom:6px;">💰 Rachunek i cel</div>${parts.join('')}</div>`;
      },
      // „🧰 Narzędzia”: porady, „co EMS zrobił”, test zaniku sieci, ocena rozbudowy, kalendarz drogich dni, mapa cieplna cen
      _exToolsHtml(s) {
        const d = s.data && typeof s.data === 'object' ? s.data : null;
        if (!d) return '';
        const n = (v) => (typeof v === 'number' && isFinite(v)) ? v : null;
        const t = s.tools || (s.tools = { out: null, exp: null, busy: '', err: '', form: {} });
        const parts = [];
        const de = d.deeds && typeof d.deeds === 'object' ? d.deeds : null;
        if (de && typeof de.text === 'string' && de.text) parts.push(`<div data-role="deeds" style="font-size:12px;margin-bottom:8px;">🤖 <b>Co EMS zrobił za Ciebie:</b> ${exEsc(de.text)}</div>`);
        const ad = (Array.isArray(d.advice) ? d.advice : []).filter((a) => a && typeof a === 'object' && typeof a.title === 'string');
        if (ad.length) parts.push(`<div data-role="advice" style="margin-bottom:8px;"><div style="font-size:12px;font-weight:600;margin-bottom:2px;">🧭 Porady do ustawień</div>${ad.map((a) => `<div data-role="advice-item" style="font-size:12px;border-top:1px solid var(--border,rgba(128,128,128,.25));padding:4px 0;"><b>${exEsc(a.title)}</b><div style="color:var(--muted);">${exEsc(a.text || '')}</div></div>`).join('')}</div>`);
        const pv = d.price_views && typeof d.price_views === 'object' ? d.price_views : null;
        const cal = pv && Array.isArray(pv.calendar) ? pv.calendar.filter((r) => r && typeof r.date === 'string' && n(r.avg) !== null) : [];
        if (cal.length >= 5) {
          const colr = (l) => l === 'high' ? 'var(--red)' : (l === 'low' ? 'var(--green)' : 'var(--border,rgba(128,128,128,.35))');
          parts.push(`<div data-role="price-calendar" style="margin-bottom:8px;"><div style="font-size:12px;font-weight:600;margin-bottom:4px;">📅 Kalendarz drogich dni (średnia cena zakupu)</div><div style="display:flex;flex-wrap:wrap;gap:3px;">${cal.map((r) => `<div data-level="${exEsc(r.level || '')}" title="${exEsc(r.date)}: ${exFmt(r.avg, 2)} zł/kWh" style="width:34px;padding:3px 0;border-radius:6px;text-align:center;font-size:10px;color:${r.level === 'mid' ? 'inherit' : '#fff'};background:${colr(r.level)};">${exEsc(r.date.slice(8, 10))}<br>${exFmt(r.avg, 2)}</div>`).join('')}</div><div style="font-size:11px;color:var(--muted);margin-top:2px;">Czerwone: ≥ 125% mediany (${n(pv.median) !== null ? exFmt(pv.median, 2) : '—'} zł/kWh), zielone: ≤ 80%.</div></div>`);
        }
        const heat = pv && Array.isArray(pv.heat) ? pv.heat.filter((r) => r && typeof r.date === 'string' && Array.isArray(r.h) && r.h.length === 24) : [];
        const hv = heat.flatMap((r) => r.h.filter((v) => n(v) !== null));
        if (heat.length >= 3 && hv.length) {
          const lo = Math.min(...hv), hi = Math.max(...hv);
          const cell = (v) => { if (n(v) === null) return '<td></td>'; const k = hi > lo ? (v - lo) / (hi - lo) : 0; return `<td title="${exFmt(v, 2)} zł/kWh" style="background:rgba(${Math.round(60 + 195 * k)},${Math.round(180 - 120 * k)},80,.85);width:12px;height:12px;"></td>`; };
          parts.push(`<div data-role="price-heat" style="margin-bottom:8px;overflow-x:auto;"><div style="font-size:12px;font-weight:600;margin-bottom:4px;">🌡️ Mapa cieplna cen (doby × godziny)</div><table style="border-collapse:separate;border-spacing:1px;font-size:9px;">${heat.map((r) => `<tr><td style="padding-right:4px;color:var(--muted);">${exEsc(r.date.slice(5))}</td>${r.h.map(cell).join('')}</tr>`).join('')}</table><div style="font-size:11px;color:var(--muted);">Od lewej godzina 0 do 23; zielone — tanio, czerwone — drogo (od ${exFmt(lo, 2)} do ${exFmt(hi, 2)} zł/kWh).</div></div>`);
        }
        const dis = t.busy ? 'disabled' : '';
        const o = t.out && typeof t.out === 'object' ? t.out : null;
        let outHtml = '';
        if (o) outHtml = o.ok ? `<div data-role="outage-result" style="font-size:12px;margin-top:4px;">Start: ${exFmt(o.soc, 0)}% (próg ${exFmt(o.floor, 0)}%), pobór ${exFmt(o.load_w, 0)} W<table style="width:100%;border-collapse:collapse;">${(Array.isArray(o.scenarios) ? o.scenarios : []).map((x) => `<tr><td style="padding:2px 0;color:var(--muted);">${exEsc(x && x.label)}</td><td style="text-align:right;font-weight:600;">${exEsc(x && x.text)}</td></tr>`).join('')}</table><div style="font-size:11px;color:var(--muted);">${exEsc(o.note || '')}</div></div>` : `<div data-role="outage-result" class="ex-note">${exEsc(o.error || 'Brak wyniku.')}</div>`;
        parts.push(`<div data-role="outage" style="margin-bottom:8px;"><div style="font-size:12px;font-weight:600;margin-bottom:4px;">🔌 Test zaniku sieci</div><button class="btn" data-exi="outage" ${dis} style="padding:6px 14px;font-size:12px;">Sprawdź, jak długo wytrzyma dom</button>${outHtml}</div>`);
        const f = t.form || {};
        const inp = (k, label, ph) => `<label style="font-size:11px;color:var(--muted);display:inline-block;margin:0 8px 4px 0;">${label}<br><input data-exf="${k}" type="number" inputmode="decimal" value="${exEsc(f[k] == null ? '' : f[k])}" placeholder="${ph}" style="width:90px;padding:4px;"></label>`;
        const e = t.exp && typeof t.exp === 'object' ? t.exp : null;
        let eHtml = '';
        if (e) {
          const row = (r, name) => r && typeof r === 'object' ? `<tr data-role="expand-${name}"><td style="color:var(--muted);">${name === 'bat' ? 'Bateria' : 'Panele'}</td><td style="text-align:right;">koszt ${exFmt(r.cost, 0)} zł</td><td style="text-align:right;">zysk ${exFmt(r.annual, 0)} zł/rok</td><td style="text-align:right;font-weight:600;">${r.payback_years == null ? 'brak zwrotu' : 'zwrot ' + exFmt(r.payback_years, 1) + ' lat'}</td></tr>${r.note ? `<tr><td colspan="4" style="font-size:11px;color:var(--muted);">${exEsc(r.note)}</td></tr>` : ''}` : '';
          eHtml = e.ok ? `<div data-role="expand-result" style="font-size:12px;"><table style="width:100%;border-collapse:collapse;">${row(e.battery, 'bat')}${row(e.pv, 'pv')}</table><div style="font-size:11px;color:var(--muted);">Średnio kupujesz po ${exFmt(e.avg_buy, 2)} zł/kWh, sprzedajesz po ${exFmt(e.avg_sell, 2)} zł/kWh (z ${exFmt(e.days, 0)} dób). ${exEsc(e.note || '')}</div></div>` : `<div data-role="expand-result" class="ex-note">${exEsc(e.error || 'Brak wyniku.')}</div>`;
        }
        parts.push(`<div data-role="expand" style="margin-bottom:12px;"><div style="font-size:12px;font-weight:600;margin-bottom:4px;">📐 Czy opłaca się rozbudowa?</div>${inp('batt_kwh', 'Bateria [kWh]', '5')}${inp('batt_cost_per_kwh', 'zł/kWh', '2000')}${inp('pv_kwp', 'Panele [kWp]', '3')}${inp('pv_now_kwp', 'Obecnie [kWp]', '6')}${inp('pv_cost_per_kwp', 'zł/kWp', '4000')}<br><button class="btn" data-exi="expand" ${dis} style="padding:6px 14px;font-size:12px;">Oszacuj</button>${eHtml}</div>`);
        if (t.err) parts.push(`<div class="ex-chip bad" data-role="tools-err" style="display:block;border-radius:12px;padding:8px 12px;margin-bottom:8px;">Nie udało się: ${exEsc(t.err)}</div>`);
        return `<div data-role="tools" style="margin-bottom:14px;"><div style="font-size:12px;font-weight:600;margin-bottom:6px;">🧰 Narzędzia</div>${parts.join('')}</div>`;
      },
      async _exToolsAct(kind) {
        const s = this._exS().ins;
        const t = s.tools || (s.tools = { out: null, exp: null, busy: '', err: '', form: {} });
        if (t.busy) return;
        t.busy = kind; t.err = ''; this._exInsights();
        try {
          if (kind === 'outage') t.out = exResp(await exCall(this, 'grid_outage_test', {})) || null;
          else {
            const data = {};
            Object.keys(t.form || {}).forEach((k) => { const v = parseFloat(String(t.form[k]).replace(',', '.')); if (isFinite(v)) data[k] = v; });
            t.exp = exResp(await exCall(this, 'expand_estimate', data)) || null;
          }
        } catch (e) { t.err = exErr(e); }
        t.busy = '';
        this._exInsights();
      },
      _exCautionHtml(s) {
        const pc = s.data && s.data.pv_caution && typeof s.data.pv_caution === 'object' ? s.data.pv_caution : null;
        if (!pc) return '';
        const admin = this._dgIsAdmin();
        const cur = exNum(pc.current);
        const prop = pc.proposal && typeof pc.proposal === 'object' && typeof pc.proposal.text === 'string' && exNum(pc.proposal.to) !== null ? pc.proposal : null;
        const last = pc.can_revert && pc.last && typeof pc.last === 'object' ? pc.last : null;
        const msg = s.cmsg ? (s.cmsg.startsWith('ok:') ? `<div class="ex-chip ok" data-role="pv-caution-msg" style="display:block;border-radius:12px;padding:8px 12px;margin-bottom:8px;">${exEsc(s.cmsg.slice(3))}</div>`
          : `<div class="ex-chip bad" data-role="pv-caution-msg" style="display:block;border-radius:12px;padding:8px 12px;margin-bottom:8px;">Nie udało się: ${exEsc(s.cmsg.slice(4))}</div>`) : '';
        const dis = s.cbusy ? 'disabled' : '';
        const btn = (a, label, primary) => `<button class="btn" data-exi="${a}" ${dis} style="padding:6px 14px;font-size:12px;${primary ? 'background:var(--accent,#0a84ff);color:#fff;' : ''}">${label}</button>`;
        let body = '';
        if (prop) {
          body = `<div class="ex-chip warn" data-role="pv-caution" style="display:block;border-radius:12px;padding:10px 12px;">
              <div style="font-weight:600;">☀️ Propozycja: ostrożność prognozy PV ${exFmt(prop.from, 0)}% → ${exFmt(prop.to, 0)}%</div>
              <div style="font-size:12px;margin-top:4px;color:var(--text);">${exEsc(prop.text)}</div>
              <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px;">${admin ? btn('cau-apply', `Zastosuj (${exFmt(prop.to, 0)}%)`, true) + btn('cau-dismiss', 'Nie teraz') : '<span style="font-size:12px;color:var(--muted);">Zatwierdzić może administrator.</span>'}</div></div>`;
        } else if (last) {
          body = `<div class="ex-note" data-role="pv-caution">☀️ Ostrożność prognozy PV: ${exFmt(last.to, 0)}% (zmieniona z ${exFmt(last.from, 0)}% dnia ${exEsc(exDay(last.date))} na podstawie ocen dobowych).${admin ? `<div style="margin-top:6px;">${btn('cau-revert', `Cofnij do ${exFmt(last.from, 0)}%`)}</div>` : ''}</div>`;
        } else if (cur !== null) {
          body = `<div class="ex-note" data-role="pv-caution">☀️ Ostrożność prognozy PV w planie: ${exFmt(cur, 0)}%. EMS sprawdza, czy prognoza PV bywa stale zawyżona albo zaniżona; gdy tak, pojawi się tu propozycja zmiany do zatwierdzenia jednym kliknięciem (z możliwością cofnięcia).</div>`;
        }
        return body || msg ? `<div style="margin-bottom:14px;">${msg}${body}</div>` : '';
      },
      _exSavHtml() {
        const s = this._exS().ins;
        if (!s.data) {
          if (s.err) return `<div class="chart-empty" style="color:var(--red);">Nie udało się wczytać: ${exEsc(s.err)}</div><div class="ex-note">Wymaga integracji 0.8.5 lub nowszej.</div><button class="btn" data-exi="reload" style="margin-top:8px;">Spróbuj ponownie</button>`;
          return '<div class="chart-empty">Ładowanie…</div>';
        }
        const sv = s.data.savings || {};
        const p = sv[s.period] || {};
        const pills = EX_PERIODS.map(([k, l]) => `<button class="btn" data-exi="period" data-p="${k}" style="padding:5px 12px;font-size:12px;${s.period === k ? 'background:var(--accent,#0a84ff);color:#fff;' : ''}">${l}</button>`).join('');
        const col = (v) => (exNum(v) === null ? 'inherit' : (Number(v) >= 0 ? 'var(--green)' : 'var(--red)'));
        const cost = (v) => { const n = exNum(v); return n === null ? '—' : (n < 0 ? '−' : '') + Math.abs(n).toFixed(2).replace('.', ',') + ' zł'; };
        const cf = s.data.cost_forecast || null;
        let cfHtml = '';
        if (cf && cf.today) {
          const z = (v) => { const n = exNum(v); return n === null ? '—' : (n < 0 ? '−' : '') + exFmt(Math.abs(n), 2) + ' zł'; };
          const t = cf.today, tm = cf.tomorrow || {};
          cfHtml = '<div class="ex-sum" id="exCostFc" style="margin-bottom:6px;">'
            + `<span class="ex-chip" style="white-space:normal;">📅 Dziś: dotąd ${z(t.so_far)}${t.total !== null && t.total !== undefined ? `, do końca doby wg planu ${z(t.rest_plan)}, razem ≈ <b>${z(t.total)}</b>` : ''}</span>`
            + (tm.plan !== null && tm.plan !== undefined ? `<span class="ex-chip" style="white-space:normal;">🗓 Jutro wg planu: ≈ <b>${z(tm.plan)}</b></span>` : '')
            + '</div>'
            + `<div class="ex-note" style="margin-bottom:8px;">${exEsc(cf.note || '')} Prognoza do końca miesiąca jest w „Rachunek i cel”.</div>`;
        }
        if (!p.days) {
          return `<div class="ex-nav" style="justify-content:flex-start;flex-wrap:wrap;gap:6px;">${pills}</div>${cfHtml}
            <div class="chart-empty">Brak danych za ten okres. Oszczędności liczą się od dnia instalacji wersji 0.8.5 — pierwszy pełny dzień pojawi się jutro.</div>`;
        }
        const tiles = [
          exTile('Zapłaciłeś', cost(p.actual), 'zakup z sieci minus to, co sprzedałeś'),
          exTile('Bez baterii zapłaciłbyś', cost(p.nobat), 'ten sam dom i PV, ale bez magazynu'),
          exTile('Z samą baterią (bez EMS)', cost(p.simple), 'bateria ładuje się tylko z nadwyżki PV'),
          exTile('Oszczędność', `<span style="color:${col(p.vs_nobat)}">${exMoney(p.vs_nobat)}</span>`, 'dzięki baterii i EMS, wobec domu bez baterii'),
          exTile('Z tego zasługa EMS', `<span style="color:${col(p.vs_simple)}">${exMoney(p.vs_simple)}</span>`, 'różnica wobec baterii działającej „samej” (minus = EMS wypadł gorzej)'),
        ];
        const daily = (sv.daily || []).filter((d) => d.complete || d.partial).slice(-30);
        let bars = '';
        if (daily.length > 1) {
          const vals = daily.map((d) => Number(d.nobat) - Number(d.actual));
          const mx = Math.max(...vals.map((v) => Math.abs(v)), 0.01);
          bars = `<div style="font-size:11px;color:var(--muted);margin-top:12px;">Oszczędność dzień po dniu (względem braku baterii)</div>
            <div style="display:flex;align-items:center;gap:2px;height:80px;margin-top:4px;">${daily.map((d, i) => {
              const v = vals[i]; const h = Math.max(2, Math.round(Math.abs(v) / mx * 48));
              const tip = `${exDay(d.date)}${d.partial ? ' (dziś, do teraz)' : ''}: ${exMoney(v)} · koszt ${cost(d.actual)}, bez baterii ${cost(d.nobat)}, bateria bez planera ${cost(d.simple)}`;
              return `<div title="${exEsc(tip)}" style="flex:1;min-width:0;height:100%;display:flex;flex-direction:column;justify-content:center;">
                <div style="height:${v >= 0 ? h : 0}px;background:var(--green);opacity:${d.partial ? 0.5 : 1};border-radius:2px 2px 0 0;align-self:stretch;margin-top:auto;"></div>
                <div style="height:${v < 0 ? h : 0}px;background:var(--red);opacity:${d.partial ? 0.5 : 1};border-radius:0 0 2px 2px;margin-bottom:auto;"></div></div>`;
            }).join('')}</div>`;
        }
        const pr = sv.params || {};
        return `<div class="ex-nav" style="justify-content:flex-start;flex-wrap:wrap;gap:6px;">${pills}</div>
          ${cfHtml}<div class="ex-tiles">${tiles.join('')}</div>${bars}
          <div class="ex-note">Z ${p.days} ${p.days === 1 ? 'dnia' : 'dni'}${sv.since ? `, dane od ${exEsc(exDay(sv.since))}` : ''}. Dzisiejszy dzień liczony do bieżącej godziny. Ceny godzinowe, bez opłat stałych.
            Porównuję 3 sytuacje: dom bez baterii · bateria bez sterowania · bateria z EMS (Twoja).
            Bateria ${exFmt(pr.cap, 1)} kWh, sprawność ${exPct((exNum(pr.eff) || 0) * 100)}, próg ${exPct(pr.floor)}.</div>`;
      },
      _exAccHtml() {
        const s = this._exS().ins;
        if (!s.data) return s.err ? `<div class="chart-empty" style="color:var(--red);">Nie udało się wczytać: ${exEsc(s.err)}</div>` : '<div class="chart-empty">Ładowanie…</div>';
        const ac = s.data.accuracy || {};
        const pv = ac.pv || {}, ld = ac.load || {}, so = ac.soc || {}, pc = ac.pv_correction || {};
        const bias = (b) => { const n = exNum(b); return n === null ? '' : (n > 0 ? `prognoza zawyżona o ${exPct(n)}` : (n < 0 ? `prognoza zaniżona o ${exPct(-n)}` : 'bez stałego odchylenia')); };
        const errCol = (m) => { const n = exNum(m); return n === null ? 'inherit' : (n <= 15 ? 'var(--green)' : (n <= 30 ? 'var(--orange)' : 'var(--red)')); };
        const fac = exNum(pc.factor);
        const corrTxt = !s.data.pv_correction_on ? 'wyłączona przełącznikiem' : (pc.days >= 5 ? `z ${pc.days} dni${exNum(pc.ratio) !== null ? `, wykonanie / prognoza ${exFmt(pc.ratio, 2)}` : ''}` : `czeka na ≥ 5 dni z prognozą ≥ 1 kWh (jest ${pc.days || 0})`);
        const tiles = [
          exTile('Prognoza PV — błąd', `<span style="color:${errCol(pv.mape)}">${exPct(pv.mape, 1)}</span>`, pv.n ? `${bias(pv.bias)} · ${pv.n} dni` : 'zbiera dane (prognoza z rana vs wykonanie)'),
          exTile('Prognoza zużycia — błąd', `<span style="color:${errCol(ld.mape)}">${exPct(ld.mape, 1)}</span>`, ld.n ? `${bias(ld.bias)} · ${ld.n} dni` : 'brak historii'),
          exTile('Plan SOC — błąd', exNum(so.mae) === null ? '—' : exFmt(so.mae, 1, ' pp'), so.n ? `średnio na godzinę · ${so.n} dni` : 'zbiera dane (plan z rana vs SOC)'),
          exTile('Korekta PV dziś', s.data.pv_correction_on && fac !== null ? '× ' + exFmt(fac, 2) : '—', corrTxt),
        ];
        const rows = (ac.days || []).slice(-30);
        const pvRows = rows.filter((r) => r.pv_fc !== null || r.pv_act !== null);
        const ldRows = rows.filter((r) => r.load_fc !== null || r.load_act !== null);
        const charts = (pvRows.length > 1 ? `<div style="font-size:11px;color:var(--muted);margin-top:12px;">Produkcja PV: prognoza (szary) i wykonanie, kWh/dzień</div>${exPairBars(pvRows, 'pv_fc', 'pv_act', 'kWh', 'var(--orange,#ff9f0a)')}` : '')
          + (ldRows.length > 1 ? `<div style="font-size:11px;color:var(--muted);margin-top:12px;">Zużycie domu: prognoza (szary) i wykonanie, kWh/dzień</div>${exPairBars(ldRows, 'load_fc', 'load_act', 'kWh', 'var(--accent,#0a84ff)')}` : '');
        const hz = Array.isArray(ac.pv_by_horizon) ? ac.pv_by_horizon : [];
        const hzName = (h) => h === 0 ? 'dziś' : h === 1 ? 'jutro' : `za ${h} dni`;
        const hzRows = hz.map((r) => `<tr><td>${hzName(r.h)}</td><td style="text-align:right;">${r.n || 0}</td>
            <td style="text-align:right;color:${errCol(r.mape)}">${exPct(r.mape, 1)}</td>
            <td style="text-align:right;color:${errCol(r.mape_adj)}">${r.n_adj >= 3 ? exPct(r.mape_adj, 1) : '—'}</td>
            <td style="text-align:right;">${s.data.pv_correction_on ? '× ' + exFmt(r.factor, 2) : '—'}</td>
            <td style="text-align:right;">± ${exPct((exNum(r.spread) || 0) * 100)}</td></tr>`).join('');
        const hzTable = hz.length ? `<div style="font-size:11px;color:var(--muted);margin-top:12px;">Prognoza PV: błąd osobno dla każdego dnia do przodu</div>
          <div style="overflow-x:auto;"><table data-role="pv-horizon" style="width:100%;border-collapse:collapse;font-size:12px;margin-top:4px;">
            <thead><tr style="color:var(--muted);text-align:right;"><th style="text-align:left;font-weight:600;">Dzień</th><th style="font-weight:600;">Dni danych</th><th style="font-weight:600;">Błąd surowej</th><th style="font-weight:600;">Błąd po korekcie</th><th style="font-weight:600;">Korekta</th><th style="font-weight:600;">Zakres</th></tr></thead>
            <tbody>${hzRows}</tbody></table></div>` : '';
        const hzTune = (() => {
          const tn = hz.filter((r) => r.tune && r.tune.mae != null);
          if (!tn.length) return '';
          const ch = tn.filter((r) => r.tune.window !== 30 || r.tune.mode !== 'median');
          const nm = (t) => `${t.window} dni${t.mode === 'ewma' ? ', świeższe dni ważniejsze' : ''}`;
          return `<div class="ex-note" data-role="pv-tune">🎯 Samostrojenie PV: EMS co dobę sprawdza okno uczenia (7, 14 albo 30 dni) na Twojej historii. ${ch.length
            ? ch.map((r) => `${hzName(r.h)}: ${nm(r.tune)} (błąd ${exFmt(r.tune.mae, 2)} kWh zamiast ${exFmt(r.tune.mae_default, 2)} kWh)`).join('; ') + '.'
            : 'Na razie standardowe 30 dni jest najlepsze albo żaden wariant nie był wyraźnie lepszy.'}</div>`;
        })();
        const rv = (Array.isArray(s.data.reviews) ? s.data.reviews : []).filter((r) => r && typeof r === 'object' && Array.isArray(r.items)).slice(0, 7);
        const vCol = (v) => v === 'trafny' ? 'var(--green)' : (v === 'chybiony' ? 'var(--red)' : 'var(--orange)');
        const lCol = (l) => l === 'ok' ? 'var(--green)' : (l === 'bad' ? 'var(--red)' : 'var(--orange)');
        const dDay = (d) => { const m = /^\d{4}-(\d{2})-(\d{2})$/.exec(String(d || '')); return m ? `${m[2]}.${m[1]}` : exEsc(String(d || '')); };
        const cName = { pv: 'prognoza PV', load: 'prognoza zużycia', soc: 'poziom baterii', sale: 'sprzedaż z baterii' };
        const tl = s.data.reviews_tally || {};
        const tc = tl.counts || {};
        const tallyTxt = tl.n ? `Ostatnie ${exFmt(tl.n, 0)} dób: plan trafny <b>${exFmt(tc['trafny'] || 0, 0)}×</b>, częściowo trafny <b>${exFmt(tc['częściowo trafny'] || 0, 0)}×</b>, chybiony <b>${exFmt(tc['chybiony'] || 0, 0)}×</b>${tl.top_culprit && cName[tl.top_culprit] ? ` · najczęściej zawodziło: <b>${exEsc(cName[tl.top_culprit])}</b> (${exFmt(tl.top_culprit_n || 0, 0)}×)` : ''}.` : '';
        const revRow = (r, i) => {
          const items = r.items.filter((x) => x && typeof x === 'object');
          const chips = items.map((x) => `<span style="color:${lCol(x.level)};white-space:nowrap;">${exEsc(x.short || x.label || '')}</span>`).join(' · ');
          const cul = r.culprit && r.culprit.text ? `<div style="margin-top:4px;"><b>Co zawiodło:</b> ${exEsc(r.culprit.text)}</div>` : '<div style="margin-top:4px;color:var(--green);">Nic istotnego nie zawiodło.</div>';
          const det = items.map((x) => `<div style="color:var(--muted);">• ${exEsc(x.label || '')}: ${exEsc(x.detail || '')}</div>`).join('');
          const facts = Array.isArray(r.facts) && r.facts.length ? `<div style="margin-top:4px;color:var(--muted);">${r.facts.map(exEsc).join(' · ')}</div>` : '';
          return `<details data-role="review-day" ${i === 0 ? 'open' : ''} style="border-top:1px solid var(--border,rgba(128,128,128,.25));padding:6px 0;">
            <summary style="cursor:pointer;font-size:12px;"><b>${dDay(r.date)}</b> <span style="color:${vCol(r.verdict)};font-weight:600;">${exEsc(r.verdict || '')}</span> <span style="color:var(--muted);">(${exFmt(r.score, 0)}/100)</span><div style="font-size:11px;margin-top:2px;">${chips}</div></summary>
            <div style="font-size:12px;margin:4px 0 2px 12px;">${cul}${det}${facts}</div></details>`;
        };
        const reviewHtml = rv.length
          ? `<div data-role="plan-review" style="margin-bottom:14px;"><div style="font-size:12px;font-weight:600;margin-bottom:4px;">📋 Ocena planu po dobie</div>
              <div style="font-size:12px;color:var(--muted);margin-bottom:6px;">${tallyTxt}</div>${rv.map(revRow).join('')}</div>`
          : `<div class="ex-note" data-role="plan-review">📋 Ocena planu po dobie: pierwsza pojawi się po północy — EMS porówna wtedy plan z rana (prognoza PV, zużycie, poziom baterii, sprzedaż) z tym, co się faktycznie stało, i wskaże, co zawiodło.</div>`;
        const ap = (Array.isArray(s.data.arb_proof) ? s.data.arb_proof : []).filter((r) => r && typeof r === 'object' && typeof r.date === 'string').slice(0, 7);
        const apCol = (l) => l === 'ok' ? 'var(--green)' : (l === 'bad' ? 'var(--red)' : (l === 'warn' ? 'var(--orange)' : 'var(--muted)'));
        const apIco = (l) => l === 'ok' ? '✔' : (l === 'bad' ? '⚠' : (l === 'warn' ? '!' : '–'));
        const apRows = ap.map((r) => `<tr data-level="${exEsc(r.level || '')}"><td>${dDay(r.date)}</td><td style="text-align:right;">${exFmt(r.in, 1)} kWh</td><td style="text-align:right;">${exFmt(r.out, 1)} kWh</td><td style="text-align:right;font-weight:600;">${exFmt(r.leak, 1)} kWh</td><td style="color:${apCol(r.level)};">${apIco(r.level)} ${exEsc(r.text || '')}</td></tr>`).join('');
        const arbHtml = ap.length
          ? `<div data-role="arb-proof" style="margin-bottom:14px;"><div style="font-size:12px;font-weight:600;margin-bottom:4px;">🔒 Dowód: nie sprzedajemy prądu z sieci</div>
              <div style="font-size:12px;color:var(--muted);margin-bottom:6px;">Zakaz „ładuj z sieci → sprzedaj”: kolumna „z sieci sprzedane” ma być 0. To górna granica — liczymy, że do sieci schodzi najpierw energia, którą bateria wcześniej pobrała z sieci.</div>
              <div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr style="text-align:left;color:var(--muted);"><th>Dzień</th><th style="text-align:right;">Z sieci do baterii</th><th style="text-align:right;">Z baterii do sieci</th><th style="text-align:right;">Z sieci sprzedane</th><th>Wynik</th></tr></thead><tbody>${apRows}</tbody></table></div></div>`
          : `<div class="ex-note" data-role="arb-proof">🔒 Dowód braku arbitrażu: od teraz EMS liczy każdej doby, ile energii poszło z sieci do baterii, ile z baterii do sieci i ile z tego mogło pochodzić z sieci (ma być 0). Pierwszy wiersz pojawi się, gdy bateria zacznie się ładować z sieci albo oddawać energię do sieci.</div>`;
        return `${this._exCautionHtml(s)}${this._exBillHtml(s)}${this._exToolsHtml(s)}${reviewHtml}${arbHtml}<div class="ex-tiles">${tiles.join('')}</div>${hzTable}${hzTune}${charts}
          <div class="ex-note">Błąd to średnia różnica prognozy i wykonania w procentach (dni z co najmniej 0,5 kWh), z ostatnich 30 dni. Prognoza PV jest zapisywana rano (od 6:00) dla każdego z 7 dni do przodu, prognoza zużycia — dzień wcześniej.
            Korekta PV jest liczona osobno dla każdego dnia do przodu (mediana wykonania do prognozy z 30 dni, w granicach 0,5–1,4), uwzględnia stały wzorzec godzinowy i poprawia dzisiejszy dzień na podstawie godzin, które już minęły.
            Dni, w których bateria była pełna i falownik ucinał produkcję, nie uczą modelu. „Błąd po korekcie” liczony jest z prognoz faktycznie wydanych po korekcie, więc pokazuje, czy korekta pomaga. Zakres to typowy błąd tego dnia.</div>`;
      },
    });

    // =====================================================================
    //  PROFILE PRACY: zima / lato / urlop / burza jednym kliknięciem, z podglądem zmian i powrotem do poprzednich ustawień
    // =====================================================================
    Object.assign(BmsPanel.prototype, {
      _exProf() {
        const box = this._el('exProfBox');
        if (!box || !this._tabNeeds('ems')) return;
        const s = this._exS().prof;
        if (!box.dataset.exBound) {
          box.dataset.exBound = '1';
          box.addEventListener('click', (ev) => {
            const b = ev.target && ev.target.closest ? ev.target.closest('[data-pf]') : null;
            if (!b || b.disabled) return;
            const a = b.dataset.pf, ps = this._exS().prof;
            if (a === 'pick') { ps.sel = ps.sel === b.dataset.id ? null : b.dataset.id; ps.msg = ''; this._exProf(); }
            else if (a === 'cancel') { ps.sel = null; this._exProf(); }
            else if (a === 'apply') this._exProfAct('profile_apply', { id: b.dataset.id });
            else if (a === 'revert') this._exProfAct('profile_revert', {});
            else if (a === 'reload') { ps.at = 0; this._exProf(); }
            else if (a === 'schedule') this._exProfAct('profile_schedule', { id: b.dataset.id, from: ps.dFrom, to: ps.dTo });
            else if (a === 'plan-clear') this._exProfAct('profile_schedule_clear', {});
            else if (a === 'save') this._exProfAct('profile_save', { name: ps.name, icon: ps.icon || undefined });
            else if (a === 'delete') this._exProfAct('profile_delete', { id: b.dataset.id });
          });
          // pola formularza zapisują wartość bez przerysowania (żeby nie gubić fokusu); data i ikona przerysowują, bo zmieniają stan przycisków
          const onField = (ev) => {
            const f = ev.target && ev.target.closest ? ev.target.closest('[data-pf-in]') : null;
            if (!f) return;
            const ps = this._exS().prof, k = f.dataset.pfIn;
            if (k === 'name') ps.name = String(f.value || '').slice(0, 24);
            else if (k === 'icon') ps.icon = String(f.value || '');
            else if (k === 'from') ps.dFrom = String(f.value || '');
            else if (k === 'to') ps.dTo = String(f.value || '');
            if (ev.type === 'change' && k !== 'name') this._exProf();
          };
          box.addEventListener('input', onField);
          box.addEventListener('change', onField);
        }
        if (!s.loading && !s.busy && Date.now() - s.at > 120000) this._exProfLoad();
        const key = JSON.stringify([s.at, s.err, s.sel, s.busy, s.msg, !!s.data, this._dgIsAdmin(), TC('text'), s.icon, s.dFrom, s.dTo]);
        if (box.dataset.exKey === key) return;
        box.dataset.exKey = key;
        box.innerHTML = this._exProfHtml();
      },
      async _exProfLoad() {
        const s = this._exS().prof;
        s.loading = true;
        try { s.data = exResp(await exCall(this, 'profiles_get', {})) || null; s.err = ''; }
        catch (e) { s.err = exErr(e); }
        s.at = Date.now(); s.loading = false;
        this._exProf();
      },
      async _exProfAct(service, data) {
        const s = this._exS().prof;
        if (s.busy) return;
        s.busy = true; s.msg = ''; this._exProf();
        try {
          const r = exResp(await exCall(this, service, data)) || {};
          if (Array.isArray(r.profiles)) { s.data = { profiles: r.profiles, active: r.active || null, plan: r.plan || null, custom_limit: r.custom_limit, icons: r.icons, custom_keys: r.custom_keys }; s.at = Date.now(); }
          const nm = (s.data && s.data.active && s.data.active.name) || '';
          const planNm = (s.data && s.data.plan && s.data.plan.name) || '';
          if (service === 'profile_apply') s.msg = `ok:Profil „${nm}” włączony — zmieniono ${exFmt(r.changed, 0)} ustawień${(r.skipped || []).length ? `, pominięto ${r.skipped.length} (brak encji lub zapis nie zadziałał)` : ''}.`;
          else if (service === 'profile_revert') s.msg = `ok:Przywrócono ${exFmt(r.restored, 0)} ustawień${(r.kept || []).length ? `; ${r.kept.length} zostawiono, bo zmieniłeś je ręcznie` : ''}.`;
          else if (service === 'profile_save') { s.msg = r.replaced ? 'ok:Własny profil nadpisany bieżącymi ustawieniami.' : 'ok:Zapisano własny profil z bieżących ustawień.'; s.name = ''; }
          else if (service === 'profile_delete') s.msg = 'ok:Własny profil usunięty' + (r.dropped_plan ? ' razem z jego planem.' : '.');
          else if (service === 'profile_schedule') s.msg = `ok:Zaplanowano profil „${planNm}” od ${exDay(s.dFrom)} do ${exDay(s.dTo)} (włącza się sam, po ostatnim dniu wraca do poprzednich ustawień).`;
          else s.msg = 'ok:Plan profilu anulowany.';
          if (service !== 'profile_save') s.sel = null;
          if (service === 'profile_schedule') { s.dFrom = ''; s.dTo = ''; }
        } catch (e) { s.msg = 'err:' + exErr(e); }
        s.busy = false;
        this._exProf();
      },
      _exProfHtml() {
        const s = this._exS().prof;
        if (!s.data) {
          if (s.err) return `<div class="chart-empty" style="color:var(--red);">Nie udało się wczytać profili: ${exEsc(s.err)}</div><div class="ex-note">Wymaga integracji ze zmianą „profile pracy”.</div><button class="btn" data-pf="reload" style="margin-top:8px;">Spróbuj ponownie</button>`;
          return '<div class="chart-empty">Ładowanie…</div>';
        }
        const admin = this._dgIsAdmin();
        const profiles = (Array.isArray(s.data.profiles) ? s.data.profiles : []).filter((p) => p && p.id);
        const act = s.data.active && typeof s.data.active === 'object' ? s.data.active : null;
        const when = (iso) => { const d = new Date(iso); return isFinite(d) ? d.toLocaleString('pl-PL', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : ''; };
        const msg = s.msg ? (s.msg.startsWith('ok:') ? `<div class="ex-chip ok" style="display:block;border-radius:12px;padding:8px 12px;margin-bottom:10px;">${exEsc(s.msg.slice(3))}</div>`
          : `<div class="ex-chip bad" style="display:block;border-radius:12px;padding:8px 12px;margin-bottom:10px;">Nie udało się: ${exEsc(s.msg.slice(4))}</div>`) : '';
        const plan = s.data.plan && typeof s.data.plan === 'object' && s.data.plan.id && /^\d{4}-\d{2}-\d{2}$/.test(String(s.data.plan.from || '')) && /^\d{4}-\d{2}-\d{2}$/.test(String(s.data.plan.to || '')) ? s.data.plan : null;
        const planBanner = plan
          ? `<div data-role="profile-plan" style="background:var(--surface);border-radius:12px;padding:10px 12px;margin-bottom:12px;font-size:12px;line-height:1.5;">
              📅 ${plan.status === 'active' ? 'Trwa zaplanowany profil' : 'Zaplanowany profil'}: <b>${exEsc(plan.name || plan.id)}</b> od ${exEsc(exDay(plan.from))} do ${exEsc(exDay(plan.to))} (włącznie)${plan.status === 'active' ? '' : ' — włączy się sam pierwszego dnia'}. Po ostatnim dniu ustawienia wrócą do poprzednich.
              ${admin ? `<div style="margin-top:6px;"><button type="button" class="btn" data-pf="plan-clear" style="padding:6px 12px;font-size:12px;" ${s.busy ? 'disabled' : ''}>${plan.status === 'active' ? 'Zakończ teraz' : 'Anuluj plan'}</button></div>` : ''}</div>`
          : '';
        let banner = '';
        if (act) {
          const rs = (Array.isArray(act.restore) ? act.restore : []).map((r) => `<div style="color:var(--muted);">• ${exEsc(r.label)}: ${exEsc(r.now_text)} → ${exEsc(r.prev_text)}</div>`).join('');
          const ended = act.ended && act.ended.at;
          banner = `<div style="background:var(--surface);border-radius:12px;padding:10px 12px;margin-bottom:12px;font-size:12px;line-height:1.5;">
            ${ended ? `ℹ️ Profil <b>${exEsc(act.name || act.id)}</b> (od ${exEsc(when(act.since))}) przestał obowiązywać ${exEsc(when(act.ended.at))} — zmieniono ręcznie albo tryb wygasł sam.`
                    : `✅ Zastosowany profil: <b>${exEsc(act.name || act.id)}</b> (od ${exEsc(when(act.since))}).`}
            ${act.can_revert ? `<details style="margin-top:6px;"><summary style="cursor:pointer;">Co przywróci powrót do poprzednich ustawień</summary><div style="margin:4px 0 0 12px;">${rs}</div></details>
              <button type="button" class="btn" data-pf="revert" style="margin-top:8px;padding:8px 14px;flex-direction:row;gap:8px;" ${s.busy || !admin ? 'disabled' : ''}><span>↩️</span><span class="label">Wróć do ustawień sprzed profilu</span></button>` : ''}
          </div>`;
        }
        const chips = `<div style="display:flex;gap:8px;flex-wrap:wrap;">${profiles.map((p) => `<button type="button" class="btn" data-pf="pick" data-id="${exEsc(p.id)}" aria-pressed="${s.sel === p.id}"
            style="padding:10px 16px;flex-direction:row;gap:8px;${p.active ? 'outline:2px solid var(--green);' : (s.sel === p.id ? 'outline:2px solid var(--accent,#0a84ff);' : '')}"><span style="font-size:16px;">${exEsc(p.icon || '')}</span><span class="label">${exEsc(p.name)}${p.active ? ' ✓' : ''}</span></button>`).join('')}</div>`;
        let prev = '';
        const todayIso = (() => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; })();
        const sel = profiles.find((p) => p.id === s.sel);
        if (sel) {
          const rows = (Array.isArray(sel.changes) ? sel.changes : []).map((c) => c.available
            ? `<tr><td>${exEsc(c.label)}</td><td style="text-align:right;color:var(--muted);">${exEsc(c.now_text)}</td><td style="text-align:right;${c.differs ? 'font-weight:700;' : 'color:var(--muted);'}">${exEsc(c.target_text)}${c.differs ? '' : ' (bez zmian)'}</td></tr>`
            : `<tr><td style="color:var(--muted);">${exEsc(c.label)}</td><td colspan="2" style="text-align:right;color:var(--orange);">brak encji — pominięte</td></tr>`).join('');
          prev = `<div data-role="profile-preview" style="margin-top:12px;border-top:1px solid var(--line);padding-top:10px;">
            <div style="font-size:12px;margin-bottom:8px;">${exEsc(sel.desc || '')}</div>
            <div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr style="color:var(--muted);text-align:right;"><th style="text-align:left;font-weight:600;">Ustawienie</th><th style="font-weight:600;">Teraz</th><th style="font-weight:600;">Po profilu</th></tr></thead><tbody>${rows}</tbody></table></div>
            ${sel.nothing_to_change ? '<div class="ex-note">Wszystko jest już ustawione tak jak w tym profilu — nic się nie zmieni.</div>' : ''}
            ${admin ? '' : '<div class="ex-note" style="color:var(--orange);">Zmiana profilu wymaga konta administratora Home Assistant.</div>'}
            ${admin ? `<div data-role="profile-schedule" style="margin-top:12px;font-size:12px;"><div style="font-weight:600;margin-bottom:4px;">📅 Albo zaplanuj na daty (np. urlop)</div>
              <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
                <label>od <input type="date" data-pf-in="from" value="${exEsc(s.dFrom)}" min="${exEsc(todayIso)}" style="padding:6px;border-radius:8px;"></label>
                <label>do <input type="date" data-pf-in="to" value="${exEsc(s.dTo)}" min="${exEsc(s.dFrom || todayIso)}" style="padding:6px;border-radius:8px;"></label>
                <button type="button" class="btn" data-pf="schedule" data-id="${exEsc(sel.id)}" style="padding:8px 14px;" ${s.busy || !s.dFrom || !s.dTo || s.dTo < s.dFrom ? 'disabled' : ''}>Zaplanuj</button></div>
              <div style="color:var(--muted);margin-top:4px;">Włączy się sam pierwszego dnia, a po ostatnim dniu wróci do poprzednich ustawień (i do poprzedniego profilu, jeśli jakiś był).</div></div>` : ''}
            <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px;">
              <button type="button" class="btn" data-pf="apply" data-id="${exEsc(sel.id)}" style="padding:10px 16px;flex-direction:row;gap:8px;" ${s.busy || !admin ? 'disabled' : ''}><span>✅</span><span class="label">${s.busy ? 'Stosuję…' : `Zastosuj profil „${exEsc(sel.name)}”`}</span></button>
              <button type="button" class="btn" data-pf="cancel" style="padding:10px 16px;flex-direction:row;gap:8px;"><span class="label">Anuluj</span></button>
              ${admin && sel.custom ? `<button type="button" class="btn" data-pf="delete" data-id="${exEsc(sel.id)}" style="padding:10px 16px;flex-direction:row;gap:8px;" ${s.busy ? 'disabled' : ''}><span>🗑</span><span class="label">Usuń ten profil</span></button>` : ''}</div></div>`;
        }
        const nCustom = profiles.filter((p) => p.custom).length;
        const limit = Number.isFinite(Number(s.data.custom_limit)) ? Number(s.data.custom_limit) : 8;
        const icons = (Array.isArray(s.data.icons) ? s.data.icons : []).filter((x) => typeof x === 'string' && x.length <= 4);
        const saveForm = admin
          ? `<div data-role="profile-save" style="margin-top:14px;border-top:1px solid var(--line);padding-top:10px;font-size:12px;">
              <div style="font-weight:600;margin-bottom:4px;">💾 Zapisz bieżące ustawienia jako własny profil</div>
              <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
                <input type="text" data-pf-in="name" maxlength="24" placeholder="Nazwa, np. Weekend" value="${exEsc(s.name)}" style="padding:8px;border-radius:8px;min-width:160px;">
                ${icons.length ? `<select data-pf-in="icon" style="padding:8px;border-radius:8px;">${icons.map((ic) => `<option value="${exEsc(ic)}" ${s.icon === ic ? 'selected' : ''}>${exEsc(ic)}</option>`).join('')}</select>` : ''}
                <button type="button" class="btn" data-pf="save" style="padding:8px 14px;" ${s.busy ? 'disabled' : ''}>Zapisz</button></div>
              <div style="color:var(--muted);margin-top:4px;">Zapamiętuję tylko zwykłe ustawienia (sprzedaż, ładowanie z sieci, rezerwa, ostrożność PV, progi SOC…) — bez godzin, prądów, mocy i zabezpieczeń. Ta sama nazwa nadpisuje profil. Własnych profili: ${nCustom} z ${limit}.</div></div>`
          : '';
        return `${msg}${planBanner}${banner}<div class="ex-note" style="margin:0 0 10px;font-size:12px;">Gotowe zestawy ustawień jednym kliknięciem. Najpierw zobaczysz, co dokładnie się zmieni; po zastosowaniu EMS zapamięta poprzednie wartości i możesz do nich wrócić.</div>${chips}${prev}${saveForm}
          <div class="ex-note">Profil zmienia tylko zwykłe ustawienia EMS (te same, które można zmienić ręcznie) — nie rusza godzin, prądów ani mocy falownika. Gdy ręcznie zmienisz którekolwiek ustawienie z profilu, profil uznaje się za zakończony.</div>`;
      },
    });

    // =====================================================================
    //  KREATOR INSTALACJI: sprawdzenie konfiguracji i podgląd komend BEZ wysyłania czegokolwiek do falownika
    // =====================================================================
    const EX_ST_ICON = { ok: '✅', warn: '⚠️', error: '❌' };

    Object.assign(BmsPanel.prototype, {
      _exWiz() {
        const box = this._el('exWizBox');
        if (!box || this._activeTab !== 'diag') return;
        const s = this._exS(), w = s.wiz;
        if (!box.dataset.exBound) {
          box.dataset.exBound = '1';
          box.addEventListener('click', (ev) => {
            const b = ev.target && ev.target.closest ? ev.target.closest('[data-ex]') : null;
            if (!b) return;
            if (b.dataset.ex === 'wiz-run') this._exWizRun();
            else if (b.dataset.ex === 'wiz-copy') this._exWizCopy();
          });
        }
        const key = JSON.stringify([w.state, w.err, w.data ? [w.data.summary, w.data.version, (w.data.checks || []).length] : null, TC('text')]);
        if (box.dataset.exKey === key) return;
        box.dataset.exKey = key;
        const intro = 'Kreator sprawdza, czy integracja widzi encje falownika (tryb pracy, prąd ładowania, moc eksportu, TOU), czy działają ceny RCE i prognoza PV oraz co wykonałby każdy przycisk. <b>Niczego nie wysyła do falownika</b> — to tylko odczyt i podgląd.';
        const runBtn = (label) => `<button type="button" class="btn" data-ex="wiz-run" style="padding:10px 16px;flex-direction:row;gap:8px;" ${w.state === 'loading' ? 'disabled' : ''}><span>🧭</span><span class="label">${label}</span></button>`;
        if (w.state === 'idle') { box.innerHTML = `<div class="ex-note" style="margin:0 0 12px;font-size:12px;">${intro}</div>${runBtn('Sprawdź konfigurację')}`; return; }
        if (w.state === 'loading') { box.innerHTML = `<div class="chart-empty">Sprawdzam konfigurację…</div>`; return; }
        if (w.state === 'error') {
          box.innerHTML = `<div class="ex-chip bad" style="display:block;border-radius:12px;padding:10px 12px;margin-bottom:10px;">Nie udało się wykonać sprawdzenia: ${exEsc(w.err)}</div><div class="ex-note" style="margin:0 0 12px;">Kreator wymaga konta administratora Home Assistant i integracji w wersji z usługą <code>health_check</code>.</div>${runBtn('Spróbuj ponownie')}`;
          return;
        }
        const d = w.data || {}, sm = d.summary || {};
        const head = sm.ready
          ? `<span class="ex-chip ok">✅ gotowe do pracy</span>`
          : `<span class="ex-chip bad">❌ do poprawy: ${exEsc(sm.errors || 0)} błędów${sm.commands_failing ? `, ${exEsc(sm.commands_failing)} komend nie zadziała` : ''}</span>`;
        const chips = `<div class="ex-sum">${head}${sm.warnings ? `<span class="ex-chip warn">⚠ ${exEsc(sm.warnings)} uwag</span>` : ''}<span class="ex-chip">${exEsc(sm.ok || 0)} poprawnych</span>${d.version ? `<span class="ex-chip">wersja ${exEsc(d.version)}</span>` : ''}</div>`;
        const order = { error: 0, warn: 1, ok: 2 };
        const checks = (d.checks || []).slice().sort((a, b) => (order[a.status] ?? 3) - (order[b.status] ?? 3)).map((c) => `
          <div class="ex-chk"><span class="ic">${EX_ST_ICON[c.status] || '•'}</span><div><b>${exEsc(c.title)}</b><div>${exEsc(c.detail)}</div>${c.fix ? `<div class="fix">→ ${exEsc(c.fix)}</div>` : ''}</div></div>`).join('');
        const cmds = (d.commands || []).map((c) => `
          <details class="ex-cmd"${c.ok ? '' : ' open'}><summary><span>${c.ok ? '✅' : '❌'}</span><span>${exEsc(c.label)}</span></summary>
            ${c.error ? `<div class="st" style="color:var(--red);">${exEsc(c.error)}</div>` : ''}
            ${(c.steps || []).map((x) => `<div class="st">${x.exists ? '' : '⚠ '}<code>${exEsc(x.domain)}.${exEsc(x.domain === 'button' ? 'press' : 'set')}</code> → <code>${exEsc(x.entity_id)}</code>${x.value !== undefined && x.value !== null && x.value !== '' ? ` = <b>${exEsc(x.value)}</b>` : ''}</div>`).join('')}
          </details>`).join('');
        box.innerHTML = `${chips}${checks || '<div class="chart-empty">Brak wyników.</div>'}
          <div class="section-title" style="margin:16px 0 4px;padding-left:0;">Co zrobią przyciski (podgląd)</div>${cmds || '<div class="ex-note">Brak komend do wyświetlenia.</div>'}
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:14px;">${runBtn('Sprawdź ponownie')}
            <button type="button" class="btn" data-ex="wiz-copy" style="padding:10px 16px;flex-direction:row;gap:8px;"><span>📋</span><span class="label">Kopiuj raport</span></button></div>
          <div class="ex-note">Raport można wkleić znajomemu lub przy zgłaszaniu problemu — zawiera nazwy encji i wyniki testów, bez haseł i adresów.</div>`;
      },

      async _exWizRun() {
        const s = this._exS(), w = s.wiz;
        if (w.state === 'loading') return;
        w.state = 'loading'; w.err = ''; this._exWiz();
        try {
          const res = exResp(await exCall(this, 'health_check', {}));
          if (!res || !Array.isArray(res.checks)) throw new Error('nieprawidłowa odpowiedź integracji');
          w.data = res; w.state = 'done';
        } catch (e) { w.state = 'error'; w.err = exErr(e); }
        this._exWiz();
      },

      _exWizText() {
        const d = this._exS().wiz.data; if (!d) return '';
        const out = [`EMS komp-dec ${d.version || ''} — raport konfiguracji`, ''];
        (d.checks || []).forEach((c) => out.push(`[${String(c.status).toUpperCase()}] ${c.title}: ${c.detail}${c.fix ? ' → ' + c.fix : ''}`));
        out.push('', 'Komendy:');
        (d.commands || []).forEach((c) => {
          out.push(`${c.ok ? '[OK]' : '[BŁĄD]'} ${c.label}${c.error ? ' — ' + c.error : ''}`);
          (c.steps || []).forEach((x) => out.push(`    ${x.entity_id}${x.value !== undefined && x.value !== null && x.value !== '' ? ' = ' + x.value : ''}${x.exists ? '' : ' (brak encji)'}`));
        });
        return out.join('\n');
      },

      async _exWizCopy() {
        const txt = this._exWizText(); if (!txt) return;
        try {
          if (!navigator.clipboard || !navigator.clipboard.writeText) throw new Error('schowek niedostępny');
          await navigator.clipboard.writeText(txt);
          this._showToast('✅ Skopiowano raport');
        } catch (e) {
          this._showToast('❌ Nie udało się skopiować — ' + exErr(e), true);
        }
      },
    });

    // =====================================================================
    //  NOWOŚCI: nadpisanie planu, tabela planu godzina po godzinie, historia SOC (zakładka EMS)
    //           porównanie taryf i symulacja roczna (zakładka Zysk i log)
    //  Dane liczy integracja (sensor „Widok planu”, usługi analysis_get/analysis_set, override_set/override_clear).
    // =====================================================================
    const PLUS_CSS = `
      .px-note { font-size:11px; color:var(--muted); line-height:1.5; margin-top:8px; }
      .px-row { display:flex; flex-wrap:wrap; gap:8px; align-items:center; padding:8px 0; border-bottom:1px solid var(--line); }
      .px-row:last-child { border-bottom:none; }
      .px-row .nm { flex:1; min-width:150px; font-size:13px; color:var(--text); }
      .px-row .nm small { display:block; font-size:11px; color:var(--muted); }
      .px-row select, .px-row input { background:var(--surface); color:var(--text); border:1px solid var(--line); border-radius:10px; padding:7px 8px; font-size:13px; }
      .px-row input[type=number] { width:84px; }
      .px-row input[type=text] { width:120px; }
      .px-ovr { display:flex; justify-content:space-between; align-items:center; gap:10px; padding:8px 12px; margin-bottom:8px; border-radius:12px; background:rgba(10,132,255,.12); font-size:13px; color:var(--text); }
      .px-tbl-wrap { overflow-x:auto; -webkit-overflow-scrolling:touch; }
      table.px-tbl { width:100%; border-collapse:collapse; font-size:12px; min-width:520px; }
      table.px-tbl th { text-align:right; font-weight:500; color:var(--muted); padding:6px 6px; border-bottom:1px solid var(--line); white-space:nowrap; }
      table.px-tbl td { text-align:right; padding:5px 6px; border-bottom:1px solid var(--line); color:var(--text2); white-space:nowrap; }
      table.px-tbl th:first-child, table.px-tbl td:first-child, table.px-tbl th:nth-child(2), table.px-tbl td:nth-child(2) { text-align:left; }
      table.px-tbl.sim { min-width:0; table-layout:auto; }
      table.px-tbl.sim th, table.px-tbl.sim td { padding:6px 4px; }
      table.px-tbl.sim th:first-child, table.px-tbl.sim td:first-child { white-space:normal; width:100%; }
      table.px-tbl.sim th:nth-child(n+2), table.px-tbl.sim td:nth-child(n+2) { text-align:right; white-space:nowrap; }
      table.px-tbl tr.day td { background:var(--surface); color:var(--text); font-weight:600; text-align:left; }
      table.px-tbl tr.peak td:first-child { box-shadow: inset 3px 0 0 var(--orange); }
      table.px-tbl tr.tot td { font-weight:600; color:var(--text); border-bottom:none; }
      .px-act { display:inline-block; padding:2px 8px; border-radius:999px; font-size:11px; }
      /* tabela planu na wąskim ekranie (telefon): każda godzina to dwa wiersze, żeby były widoczne WSZYSTKIE kolumny bez przewijania w bok */
      .px-tbl-wrap.px-plan { container-type:inline-size; }
      @container (max-width: 560px) {
        table.px-tbl.plan { min-width:0 !important; display:block; font-size:12px; }
        table.px-tbl.plan thead { display:none; }
        table.px-tbl.plan tbody { display:block; }
        table.px-tbl.plan tr { display:block; border-bottom:1px solid var(--line); }
        table.px-tbl.plan tr.day td { display:block; border:0; padding:6px 8px; }
        table.px-tbl.plan tr:not(.day):not(.tot) { display:grid; grid-template-columns:46px repeat(5, minmax(0, 1fr)); column-gap:4px; align-items:center; padding:5px 0 6px; }
        table.px-tbl.plan tr:not(.day):not(.tot) td { display:block; border:0; padding:0; text-align:left; white-space:nowrap; min-width:0; }
        table.px-tbl.plan tr:not(.day):not(.tot) td:nth-child(1) { grid-area:1 / 1 / 3 / 2; font-weight:600; color:var(--text); padding-left:6px; }
        table.px-tbl.plan tr:not(.day):not(.tot) td:nth-child(2) { grid-area:1 / 2 / 2 / 5; overflow:hidden; text-overflow:ellipsis; }
        table.px-tbl.plan tr:not(.day):not(.tot) td:nth-child(8) { grid-area:1 / 5 / 2 / 7; text-align:right; font-weight:600; padding-right:6px; }
        table.px-tbl.plan tr:not(.day):not(.tot) td:nth-child(n+3):nth-child(-n+7) { grid-row:2; font-size:11px; overflow:hidden; text-overflow:ellipsis; }
        table.px-tbl.plan td:nth-child(3) { grid-column:2; } table.px-tbl.plan td:nth-child(4) { grid-column:3; } table.px-tbl.plan td:nth-child(5) { grid-column:4; }
        table.px-tbl.plan td:nth-child(6) { grid-column:5; } table.px-tbl.plan td:nth-child(7) { grid-column:6; }
        table.px-tbl.plan td[data-l]::before { content:attr(data-l) ' '; color:var(--muted); font-weight:400; }
        table.px-tbl.plan tr.tot { display:flex; flex-wrap:wrap; gap:2px 12px; padding:8px 6px; }
        table.px-tbl.plan tr.tot td { display:block; border:0; padding:0; text-align:left; white-space:normal; }
        table.px-tbl.plan tr.tot td:empty { display:none; }
      }
      .px-act.grid { background:rgba(10,132,255,.16); color:#0a84ff; }
      .px-act.sell { background:rgba(255,159,10,.18); color:var(--orange); }
      .px-act.pv { background:rgba(48,209,88,.16); color:var(--green); }
      .px-act.home { background:var(--surface); color:var(--text2); }
      .px-act.idle { background:transparent; color:var(--muted); }
      .px-neg { color:var(--green); } .px-pos { color:var(--red); }
      .px-hist svg { width:100%; height:auto; display:block; }
      .px-best td { font-weight:600; color:var(--green) !important; }
      .mp-bill { display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); gap:8px; margin-bottom:10px; }
      .mp-bill > div { padding:9px 12px; border-radius:14px; background:var(--card); border:1px solid var(--line); }
      .mp-bill small { display:block; font-size:11px; color:var(--muted); }
      .mp-bill b { font-size:18px; font-variant-numeric:tabular-nums; color:var(--text); }
      .mp-bill b.pos { color:var(--green); } .mp-bill b.neg { color:var(--red); }
      .mp-chips { display:flex; gap:6px; flex-wrap:wrap; margin-bottom:10px; }
      .mp-chip { display:inline-flex; gap:8px; align-items:center; padding:5px 6px 5px 12px; border-radius:999px; background:rgba(10,132,255,.12); font-size:12px; }
      .mp-chip button { border:0; background:transparent; color:var(--muted); font-size:14px; cursor:pointer; padding:0 6px; }
    `;
    const pxKind = { charge: 'Ładuj z sieci', no_sell: 'Nie sprzedawaj z baterii', no_grid: 'Nie ładuj z sieci' };
    const pxDayLabel = (iso) => {
      const t = new Date(); const p = (d) => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
      const tm = new Date(t.getTime() + 86400000);
      if (iso === p(t)) return 'Dziś'; if (iso === p(tm)) return 'Jutro'; return iso;
    };
    const pxZl = (v, sign) => { const n = exNum(v); if (n === null) return '—'; const a = Math.abs(n).toFixed(2).replace('.', ','); return (sign ? (n > 0 ? '+' : n < 0 ? '−' : '') : (n < 0 ? '−' : '')) + a + ' zł'; };
    const pxZl0 = (v) => { const n = exNum(v); if (n === null) return '—'; return (n < 0 ? '−' : '') + String(Math.round(Math.abs(n))).replace(/\B(?=(\d{3})+(?!\d))/g, ' ') + ' zł'; };
    const pxPrice = (v) => (exNum(v) === null ? '—' : exNum(v).toFixed(2).replace('.', ','));

    Object.assign(BmsPanel.prototype, {
      _exPx() {
        const s = this._exS();
        if (!s.px) s.px = { ovr: { charge: { h: 2, t: 80 }, no_sell: { h: 4 }, no_grid: { h: 8 } }, an: { data: null, at: 0, loading: false, err: '' } };
        return s.px;
      },
      _exPlus() {
        const root = this.shadowRoot; if (!root) return;
        if (!root.getElementById('exPlusStyle')) { const st = document.createElement('style'); st.id = 'exPlusStyle'; st.textContent = PLUS_CSS; root.appendChild(st); }
        if (this._tabNeeds('ems') || this._tabNeeds('charts')) {
          this._safe(() => this._exOvr());
          this._safe(() => this._exTable());
          this._safe(() => this._exHist());
        }
        if (this._tabNeeds('log')) this._safe(() => this._exAnalysis());
        this._safe(() => this._exMain());
      },

      // ------------------------------------------------------------ ekran główny: rachunek dnia i znaczniki aktywnych nadpisań
      _exMain() {
        const box = this._el('exMainBox'); if (!box || !this._tileOn('main-plan')) return;
        const a = this._pvAttrs ? this._pvAttrs() : {};
        const ps = this._hass.states[this._eid('sensor', 'profit_today')];
        const pa = (ps && ps.attributes) || {};
        const day = (pa.sums && pa.sums.day) || null;
        const sv = pa.extras && pa.extras.day && pa.extras.day.savings;
        const ovr = Array.isArray(a.overrides) ? a.overrides : [];
        const key = JSON.stringify([day, sv, ovr.map(o => o.id)]);
        if (box.dataset.exKey === key) return;
        box.dataset.exKey = key;
        const zl = (v) => { const n = exNum(v); return n === null ? '—' : (n < 0 ? '−' : '') + Math.abs(n).toFixed(2).replace('.', ',') + ' zł'; };
        const tile = (l, v, cls) => `<div><small>${exEsc(l)}</small><b class="${cls || ''}">${v}</b></div>`;
        let bill = '';
        if (day) {
          const net = exNum(day.net), sav = sv && exNum(sv.saving);
          bill = '<div class="mp-bill">'
            + (sav !== null && sav !== undefined ? tile('Dziś oszczędzone', (sav >= 0 ? '+' : '') + zl(sav), sav >= 0 ? 'pos' : 'neg') : '')
            + tile('Sprzedałem dziś', zl(day.revenue), 'pos')
            + tile('Kupiłem dziś', zl(day.cost))
            + (sv && exNum(sv.without_cost) !== null ? tile('Bez PV i baterii byłoby', zl(sv.without_cost)) : (net !== null ? tile('Saldo dziś', zl(net), net >= 0 ? 'pos' : 'neg') : ''))
            + '</div>';
        }
        const chips = ovr.length ? '<div class="mp-chips">' + ovr.map(o => `<span class="mp-chip">🧭 ${exEsc(o.text || pxKind[o.kind] || o.kind)}<button type="button" data-mp-del="${exEsc(o.id)}" aria-label="Usuń nadpisanie" title="Usuń">✕</button></span>`).join('') + '</div>' : '';
        box.innerHTML = bill + chips;
        if (!box.dataset.exBound) {
          box.dataset.exBound = '1';
          box.addEventListener('click', async (ev) => {
            const t = ev.target.closest && ev.target.closest('[data-mp-del]'); if (!t) return;
            try {
              await exCall(this, 'override_clear', { id: t.dataset.mpDel }); this._showToast('✅ Usunięto nadpisanie');
              box.dataset.exKey = '';
              setTimeout(() => this._exMain(), 1200);
            } catch (e) { this._showToast('❌ ' + exErr(e), true); }
          });
        }
      },

      // ------------------------------------------------------------ ręczne nadpisanie planu (14)
      _exOvr() {
        const box = this._el('exOvrBox'); if (!box) return;
        const px = this._exPx();
        const a = this._pvAttrs ? this._pvAttrs() : {};
        const list = Array.isArray(a.overrides) ? a.overrides : [];
        const key = JSON.stringify([list.map(o => o.id), TC('text')]);
        if (box.dataset.exKey === key) return;
        box.dataset.exKey = key;
        const sel = (k, opts, cur) => `<select data-px-h="${k}">${opts.map(h => `<option value="${h}" ${Number(cur) === h ? 'selected' : ''}>${h} h</option>`).join('')}</select>`;
        const row = (k, name, hint, opts, extra) => `<div class="px-row"><div class="nm">${exEsc(name)}<small>${exEsc(hint)}</small></div>${sel(k, opts, px.ovr[k].h)}${extra || ''}<button class="btn" data-px-set="${k}" style="padding:7px 14px;">Ustaw</button></div>`;
        box.innerHTML = (list.length ? list.map(o => `<div class="px-ovr"><span>🧭 ${exEsc(o.text || pxKind[o.kind] || o.kind)}</span><button class="btn" data-px-del="${exEsc(o.id)}" style="padding:5px 12px;">Usuń</button></div>`).join('')
            + (list.length > 1 ? '<div style="text-align:right;margin-bottom:6px;"><button class="btn" data-px-del="*" style="padding:5px 12px;">Usuń wszystkie</button></div>' : '') : '')
          + row('charge', 'Ładuj z sieci teraz', 'Do wybranego poziomu SOC, potem ładowanie samo się kończy.', [1, 2, 3, 4, 6, 8],
            `<span style="font-size:12px;color:var(--muted);">do</span><input type="number" min="5" max="100" step="5" value="${exEsc(px.ovr.charge.t)}" data-px-t="charge" /><span style="font-size:12px;color:var(--muted);">%</span>`)
          + row('no_sell', 'Nie sprzedawaj z baterii', 'Plan nie sprzeda energii z baterii przez ten czas.', [2, 4, 8, 12, 24, 48])
          + row('no_grid', 'Nie ładuj z sieci', 'Plan i harmonogram nie włączą ładowania z sieci przez ten czas.', [4, 8, 12, 24, 48])
          + '<div class="px-note">Nadpisanie wygasa samo, a „nie sprzedawaj” i „nie ładuj z sieci” obowiązują w całym czasie ich trwania (plan nie proponuje wtedy sprzedaży / ładowania z sieci). Zabezpieczenia (zakaz sprzedaży energii z sieci, minimalny SOC) działają nadal.</div>';
        if (!box.dataset.exBound) {
          box.dataset.exBound = '1';
          box.addEventListener('change', (ev) => {
            const h = ev.target && ev.target.dataset && ev.target.dataset.pxH, t = ev.target && ev.target.dataset && ev.target.dataset.pxT;
            if (h) px.ovr[h].h = Number(ev.target.value);
            if (t) px.ovr[t].t = Number(ev.target.value);
          });
          box.addEventListener('click', async (ev) => {
            const set = ev.target.closest && ev.target.closest('[data-px-set]'), del = ev.target.closest && ev.target.closest('[data-px-del]');
            try {
              if (set) {
                const k = set.dataset.pxSet, d = { kind: k, hours: px.ovr[k].h };
                if (k === 'charge') d.target = px.ovr.charge.t;
                set.disabled = true;
                await exCall(this, 'override_set', d);
                this._showToast('✅ Nadpisanie ustawione');
              } else if (del) {
                await exCall(this, 'override_clear', del.dataset.pxDel === '*' ? {} : { id: del.dataset.pxDel });
                this._showToast('✅ Usunięto nadpisanie');
              } else return;
              box.dataset.exKey = '';
              setTimeout(() => this._exPlus(), 1200);
            } catch (e) { this._showToast('❌ ' + exErr(e), true); if (set) set.disabled = false; }
          });
        }
      },

      // ------------------------------------------------------------ tabela planu (13)
      _exTable() {
        const box = this._el('exTblBox'); if (!box) return;
        const a = this._pvAttrs ? this._pvAttrs() : {};
        const rows = Array.isArray(a.table) ? a.table : [];
        const key = JSON.stringify([a.generated_at, rows.length, TC('text'), new Date().getHours()]);
        if (box.dataset.exKey === key) return;
        box.dataset.exKey = key;
        if (!rows.length) { box.innerHTML = '<div class="chart-empty">Plan jeszcze nie jest policzony albo nie ma danych (SOC, prognozy).</div>'; return; }
        let day = '', html = '';
        rows.forEach((r) => {
          if (r.day !== day) { day = r.day; html += `<tr class="day"><td colspan="8">${exEsc(pxDayLabel(day))}</td></tr>`; }
          const c = exNum(r.cost);
          html += `<tr class="${r.peak ? 'peak' : ''}"><td>${String(r.h).padStart(2, '0')}:00</td><td><span class="px-act ${exEsc(r.action)}">${exEsc(r.label)}</span></td>`
            + `<td data-l="Kup">${pxPrice(r.buy)}</td><td data-l="Sprz">${pxPrice(r.sell)}</td><td data-l="PV">${exFmt(r.pv, 1)}</td><td data-l="Dom">${exFmt(r.load, 1)}</td><td data-l="SOC">${exFmt(r.soc, 0, '%')}</td>`
            + `<td class="${c < -0.005 ? 'px-neg' : c > 0.005 ? 'px-pos' : ''}">${pxZl(c, true)}</td></tr>`;
        });
        const t = a.table_totals || {};
        box.innerHTML = (this._planSummaryHtml ? this._planSummaryHtml(rows) : '') + `<div class="px-tbl-wrap px-plan"><table class="px-tbl plan"><thead><tr><th>Godz.</th><th>Akcja</th><th>Kup zł</th><th>Sprz. zł</th><th>PV kWh</th><th>Dom kWh</th><th>SOC</th><th>Koszt</th></tr></thead><tbody>${html}`
          + `<tr class="tot"><td colspan="2">Razem</td><td colspan="4" style="text-align:left;">pobór ${exFmt(t.import_kwh, 1)} kWh · oddanie ${exFmt(t.export_kwh, 1)} kWh</td><td></td><td class="${exNum(t.cost) < 0 ? 'px-neg' : 'px-pos'}">${pxZl(t.cost, true)}</td></tr></tbody></table></div>`
          + '<div class="px-note">Szacunek z planu (bez strat i opłat stałych): koszt = pobór z sieci × cena zakupu − oddanie × cena sprzedaży; minus = przychód. Pomarańczowy pasek = godziny szczytu taryfy. Plan obejmuje najbliższe ~30 godzin, a gdy ceny na jutro są już znane — całą resztę dzisiaj i jutro (do ~47 h).</div>';
      },

      // ------------------------------------------------------------ historia SOC (20)
      _exHist() {
        const box = this._el('exHistBox'); if (!box) return;
        const a = this._pvAttrs ? this._pvAttrs() : {};
        const days = Array.isArray(a.soc_history) ? a.soc_history : [];
        const key = JSON.stringify([days.map(d => [d.date, (d.soc || []).filter(v => v !== null).length, d.soc && d.soc[23]]), TC('text')]);
        if (box.dataset.exKey === key) return;
        box.dataset.exKey = key;
        if (!days.length || days.every(d => d.empty)) { box.innerHTML = '<div class="chart-empty">Historia SOC zbiera się od uruchomienia tej wersji integracji — pierwsze dane pojawią się po kilku godzinach.</div>'; return; }
        const W = 840, H = 230, L = 34, R = 6, T = 10, B = 28, n = days.length * 24;
        const pw = (W - L - R) / n, y = (v) => T + (H - T - B) * (1 - v / 100);
        let bands = '', pts = [], plan = [], lbl = '', hover = '', gap = false;
        days.forEach((d, di) => {
          const x0 = L + di * 24 * pw;
          if (di) bands += `<line x1="${x0}" x2="${x0}" y1="${T}" y2="${H - B}" stroke="var(--line)" />`;
          lbl += `<text x="${x0 + 12 * pw}" y="${H - 10}" text-anchor="middle" font-size="11" fill="var(--muted)">${exEsc(d.date.slice(8, 10) + '.' + d.date.slice(5, 7))}</text>`;
          for (let h = 0; h < 24; h++) {
            const x = x0 + h * pw, soc = d.soc && d.soc[h], g = d.grid && d.grid[h], s = d.sale && d.sale[h];
            if (g || s) bands += `<rect x="${x}" y="${T}" width="${pw}" height="${H - T - B}" fill="${g ? 'rgba(10,132,255,.22)' : 'rgba(255,159,10,.26)'}" />`;
            if (typeof soc === 'number') { pts.push((gap || !pts.length ? 'M' : 'L') + (x + pw / 2).toFixed(1) + ' ' + y(soc).toFixed(1)); gap = false; } else gap = true;
            const p = d.plan && d.plan[h]; if (typeof p === 'number') plan.push((plan.length ? 'L' : 'M') + (x + pw / 2).toFixed(1) + ' ' + y(p).toFixed(1));
            hover += `<rect x="${x}" y="${T}" width="${pw}" height="${H - T - B}" fill="transparent"><title>${exEsc(d.date)} ${String(h).padStart(2, '0')}:00 — SOC ${typeof soc === 'number' ? soc.toFixed(0) + '%' : 'brak danych'}${g ? ' · ładowanie z sieci' : ''}${s ? ' · sprzedaż z baterii' : ''}</title></rect>`;
          }
        });
        const grid = [0, 25, 50, 75, 100].map(v => `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="var(--line)" stroke-dasharray="${v === 0 || v === 100 ? '' : '3 4'}"/><text x="${L - 4}" y="${y(v) + 4}" text-anchor="end" font-size="10" fill="var(--muted)">${v}</text>`).join('');
        box.innerHTML = `<div class="px-hist"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Historia poziomu baterii z ostatnich dni">${grid}${bands}<path d="${plan.join(' ')}" fill="none" stroke="var(--muted)" stroke-width="1.5" stroke-dasharray="5 4" opacity=".8"/><path d="${pts.join(' ')}" fill="none" stroke="var(--green)" stroke-width="2.2" stroke-linejoin="round"/>${lbl}${hover}</svg></div>`
          + '<div class="ex-leg"><span><i class="line" style="background:var(--green)"></i>SOC rzeczywisty</span><span><i class="line" style="background:var(--muted)"></i>plan z rana (tylko dziś)</span><span><i style="background:rgba(10,132,255,.4)"></i>ładowanie z sieci</span><span><i style="background:rgba(255,159,10,.45)"></i>sprzedaż z baterii</span></div>'
          + '<div class="px-note">Okna oznaczone z liczników godzinowych (pobór ≥ 0,3 kWh przy ładowaniu baterii; oddanie ≥ 0,3 kWh przy rozładowaniu baterii) — to oszacowanie, nie zapis komend.</div>';
      },

      // ------------------------------------------------------------ porównanie taryf i symulacja roczna (11, 12)
      async _exAnLoad() {
        const s = this._exPx().an;
        if (s.loading) return;
        s.loading = true;
        try { s.data = exResp(await exCall(this, 'analysis_get', {})) || {}; s.err = ''; }
        catch (e) { s.err = exErr(e); }
        finally { s.loading = false; s.at = Date.now(); }
        this._el('exSimBox') && (this._el('exSimBox').dataset.exKey = '');
        this._exAnalysis();
      },
      _exAnalysis() {
        const sb = this._el('exSimBox'); if (!sb) return;
        const an = this._exPx().an;
        if (!an.loading && Date.now() - an.at > 300000) this._exAnLoad();
        const key = JSON.stringify([an.at, an.err, TC('text')]);
        if (sb && sb.dataset.exKey !== key) { sb.dataset.exKey = key; sb.innerHTML = this._exSimHtml(); this._exAnBind(sb); }
      },
      _exAnBind(box) {
        if (box.dataset.exBound) return;
        box.dataset.exBound = '1';
        box.addEventListener('click', async (ev) => {
          const b = ev.target.closest && ev.target.closest('[data-px-an]'); if (!b) return;
          const val = (id) => { const e = this._el(id); const v = e ? String(e.value).trim().replace(',', '.') : ''; return v === '' ? null : v; };
          const num = (id) => { const v = val(id); return v === null ? null : Number(v); };
          try {
            const d = { invest_pv: num('pxIp'), invest_batt: num('pxIb'), batt_zl_kwh: num('pxIk'), g11: num('pxTg'), dyn_markup: num('pxTd') };
            const zp = num('pxTzp'), zo = num('pxTzo'), zw = val('pxTzw');
            d.zone = zp !== null && zo !== null ? { peak: zp, off: zo, windows: zw || '6-13,15-22' } : null;
            b.disabled = true;
            await exCall(this, 'analysis_set', d);
            this._showToast('✅ Zapisano');
            this._exPx().an.at = 0; this._exAnLoad();
          } catch (e) { this._showToast('❌ ' + exErr(e), true); b.disabled = false; }
        });
      },
      // Ujemne ceny (sprzedaży / zakupu) z godzinowych koszyków: ile godzin, ile kWh i ile to kosztowało / dało.
      _exNegHtml(data) {
        const neg = data && data.neg; if (!neg) return '';
        const zl2 = (v) => { const n = exNum(v); return n === null ? '—' : exFmt(n, 2) + ' zł'; };
        if (!(neg.sell_h > 0 || neg.buy_h > 0)) return `<div class="ex-sum"><span class="ex-chip ok">✓ ceny ujemne: brak w ostatnich ${exEsc(String(neg.days))} dobach</span></div>`;
        let h = '';
        if (neg.sell_h > 0) h += `<div class="ex-sum"><span class="ex-chip warn" style="white-space:normal;">📉 ujemna cena SPRZEDAŻY: ${exEsc(String(neg.sell_h))} h w ${exEsc(String(neg.sell_days))} z ${exEsc(String(neg.days))} dób · wyeksportowano ${exFmt(neg.sell_kwh, 1)} kWh · dopłata ${zl2(neg.sell_cost)}${neg.sell_cost_year > 0 ? ` (≈ ${pxZl0(neg.sell_cost_year)} / rok${neg.extrapolated ? ', ekstrapolacja' : ''})` : ''}</span></div>`;
        if (neg.buy_h > 0) h += `<div class="ex-sum"><span class="ex-chip" style="white-space:normal;">📉 ujemna cena ZAKUPU: ${exEsc(String(neg.buy_h))} h w ${exEsc(String(neg.buy_days))} z ${exEsc(String(neg.days))} dób · pobrano ${exFmt(neg.buy_kwh, 1)} kWh · przychód ${zl2(neg.buy_gain)}</span></div>`;
        if (neg.sell_h > 0) {
          const thr = exNum(data.neg_threshold);
          h += data.neg_reaction
            ? `<div class="px-note">Reakcja na niskie/ujemne ceny jest włączona (próg ${thr === null ? '0' : exFmt(thr, 2)} zł/kWh). Dopłata dotyczy godzin sprzed jej włączenia albo nadwyżki PV, której samo wstrzymanie sprzedaży z baterii nie odcina.</div>`
            : '<div class="px-note">💡 Włącz „Reakcja na niskie/ujemne ceny RCE” (Ustawienia): EMS przestanie wtedy sprzedawać z baterii przy cenie poniżej progu i nie dopłacisz do eksportu.</div>';
        }
        return h;
      },
      _exSimHtml() {
        const an = this._exPx().an;
        if (!an.data) return an.err ? `<div class="chart-empty" style="color:var(--red);">Nie udało się wczytać: ${exEsc(an.err)}</div>` : '<div class="chart-empty">Ładowanie…</div>';
        const sim = an.data.sim, cfg = an.data.cfg || {}, au = an.data.auto || {};
        const inp = (id, v, ph) => `<input type="text" inputmode="decimal" id="${id}" value="${v == null ? '' : exEsc(String(v))}" placeholder="${ph}" style="width:110px" />`;
        const zc = cfg.zone || {}, az = au.zone || {};
        const ph = (v, t) => (v == null ? t : 'auto ' + exFmt(v, 2));
        const form = '<div class="px-row"><div class="nm">Nakłady (do liczenia zwrotu)<small>instalacja PV i bateria, zł; cena dokupienia baterii za 1 kWh</small></div>' + inp('pxIp', cfg.invest_pv, 'PV zł') + inp('pxIb', cfg.invest_batt, 'bateria zł') + inp('pxIk', cfg.batt_zl_kwh, 'zł za kWh baterii')
          + '<button class="btn" data-px-an="invest" style="padding:7px 14px;">Zapisz</button></div>'
          + '<div class="px-row"><div class="nm">Porównanie taryf<small>stawki do porównania, zł/kWh. Puste pola liczą się automatycznie z Twoich cen (strefowa, dynamiczna); G11 trzeba wpisać</small></div>' + inp('pxTg', cfg.g11, 'G11 zł/kWh') + inp('pxTd', cfg.dyn_markup, ph(au.dyn_markup, 'narzut dynamic'))
          + inp('pxTzp', zc.peak, ph(az.peak, 'strefa: szczyt')) + inp('pxTzo', zc.off, ph(az.off, 'strefa: poza')) + inp('pxTzw', zc.windows, az.windows && az.peak != null ? 'auto ' + az.windows : 'okna np. 6-13,15-22')
          + '<button class="btn" data-px-an="invest" style="padding:7px 14px;">Zapisz</button></div>';
        const bt = an.data.batt;
        const battBox = bt && Array.isArray(bt.rows) && bt.rows.length
          ? `<div class="px-tbl-wrap"><table class="px-tbl sim" id="exBattTbl"><thead><tr><th style="text-align:left;">Czy większa bateria się opłaca? (teraz ${exFmt(bt.cap_kwh, 1)} kWh)</th><th>Zysk / rok</th><th>Zwrot</th></tr></thead><tbody>`
            + bt.rows.map(r => `<tr><td style="text-align:left;">+${exFmt(r.extra_kwh, 0)} kWh (razem ${exFmt(r.cap_kwh, 1)} kWh)</td><td style="color:${exNum(r.saving_year) > 0 ? 'var(--green)' : 'inherit'};">${exNum(r.saving_year) > 0 ? '+' : ''}${exFmt(r.saving_year, 0)} zł</td><td>${r.payback_years != null ? exFmt(r.payback_years, 1) + ' lat' : '—'}</td></tr>`).join('')
            + `</tbody></table></div><div class="px-note">${exEsc(bt.note || '')}${cfg.batt_zl_kwh ? '' : ' Wpisz cenę dokupienia baterii (zł za kWh) poniżej, żeby zobaczyć czas zwrotu.'}</div>`
          : '';
        const tc = an.data.tariff, tcRows = tc && Array.isArray(tc.rows) ? tc.rows : [];
        const tcol = (v) => { const n = exNum(v); return n === null ? '' : (n < -0.005 ? 'color:var(--green);' : (n > 0.005 ? 'color:var(--red);' : '')); };
        const tcSign = (v) => { const n = exNum(v); return n === null ? '—' : (n > 0 ? '+' : '') + exFmt(n, 2) + ' zł'; };
        const tariffBox = tcRows.length > 1 && tc.days > 0
          ? `<div class="px-tbl-wrap"><table class="px-tbl sim"><thead><tr><th style="text-align:left;">Ile zapłaciłbyś za ten sam pobór z sieci (${exEsc(String(tc.days))} dób, ${exFmt(tc.import_kwh, 1)} kWh)</th><th>Na miesiąc</th><th>Różnica</th></tr></thead><tbody>`
            + tcRows.map(r => `<tr class="${tc.best === r.key ? 'px-best' : ''}"><td style="text-align:left;">${exEsc(r.name)}${r.what_if ? ' <small>(scenariusz, nie taryfa)</small>' : ''}</td><td>${exFmt(r.per_month, 2)} zł</td><td style="${tcol(r.diff_month)}">${r.key === 'actual' ? '—' : tcSign(r.diff_month)}</td></tr>`).join('')
            + `</tbody></table></div><div class="px-note">${exEsc(tc.note || '')} Wiersze „6 najdroższych / najtańszych godzin” pokazują, ile kosztuje samo przesunięcie poboru w czasie.</div>`
          : '';
        if (!sim) return tariffBox + battBox + '<div class="chart-empty">Za mało pełnych dób z danymi godzinowymi (potrzeba co najmniej 3) — symulacja pojawi się po kilku dniach pracy.</div>' + form;
        const rows = (sim.scenarios || []).map(s => `<tr class="${s.key === 'ems' ? 'px-best' : ''}"><td style="text-align:left;">${exEsc(s.name)}</td><td>${pxZl0(s.period)}</td><td>${pxZl0(s.year)}</td></tr>`).join('');
        const sv = sim.savings_year || {}, pb = sim.payback || {};
        const yrs = (v) => exFmt(v, 1) + ' lat';
        // chip z oszczędnością: ujemna wartość = scenariusz wychodzi drożej, więc nie nazywamy tego „oszczędnością” na zielono
        const sav = (ico, label, v, suffix) => { const n = exNum(v); return `<span class="ex-chip ${n !== null && n < 0 ? 'warn' : 'ok'}">${ico} ${label} ≈ ${pxZl0(v)}${suffix || ''}</span>`; };
        const sc = {}; (sim.scenarios || []).forEach(s => { sc[s.key] = exNum(s.period); });
        const pvWorse = sc.nopv != null && sc.nobat != null && sc.nobat > sc.nopv;
        const neg = an.data.neg || null, hasNeg = !!(neg && (neg.sell_h > 0 || neg.buy_h > 0));
        const negBox = this._exNegHtml(an.data);
        const pvWorseTxt = !pvWorse ? '' : (hasNeg
          ? `⚠ „Samo PV” wychodzi drożej niż „Bez PV”, bo w danych są godziny z ujemną ceną (${exEsc(String(neg.sell_h))} h sprzedaży, ${exEsc(String(neg.buy_h))} h zakupu) — to nie błąd obliczeń, ale wynik roczny jest przez to mało wiarygodny.`
          : (neg ? `⚠ „Samo PV” wychodzi drożej niż „Bez PV”, a w ostatnich ${exEsc(String(neg.days))} dobach nie widzę godzin z ujemną ceną — więc to najpewniej błędne ceny w danych (np. zły sensor ceny zakupu/sprzedaży albo stare doby). Sprawdź ceny w zakładce „Ceny”. Wynik roczny jest niewiarygodny.`
                 : '⚠ „Samo PV” wychodzi drożej niż „Bez PV” — to możliwe tylko przy ujemnych cenach albo błędnych cenach w danych. Wynik roczny jest niewiarygodny.'));
        return tariffBox + battBox + `<div class="px-tbl-wrap"><table class="px-tbl sim"><thead><tr><th style="text-align:left;">Scenariusz</th><th>${exEsc(String(sim.days))} dób</th><th>Rocznie</th></tr></thead><tbody>${rows}</tbody></table></div>`
          + `<div class="ex-sum" style="margin-top:10px;">${sav('☀️', 'PV', sv.pv, ' / rok')}${sav('🔋', 'bateria', sv.battery, ' / rok')}${sav('🤖', 'EMS', sv.ems, ' / rok')}<span class="ex-chip">razem ≈ ${pxZl0(sv.total)} / rok</span></div>`
          + (pvWorseTxt ? `<div class="ex-sum"><span class="ex-chip warn" style="white-space:normal;">${pvWorseTxt}</span></div>` : '') + negBox
          + (Object.keys(pb).length ? `<div class="ex-sum"><span class="ex-chip">${pb.pv_years != null ? '⏱ zwrot PV: ' + yrs(pb.pv_years) : ''}</span><span class="ex-chip">${pb.battery_years != null ? '⏱ zwrot baterii (z EMS): ' + yrs(pb.battery_years) : ''}</span><span class="ex-chip">${pb.total_years != null ? '⏱ całość: ' + yrs(pb.total_years) : ''}</span></div>` : '')
          + (sim.extrapolated ? '<div class="ex-sum"><span class="ex-chip warn">⚠ mniej niż rok danych — wynik roczny to ekstrapolacja; zimą i latem wyjdzie inaczej</span></div>' : '')
          + form + `<div class="px-note">${exEsc(sim.note || '')} „Prosta strategia” to symulacja baterii bez planera (ładuje się z nadwyżki PV, rozładowuje na dom). Nie uwzględnia opłat stałych, zmian cen ani degradacji.</div>`;
      },
    });

  };
  install.contract = 1;
  install.version = '0.9.6.0';
  window.__bmsExtrasInstall = install;
})();
