const { chromium } = require('playwright'); const fs=require('fs');
(async()=>{
  const js=fs.readFileSync(require('path').resolve(__dirname, '../../custom_components/bms_komp_dec/frontend') + '/bms-panel.js','utf8');
  const b=await chromium.launch(); const errs=[];
  for (const w of [390,900]) {
    const p=await (await b.newContext({viewport:{width:w,height:700}})).newPage();
    p.on('pageerror',e=>errs.push(e.message));
    await p.route('**/*',r=>/^(data|about):/.test(r.request().url())?r.continue():r.abort());
    await p.setContent(`<html><body style="margin:0;background:#000"><div id="h" style="width:${w-20}px;margin:10px"></div></body></html>`);
    await p.evaluate(()=>{window.Chart=class{constructor(){}destroy(){}};window.Chart._adapters={_date:class{formats(){return{}}}}});
    await p.addScriptTag({content:js});
    await p.evaluate(()=>{const S=(v)=>({state:String(v),attributes:{},last_updated:'x'});
      const el=document.createElement('bms-panel-card');el.setConfig({type:'custom:bms-panel-card'});document.getElementById('h').appendChild(el);
      el.hass={states:{'sensor.bms_soc':S(87),'sensor.bms_pv_power':S(855)},entities:{},language:'pl',callService:async()=>{},callWS:async()=>({})};window.__el=el;});
    await p.waitForTimeout(600);
    console.log(w, await p.evaluate(()=>__el.shadowRoot.querySelector('.nf-svg').getAttribute('viewBox')));
  }
  console.log('ERR',JSON.stringify(errs)); await b.close();
})();
