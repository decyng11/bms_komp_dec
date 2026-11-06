const { openCard, chromium } = require('./ui_env');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

const DAVID = { read_holding_registers: { fields: { device: {}, address: {}, count: {} }, response: { optional: true } }, write_multiple_registers: { fields: { device: {}, address: {}, values: {} } } };
const ORIG = { read_holding_register: { fields: { device: {}, register: {} } }, read_multiple_holding_registers: { fields: { device: {}, register: {}, count: {} } },
  write_holding_register: { fields: { device: {}, register: {}, value: {} } }, write_multiple_holding_registers: { fields: { device: {}, register: {}, values: {} } } };

async function setup(b, services, { noResp } = {}) {
  const e = await openCard(b, {});
  await e.q(({ services, noResp }) => {
    window.__services = services; window.__mb = [];
    const proto = Object.getPrototypeOf(__el); const desc = Object.getOwnPropertyDescriptor(proto, 'hass');
    Object.defineProperty(__el, 'hass', { set(v) { if (window.__services) v.services = { solarman: window.__services }; desc.set.call(__el, v); }, get() { return desc.get.call(__el); }, configurable: true });
    __el.hass = __mk();
    window.__svc = {};
    ['read_holding_registers', 'read_holding_register', 'read_multiple_holding_registers', 'write_multiple_registers', 'write_holding_register', 'write_multiple_holding_registers'].forEach((n) => {
      window.__svc['solarman.' + n] = (m) => { window.__mb.push({ service: n, data: m.service_data, ret: m.return_response }); if (noResp && m.return_response) throw new Error('Service does not support responses'); return n.startsWith('read') && m.return_response ? { response: { registers: [1234] } } : {}; };
    });
  }, { services, noResp });
  await e.q(() => __el.shadowRoot.querySelector('[data-tab="diag"]').click());
  await e.page.waitForFunction(() => !!__el.shadowRoot.getElementById('dgPw'), null, { timeout: 8000 });
  await e.q(() => { const s = __el.shadowRoot; s.getElementById('dgPw').value = 'slonce'; s.querySelector('[data-act=unlock]').click(); });
  await e.page.waitForFunction(() => !!__el.shadowRoot.getElementById('dgBody'), null, { timeout: 5000 });
  await e.q(() => __el.shadowRoot.querySelector('[data-sec=adv]').click());
  await e.page.waitForFunction(() => !!__el.shadowRoot.getElementById('dgMbReg'), null, { timeout: 5000 });
  return e;
}
const read = async (e, reg, qty) => { await e.q(([r, q]) => { const s = __el.shadowRoot; s.getElementById('dgMbReg').value = r; s.getElementById('dgMbQty').value = q; s.querySelector('[data-act=mb-read]').click(); }, [reg, String(qty)]); await sleep(500); };
const write = async (e, reg, val, confirm = true) => {
  await e.q(([r, v]) => { const s = __el.shadowRoot; s.getElementById('dgMbReg').value = r; s.getElementById('dgMbVal').value = v; s.querySelector('[data-act=mb-write]').click(); }, [reg, String(val)]);
  await sleep(300);
  if (confirm) await e.q(() => { const m = __el.shadowRoot.querySelector('.dg-modal'); if (!m) return; const n = m.querySelector('#dgNeed'); if (n) n.click(); m.querySelector('[data-id=ok]').click(); });
  else await e.q(() => { const m = __el.shadowRoot.querySelector('.dg-modal'); if (m) m.querySelector('[data-id=cancel]').click(); });
  await sleep(500);
};
const out = (e) => e.q(() => __el.shadowRoot.getElementById('dgMbOut').textContent);

