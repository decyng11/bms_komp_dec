const { chromium } = require('playwright'); const fs=require('fs');
const js=fs.readFileSync(require('path').resolve(__dirname, '../../custom_components/bms_komp_dec/frontend') + '/bms-panel.js','utf8');
(async()=>{
 const b=await chromium.launch(); const errs=[];
 const ctx=await b.newContext({viewport:{width:900,height:700},deviceScaleFactor:2}); const p=await ctx.newPage();
 p.on('pageerror',e=>errs.push(e.message));
 await p.route('**/*',r=>/^(data|about):/.test(r.request().url())?r.continue():r.abort());
 await p.setContent('<html><body style="margin:0;background:#000"><div id="h" style="width:860px;margin:10px"></div></body></html>');
 await p.evaluate(()=>{window.Chart=class{constructor(){}destroy(){}};window.Chart._adapters={_date:class{formats(){return{}}}}});
 await p.addScriptTag({content:js});
 for (const [name,days] of [['evening',[{date:'2026-10-31',label:'Wczoraj',actual:5.2,forecast:10.6},{date:'2026-11-01',label:'Dziś',actual:5.0,forecast:9.6,nowcast:5.9,forecast_source:'issued'},{date:'2026-11-02',label:'Jutro',actual:null,forecast:10.2}]],
   ['night',[{date:'2026-11-01',label:'Wczoraj',actual:5.3,forecast:9.6},{date:'2026-11-02',label:'Dziś',actual:0.1,forecast:10.3,nowcast:10.3},{date:'2026-11-03',label:'Jutro',actual:null,forecast:9.3}]]]) {
  await p.evaluate(([days])=>{
   document.getElementById('h').innerHTML='';
   const el=document.createElement('bms-panel-card');el.setConfig({type:'custom:bms-panel-card'});document.getElementById('h').appendChild(el);
   el.hass={states:{'sensor.bms_load_forecast':{state:'9',attributes:{days,confidence_interval:{low:7.8,high:12.6,sigma:1.6},mape_14d:69,history_days:42,profile_days:17,history_14d:[{date:'2026-11-01',weekday:6,holiday:'Wszystkich Świętych',actual:5.3,issued:9.6,model:9.6,temp:7},{date:'2026-10-31',weekday:5,holiday:null,actual:5.2,issued:10.6,model:10.6,temp:8},{date:'2026-10-30',weekday:4,holiday:null,actual:9.8,issued:10.1,model:10.1,temp:9},{date:'2026-10-29',weekday:3,holiday:null,actual:11.4,issued:null,model:10.0,temp:10},{date:'2026-10-28',weekday:2,holiday:null,actual:8.0,issued:10.2,model:10.2,temp:11}]},last_updated:'x'}},entities:{},user:{is_admin:true},language:'pl',callService:async()=>{},callWS:async()=>({})};
   el._lastLoadConsKey=null; el.shadowRoot.querySelector('[data-tab=charts]').click(); window.__el=el;
  },[days]);
  await p.waitForTimeout(500);
  const box=p.locator('bms-panel-card >> #loadHistTable'); await box.screenshot({path:`shots/lh_${name}.png`}); console.log(await box.innerText());
 }
 console.log('ERR',JSON.stringify(errs)); await b.close();
})();
