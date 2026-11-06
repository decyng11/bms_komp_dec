const { chromium } = require('playwright'); const fs=require('fs');
(async()=>{
  const js=fs.readFileSync(require('path').resolve(__dirname, '../../custom_components/bms_komp_dec/frontend') + '/bms-panel.js','utf8');
  const b=await chromium.launch(); const errs=[];
  const p=await (await b.newContext({viewport:{width:760,height:300},deviceScaleFactor:2})).newPage();
  p.on('pageerror',e=>errs.push(e.message));
  await p.route('**/*',r=>/^(data|about):/.test(r.request().url())?r.continue():r.abort());
  await p.setContent('<html><body style="margin:0;background:#000"><div id="h" style="width:720px;margin:10px"></div></body></html>');
  await p.evaluate(()=>{window.Chart=class{constructor(){}destroy(){}};window.Chart._adapters={_date:class{formats(){return{}}}}});
  await p.addScriptTag({content:js});
  await p.evaluate(()=>{
    const S=(v,a)=>({state:String(v),attributes:a||{},last_updated:'x'});
    const el=document.createElement('bms-panel-card');el.setConfig({type:'custom:bms-panel-card'});document.getElementById('h').appendChild(el);
    el.hass={states:{'sensor.bms_reserve_soc':S(30,{price_buy:0.78,price_sell:0.25})},entities:{},language:'pl',callService:async()=>{},callWS:async()=>({})};
    window.__el=el;
  });
  await p.waitForTimeout(500);
  const t=await p.evaluate(()=>{const e=window.__el.shadowRoot.getElementById('priceBar');return e.style.display+'|'+e.innerText});
  console.log(t.replace(/\n/g,' '), 'ERR', JSON.stringify(errs));
  await p.locator('bms-panel-card >> #priceBar').screenshot({path:'shots/pricebar.png'});
  await b.close();
})();
