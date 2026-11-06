const { chromium } = require('playwright'); const fs=require('fs');
(async()=>{
  const js=fs.readFileSync(require('path').resolve(__dirname, '../../custom_components/bms_komp_dec/frontend') + '/bms-panel.js','utf8');
  const b=await chromium.launch(); const errs=[]; let fails=0;
  const ok=(c,m)=>{if(!c){fails++;console.log('FAIL',m)}else console.log('ok  ',m)};
  const mk=async(attrs,extra)=>{
    const p=await (await b.newContext({viewport:{width:900,height:900}})).newPage();
    p.on('pageerror',e=>errs.push(e.message));
    await p.route('**/*',r=>/^(data|about):/.test(r.request().url())?r.continue():r.abort());
    await p.setContent(`<html><body style="margin:0;background:#000"><div id="h" style="width:800px;margin:10px"></div></body></html>`);
    await p.evaluate(()=>{window.Chart=class{constructor(){}destroy(){}};window.Chart._adapters={_date:class{formats(){return{}}}}});
    await p.addScriptTag({content:js});
    await p.evaluate(([attrs,extra])=>{
      const S=(v,a)=>({state:String(v),attributes:a||{},last_updated:'x'});
      window.__calls=[];
      const el=document.createElement('bms-panel-card');el.setConfig({type:'custom:bms-panel-card'});document.getElementById('h').appendChild(el);
      const states={'sensor.bms_soc':S(60),'sensor.bms_pv_power':S(500),'sensor.bms_load_power':S(700),'sensor.bms_grid_power':S(0),'sensor.bms_battery_power':S(3000),
        'sensor.bms_reserve_soc':S(30,attrs)};
      for(const [k,v] of Object.entries(extra||{})) states[k]=S(v[0],v[1]);
      el.hass={states,entities:{},language:'pl',callService:async(d,s,data)=>{window.__calls.push([d,s,data]);},callWS:async()=>({})};window.__el=el;
    },[attrs,extra]);
    await p.waitForTimeout(500);
    return p;
  };
  const nodes=async p=>{await p.evaluate(()=>{__el._lastFlowKey=null;__el._drawPowerflow();});return p.evaluate(()=>__el.shadowRoot.getElementById('nodesBox').textContent.replace(/\s+/g,' '));};

  // znak baterii z backendu
  const charging=t=>/ładowanie/.test(t)&&!/rozładowanie/.test(t), discharging=t=>/rozładowanie/.test(t);
  let p=await mk({battery_charge_sign:-1}); let t=await nodes(p);
  ok(discharging(t),'znak −1 (Deye: ujemna = ładowanie): +3000 W => rozładowanie'); await p.close();
  p=await mk({battery_charge_sign:1}); t=await nodes(p);
  ok(charging(t),'znak +1 (dodatnia = ładowanie): +3000 W => ładowanie'); await p.close();
  p=await mk({}); t=await nodes(p);
  ok(discharging(t),'brak atrybutu => domyślnie jak dotąd (Deye: +3000 W = rozładowanie)'); await p.close();
  p=await mk({battery_charge_sign:1}); await nodes(p);
  await p.evaluate(()=>{const h=__el._hass; h.states['sensor.bms_reserve_soc'].attributes={battery_charge_sign:-1}; __el.hass=h;});
  t=await nodes(p); ok(discharging(t),'zmiana atrybutu w locie przełącza znak'); await p.close();

  // taryfa w tekstach
  p=await mk({tariff_peaks:'7-13,16-21',tariff_night:'21-7'});
  let h=await p.evaluate(()=>__el._sugRulesHtml());
  ok(/7–13 i 16–21/.test(h)&&/21:00–07:00/.test(h)&&!/G12w/.test(h),'reguły: okna taryfy z backendu'); ok(/szczyt 7–21/.test(h),'reguły: szczyt dzienny 7–21'); await p.close();
  p=await mk({}); h=await p.evaluate(()=>__el._sugRulesHtml());
  ok(/6–13 i 15–22/.test(h)&&/22:00–06:00/.test(h),'reguły: domyślnie G12w jak dotąd'); await p.close();
  p=await mk({tariff_peaks:'brak',tariff_night:null}); h=await p.evaluate(()=>__el._sugRulesHtml());
  ok(/brak \(taryfa jednostrefowa\)/.test(h),'reguły: taryfa jednostrefowa'); await p.close();

  // encje sterujące z backendu
  p=await mk({ctl_charge_current:'number.deye_battery_max_charging_current',ctl_tou:'select.deye_time_of_use',inverter_prefix:'deye'},
     {'number.deye_battery_max_charging_current':[0,{}],'select.deye_time_of_use':['Disabled',{}]});
  ok(await p.evaluate(()=>__el._isPvBlocked()),'PV zablokowane wg encji z backendu (prąd 0)');
  ok(await p.evaluate(()=>__el._isGridChargingOn()),'ładowanie z sieci wg encji z backendu (TOU Disabled)');
  ok(await p.evaluate(()=>__el._invPrefix()==='deye'&&__el._inv('sensor','pv1_power')==='sensor.deye_pv1_power'),'prefiks falownika z backendu');
  await p.evaluate(()=>{__el._renderShell&&0; const b=__el.shadowRoot.getElementById('btn-toggle-blokada-pv'); b&&b.click();});
  await p.waitForTimeout(200);
  let c=await p.evaluate(()=>window.__calls);
  ok(c.some(x=>x[0]==='button'&&x[1]==='press'&&x[2].entity_id==='button.bms_odblokuj_ladowanie'),'przełącznik blokady PV: przycisk odblokuj (bez 170 A w karcie)'); 
  await p.evaluate(()=>{window.__calls.length=0;const b=__el.shadowRoot.getElementById('btn-toggle-ladowanie-siec'); b&&b.click();});
  await p.waitForTimeout(200); c=await p.evaluate(()=>window.__calls);
  ok(c.some(x=>x[0]==='button'&&x[2].entity_id==='button.bms_wylacz_ladowanie_siec'),'przełącznik ładowania z sieci: przycisk wyłącz'); await p.close();
  // bez atrybutów: stare nazwy
  p=await mk({}, {'number.inverter_battery_max_charging_current':[0,{}],'select.inverter_time_of_use':['Week',{}]});
  ok(await p.evaluate(()=>__el._isPvBlocked()&&!__el._isGridChargingOn()),'bez atrybutów: nazwy domyślne (zgodność wsteczna)'); await p.close();

  // etykieta mocy sprzedaży
  p=await mk({sell_power_w:5000}); await p.evaluate(()=>__el._render());
  await p.waitForTimeout(200);
  const lab=await p.evaluate(()=>{const e=__el.shadowRoot.querySelector('#btn-script-6000 .label');return e&&e.textContent});
  ok(lab==='Sprzedaż 5000W','przycisk sprzedaży pokazuje moc z ustawień: '+lab); await p.close();
  p=await mk({}); await p.evaluate(()=>__el._render());
  const lab2=await p.evaluate(()=>{const e=__el.shadowRoot.querySelector('#btn-script-6000 .label');return e&&e.textContent});
  ok(lab2==='Sprzedaż 6000W','bez atrybutu: Sprzedaż 6000W jak dotąd'); await p.close();

  console.log('ERR',JSON.stringify(errs)); if(errs.length) fails++;
  await b.close(); console.log(fails?'FAILS '+fails:'ALL OK');
})();
