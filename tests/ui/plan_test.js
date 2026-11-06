const { chromium } = require('playwright'); const fs=require('fs');
const SC=require('path').join(__dirname, 'shots') + '/';
(async()=>{
  const js=fs.readFileSync(require('path').resolve(__dirname, '../../custom_components/bms_komp_dec/frontend') + '/bms-panel.js','utf8');
  const b=await chromium.launch(); const errs=[];
  for (const sc of ['forecast','noforecast']) {
    const ctx=await b.newContext({viewport:{width:760,height:600},deviceScaleFactor:2}); const p=await ctx.newPage();
    p.on('pageerror',e=>errs.push(e.message));
    await p.route('**/*',r=>/^(data|about):/.test(r.request().url())?r.continue():r.abort());
    await p.setContent('<html><body style="margin:0;background:#000"><div id="h" style="width:720px;margin:10px"></div></body></html>');
    await p.evaluate(()=>{window.Chart=class{constructor(){}destroy(){}};window.Chart._adapters={_date:class{formats(){return{}}}}});
    await p.addScriptTag({content:js});
    await p.evaluate((sc)=>{
      const S=(v,a)=>({state:String(v),attributes:a||{},last_updated:'x'+v});
      const now=new Date(); const h=now.getHours();
      const det=[];for(let i=0;i<24;i++){const d=new Date(now);d.setHours(i,0,0,0);det.push({period_start:d.toISOString(),pv_estimate:Math.max(0,4.2*Math.sin((i-6)/12*Math.PI))});}
      const f=det[h].pv_estimate;
      const states={'sensor.bms_soc':S(67),'sensor.bms_pv_power':S(sc==='forecast'?Math.round(f*0.84*1000)||3200:3200),'sensor.energy_battery_charge_today':S(4.1),
        'sensor.solcast_pv_forecast_forecast_today':S(8,sc==='forecast'?{detailedHourly:det}:{})};
      const el=document.createElement('bms-panel-card');el.setConfig({type:'custom:bms-panel-card'});document.getElementById('h').appendChild(el);
      el.hass={states,entities:{},language:'pl',callService:async()=>{},callWS:async()=>({})};
      el._renderPlan(); window.__el=el;
    },sc);
    const html=await p.evaluate(()=>{const e=window.__el.shadowRoot.getElementById('planBox');return e?e.innerText:'NO planBox'});
    console.log(sc,'->',html.replace(/\n/g,' | ').slice(0,300));
    const box=p.locator('bms-panel-card >> #planBox'); if(await box.count()) await box.screenshot({path:SC+`plan_${sc}.png`});
    await ctx.close();
  }
  console.log('ERR',JSON.stringify(errs)); await b.close();
})();