(async () => {
  const b = await chromium.launch();

  // A. davidrapan/ha-solarman
  let e = await setup(b, DAVID);
  await read(e, '0x0100', 1);
  let mb = await e.q(() => window.__mb);
  ok(mb.length === 1 && mb[0].service === 'read_holding_registers' && JSON.stringify(mb[0].data) === JSON.stringify({ device: 'dev123', address: 256, count: 1 }) && mb[0].ret === true, 'david: odczyt → read_holding_registers {device, address, count} z odpowiedzią: ' + JSON.stringify(mb[0]));
  ok(/1234/.test(await out(e)) && /solarman\.read_holding_registers/.test(await out(e)), 'david: wynik odczytu wyświetlony');
  await read(e, '300', 4);
  mb = await e.q(() => window.__mb);
  ok(mb[1].data.count === 4 && mb[1].data.address === 300, 'david: odczyt 4 rejestrów → count=4');
  await write(e, '0x0100', 500);
  mb = await e.q(() => window.__mb);
  ok(mb.length === 3 && mb[2].service === 'write_multiple_registers' && JSON.stringify(mb[2].data) === JSON.stringify({ device: 'dev123', address: 256, values: [500] }) && mb[2].ret === false, 'david: zapis → write_multiple_registers {device, address, values:[500]}: ' + JSON.stringify(mb[2]));
  ok(/OK — zapis wysłany/.test(await out(e)), 'david: potwierdzenie zapisu');
  ok(await e.q(() => (__el._dgLS().get('bms_diag_log') || []).some((x) => x.eid === 'modbus:256' && String(x.to) === '500')), 'david: zapis trafił do dziennika zmian');
  await write(e, '0x0100', 7, false);
  ok((await e.q(() => window.__mb.length)) === 3, 'david: anulowanie w oknie potwierdzenia nie wysyła zapisu');
  ok(e.errs.length === 0, 'A: brak błędów JS ' + JSON.stringify(e.errs));
  await e.ctx.close();

  // B. StephanJoubert/home_assistant_solarman
  e = await setup(b, ORIG);
  await read(e, '256', 1);
  mb = await e.q(() => window.__mb);
  ok(mb[0].service === 'read_holding_register' && JSON.stringify(mb[0].data) === JSON.stringify({ device: 'dev123', register: 256 }), 'oryginał: odczyt 1 rejestru → read_holding_register {device, register}: ' + JSON.stringify(mb[0]));
  ok(mb[0].ret === false || mb[0].ret === true, 'oryginał: wywołanie wykonane');
  await read(e, '256', 4);
  mb = await e.q(() => window.__mb);
  ok(mb[1].service === 'read_multiple_holding_registers' && JSON.stringify(mb[1].data) === JSON.stringify({ device: 'dev123', register: 256, count: 4 }), 'oryginał: odczyt 4 → read_multiple_holding_registers {device, register, count}');
  await write(e, '256', 65516);
  mb = await e.q(() => window.__mb);
  ok(mb[2].service === 'write_holding_register' && JSON.stringify(mb[2].data) === JSON.stringify({ device: 'dev123', register: 256, value: 65516 }), 'oryginał: zapis → write_holding_register {device, register, value}');
  await e.ctx.close();

  // C. brak usług / nieznane usługi
  e = await setup(b, {}); await read(e, '256', 1);
  ok(/nie zgłasza usług integracji Solarman/.test(await out(e)) && (await e.q(() => window.__mb.length)) === 0, 'brak usług solarman: czytelny komunikat, bez wywołania');
  await e.ctx.close();
  e = await setup(b, { cos_innego: { fields: { device: {} } }, inne: { fields: {} } }); await write(e, '256', 5);
  ok(/Nie znaleziono pasującej usługi Solarman\. Dostępne: cos_innego, inne/.test(await out(e)) && (await e.q(() => window.__mb.length)) === 0, 'nieznane usługi: lista dostępnych w komunikacie, bez wywołania');
  await e.ctx.close();
  e = await setup(b, { read_holding_registers: { fields: { dev: {}, adr: {} } } }); await read(e, '256', 1);
  ok(/nieoczekiwane pola \(dev, adr\)/.test(await out(e)), 'nieoczekiwane pola: komunikat');
  await e.ctx.close();

  // D. usługa bez odpowiedzi: ponowienie bez return_response
  e = await setup(b, { read_holding_registers: { fields: { device: {}, address: {}, count: {} } } }, { noResp: true }); await read(e, '256', 1);
  mb = await e.q(() => window.__mb);
  ok(mb.length === 2 && mb[0].ret === true && mb[1].ret === false, 'bez odpowiedzi: próba z odpowiedzią, potem ponowienie bez return_response: ' + JSON.stringify(mb.map((x) => x.ret)));
  ok(/nie zwróciła wartości w odpowiedzi/.test(await out(e)), 'bez odpowiedzi: informacja dla użytkownika');
  await e.ctx.close();

  // E. walidacja wejścia
  e = await setup(b, DAVID);
  await read(e, '70000', 1); ok(/0–65535/.test(await out(e)), 'rejestr 70000 odrzucony');
  await write(e, '256', -20, false); ok(/0–65535/.test(await out(e)) && (await e.q(() => window.__mb.length)) === 0, 'wartość −20 odrzucona (rejestr bez znaku), brak wywołania');
  await write(e, '256', 'abc', false); ok(/Podaj wartość do zapisu/.test(await out(e)), 'wartość nienumeryczna odrzucona');
  await write(e, '256', 70000, false); ok(/0–65535/.test(await out(e)) && (await e.q(() => window.__mb.length)) === 0, 'wartość 70000 odrzucona');
  ok(e.errs.length === 0, 'E: brak błędów JS ' + JSON.stringify(e.errs));
  await e.ctx.close();

  console.log('FAILS', fails); await b.close(); process.exit(fails ? 1 : 0);
})().catch((err) => { console.log('WYJĄTEK TESTU', err.message); process.exit(2); });
