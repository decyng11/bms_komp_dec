const { chromium } = require('playwright'); const fs=require('fs');
(async()=>{
  const js=fs.readFileSync(require('path').resolve(__dirname, '../../custom_components/bms_komp_dec/frontend') + '/bms-panel.js','utf8');
  const b=await chromium.launch(); const errs=[]; let fails=0;
  const ok=(c,m)=>{if(!c){fails++;console.log('FAIL',m)}else console.log('ok  ',m)};
  for (const sc of [{soc:22,name:'weekend',weekend:true},{soc:27,name:'blisko'},{soc:25,name:'na progu'},{soc:60,name:'daleko'},{soc:27,name:'brak progu',nofloor:true}]) {
    const p=await (await b.newContext({viewport:{width:420,height:900},deviceScaleFactor:2})).newPage();
    p.on('pageerror',e=>errs.push(e.message));
    await p.route('**/*',r=>/^(data|about):/.test(r.request().url())?r.continue():r.abort());
    await p.setContent(`<html><body style="margin:0;background:#000"><div id="h" style="width:400px;margin:10px"></div></body></html>`);
    await p.evaluate(()=>{window.Chart=class{constructor(){}destroy(){}};window.Chart._adapters={_date:class{formats(){return{}}}}});
    await p.addScriptTag({content:js});
    await p.evaluate((sc)=>{
      const S=(v,a)=>({state:String(v),attributes:a||{},last_updated:'x'});
      const now=new Date(); const st=new Date(now); st.setHours(13,0,0,0); const en=new Date(now); en.setHours(15,0,0,0);
      const at={price_buy:1.29,price_sell:0.3}; if(!sc.nofloor) Object.assign(at,{inverter_floor:25,usable_kwh:0.4,cheap_start:st.toISOString(),cheap_end:en.toISOString(),cheap_now:false});
      if(sc.weekend){ const s2=new Date(now); s2.setDate(s2.getDate()-1); s2.setHours(22,0,0,0); const e2=new Date(now); e2.setDate(e2.getDate()+(((8-e2.getDay())%7)||7)); e2.setHours(6,0,0,0); Object.assign(at,{cheap_start:s2.toISOString(),cheap_end:e2.toISOString(),cheap_now:true}); }
      const el=document.createElement('bms-panel-card');el.setConfig({type:'custom:bms-panel-card'});document.getElementById('h').appendChild(el);
      el.hass={states:{'sensor.bms_soc':S(sc.soc),'sensor.bms_pv_power':S(300),'sensor.bms_reserve_soc':S(30,at)},entities:{},language:'pl',callService:async()=>{},callWS:async()=>({})};window.__el=el;
    },sc);
    await p.waitForTimeout(500);
    await p.evaluate(()=>{__el._renderPlan&&__el._renderPlan();});
    const t=await p.evaluate(()=>{const e=__el.shadowRoot.getElementById('floorAlert');return e.style.display+'|'+e.className+'|'+e.textContent});
    const plan=await p.evaluate(()=>{const e=__el.shadowRoot.getElementById('planBox');return e?e.innerText.replace(/\n/g,' '):''});
    console.log(sc.name,'->',t.slice(0,170));
    if(sc.name==='weekend'){ ok(/Trwa tanie okno do (poniedziałku|jutra) 06:00/.test(t),'alert: koniec okna w kolejnej dobie ma nazwę dnia (nie samo „do 06:00”)'); ok(!/do 06:00/.test(t),'alert: brak gołego „do 06:00”'); }
    if(sc.name==='blisko'){ ok(/blisko progu odcięcia/.test(t)&&/Najbliższe tanie okno/.test(t),'alert: blisko progu + tanie okno'); ok(/próg odcięcia falownika 25%/.test(plan),'plan: znacznik progu w pasku baterii'); await p.locator('bms-panel-card >> #floorAlert').screenshot({path:'shots/floor_alert.png'}); }
    if(sc.name==='na progu'){ ok(/bad/.test(t)&&/bateria nie zasila domu/.test(t),'alert: na progu = czerwony'); }
    if(sc.name==='daleko'){ ok(/^none/.test(t),'alert ukryty gdy SOC daleko od progu'); }
    if(sc.name==='brak progu'){ ok(/^none/.test(t),'alert ukryty bez danych o progu'); ok(!/próg odcięcia/.test(plan),'plan: bez progu — bez znacznika'); }
    await p.close();
  }
  console.log('ERR',JSON.stringify(errs)); if(errs.length) fails++;
  await b.close(); console.log(fails?'FAILS '+fails:'ALL OK');
})();
