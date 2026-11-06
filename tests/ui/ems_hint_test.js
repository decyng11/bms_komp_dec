const { chromium } = require('playwright'); const fs=require('fs');
const SC=require('path').join(__dirname, 'shots') + '/';
(async()=>{
  const js=fs.readFileSync(require('path').resolve(__dirname, '../../custom_components/bms_komp_dec/frontend') + '/bms-panel.js','utf8');
  const b=await chromium.launch(); const p=await b.newPage({viewport:{width:520,height:900}}); const errs=[];
  p.on('pageerror',e=>errs.push(e.message));
  await p.route('**/*',r=>r.request().url().startsWith('data:')||r.request().url().startsWith('about:')?r.continue():r.abort());
  await p.setContent('<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0;background:#111"><div id="host" style="width:500px;margin:10px"></div></body></html>');
  await p.evaluate(()=>{window.Chart=class{constructor(){}destroy(){}};window.Chart._adapters={_date:class{formats(){return{}}}}});
  await p.addScriptTag({content:js});
  const out=await p.evaluate(async()=>{
    const S=(s,a={})=>({state:String(s),attributes:a,last_updated:'x'+s});
    const states={'sensor.bms_soc':S(75),'time.bms_bateria_sprzedaz_start':S('17:15:00'),'time.bms_bateria_sprzedaz_stop':S('17:16:00'),'number.bms_min_soc_for_sell':S(50),'number.bms_grid_import_sell_block_w':S(2000)};
    const hass={states,entities:{},language:'pl',callService:async()=>{},callWS:async()=>({})};
    const el=document.createElement('bms-panel-card');el.setConfig({type:'custom:bms-panel-card'});document.getElementById('host').appendChild(el);el.hass=hass;
    const tab=[...el.shadowRoot.querySelectorAll('.tab')].find(t=>t.dataset.tab==='ems'||/EMS/.test(t.textContent));tab&&tab.click();el.hass=Object.assign({},hass);
    await new Promise(r=>setTimeout(r,200));
    const g=id=>{const e=el.shadowRoot.getElementById(id);return e?{t:e.textContent,c:e.className}:null};
    window.__el=el;
    return {ok1:g('eid-bateria_sprzedaz_start'),ok2:g('eid-min_soc_for_sell'),ok3:g('eid-grid_import_sell_block_w'),missing:g('eid-start_grid_charge')};
  });
  console.log(JSON.stringify(out,null,1));
  const row=p.locator('bms-panel-card >> #eid-bateria_sprzedaz_start'); await row.scrollIntoViewIfNeeded();
  await p.screenshot({path:SC+'ems_hints.png'}); console.log('ERR',JSON.stringify(errs)); await b.close();
})();
