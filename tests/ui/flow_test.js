const { chromium } = require('playwright'); const fs=require('fs');
(async()=>{
  const js=fs.readFileSync(require('path').resolve(__dirname, '../../custom_components/bms_komp_dec/frontend') + '/bms-panel.js','utf8');
  const b=await chromium.launch(); const errs=[];
  for (const [name,w] of [['wide',760],['narrow',380]]) {
  const p=await (await b.newContext({viewport:{width:w,height:700},deviceScaleFactor:2})).newPage();
  p.on('pageerror',e=>errs.push(e.message));
  await p.route('**/*',r=>/^(data|about):/.test(r.request().url())?r.continue():r.abort());
  await p.setContent(`<html><body style="margin:0;background:#000"><div id="h" style="width:${w-40}px;margin:10px"></div></body></html>`);
  await p.evaluate(()=>{window.Chart=class{constructor(){}destroy(){}};window.Chart._adapters={_date:class{formats(){return{}}}}});
  await p.addScriptTag({content:js});
  await p.evaluate(()=>{
    const S=(v,a)=>({state:String(v),attributes:a||{},last_updated:'x'});
    const el=document.createElement('bms-panel-card');el.setConfig({type:'custom:bms-panel-card'});document.getElementById('h').appendChild(el);
    el.hass={states:{'sensor.bms_soc':S(71),'sensor.bms_pv_power':S(39),'sensor.bms_load_power':S(486),'sensor.bms_grid_power':S(10),'sensor.bms_battery_power':S(-403),
     'sensor.bms_energy_pv_today':S(12.4),'sensor.bms_energy_load_today':S(9.8),'sensor.bms_energy_grid_import_today':S(3.1),'sensor.bms_energy_grid_export_today':S(5.2),'sensor.bms_energy_battery_charge_today':S(4.1),'sensor.bms_energy_battery_discharge_today':S(3.6),
     'sensor.bms_reserve_soc':S(30,{price_buy:1.29,price_sell:0.305})},entities:{},language:'pl',callService:async()=>{},callWS:async()=>({})};
    window.__el=el;
  });
  await p.waitForTimeout(600);
  console.log(name, await p.evaluate(()=>{const e=window.__el.shadowRoot.getElementById('priceBar');return e.innerText.replace(/\n/g,' ')+' || '+[...window.__el.shadowRoot.querySelectorAll('.nf-d')].map(x=>x.textContent).join(' | ')}));
  await p.locator('bms-panel-card >> #nodesBox').screenshot({path:`shots/flow_${name}.png`});
  }
  console.log('ERR',JSON.stringify(errs)); await b.close();
})();
