const { chromium } = require('playwright'); const fs=require('fs');
const SC=require('path').join(__dirname, 'shots') + '/';
(async()=>{
  const js=fs.readFileSync(require('path').resolve(__dirname, '../../custom_components/bms_komp_dec/frontend') + '/bms-panel.js','utf8');
  const b=await chromium.launch(); const errs=[];
  for (const mode of ['dark','light']) {
    const ctx=await b.newContext({viewport:{width:760,height:600},deviceScaleFactor:2,colorScheme:mode}); const p=await ctx.newPage();
    p.on('pageerror',e=>errs.push(e.message));
    await p.route('**/*',r=>/^(data|about):/.test(r.request().url())?r.continue():r.abort());
    await p.setContent('<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0;background:'+(mode==='dark'?'#000':'#f2f2f7')+'"><div id="h" style="width:720px;margin:10px"></div></body></html>');
    await p.evaluate(()=>{window.Chart=class{constructor(){}destroy(){}};window.Chart._adapters={_date:class{formats(){return{}}}}});
    await p.addScriptTag({content:js});
    const out=await p.evaluate(async(mode)=>{
      const S=(v)=>({state:String(v),attributes:{},last_updated:'x'+v});
      const states={'sensor.bms_soc':S(50),'sensor.solcast_pv_forecast_forecast_today':S(8),'sensor.solcast_pv_forecast_forecast_tomorrow':S(6.1),'sensor.solcast_pv_forecast_forecast_day_3':S(10.4),'sensor.solcast_pv_forecast_forecast_day_4':S(12)};
      const hass={states,entities:{},language:'pl',callService:async()=>{},callWS:async()=>({})};
      const el=document.createElement('bms-panel-card');el.setConfig({type:'custom:bms-panel-card'});document.getElementById('h').appendChild(el);el.hass=hass;
      el._setTheme(mode,false);
      const conds=['sunny','partlycloudy','cloudy','rainy','pouring','snowy','lightning','lightning-rainy','fog','windy','snowy-rainy','hail','clear-night','exceptional'];
      const base=new Date();
      el._weatherError=null;
      el._weatherForecast=conds.slice(0,7).map((c,i)=>({datetime:new Date(base.getTime()+i*86400000).toISOString(),condition:c,temperature:9+i,templow:3+i}));
      el._lastWeatherKey=null;el._renderWeather();
      const c1=el.shadowRoot.getElementById('weatherContainer').innerHTML;
      // druga porcja warunków do osobnego zrzutu
      el._weatherForecast=conds.slice(7,14).map((c,i)=>({datetime:new Date(base.getTime()+i*86400000).toISOString(),condition:c,temperature:2+i,templow:-1+i}));
      el._lastWeatherKey=null;
      window.__el=el;
      return {svgCount:(c1.match(/class="wx"/g)||[]).length, kwh:(c1.match(/kWh/g)||[]).length, emoji:(c1.match(/🌡/g)||[]).length};
    },mode);
    console.log(mode,JSON.stringify(out));
    const box=p.locator('bms-panel-card >> #weatherContainer');
    await box.screenshot({path:SC+`wx_${mode}_1.png`});
    await p.evaluate(()=>{window.__el._renderWeather();});
    await box.screenshot({path:SC+`wx_${mode}_2.png`});
    const anim=await p.evaluate(()=>{const e=window.__el.shadowRoot.querySelector('.wx .a-spin, .wx .a-drift, .wx .a-float, .wx .a-twinkle');return e?getComputedStyle(e).animationName:null});
    console.log(' animacja:',anim);
    await ctx.close();
  }
  // reduced motion
  const ctx=await b.newContext({reducedMotion:'reduce'});const p=await ctx.newPage();
  await p.route('**/*',r=>/^(data|about):/.test(r.request().url())?r.continue():r.abort());
  await p.setContent('<html><body><div id="h"></div></body></html>');
  await p.evaluate(()=>{window.Chart=class{};window.Chart._adapters={_date:class{formats(){return{}}}}});
  await p.addScriptTag({content:js});
  const rm=await p.evaluate(()=>{const el=document.createElement('bms-panel-card');el.setConfig({type:'custom:bms-panel-card'});document.getElementById('h').appendChild(el);
    el.hass={states:{},entities:{},language:'pl',callService:async()=>{},callWS:async()=>({})};
    el._weatherError=null;el._weatherForecast=[{datetime:new Date().toISOString(),condition:'sunny',temperature:5,templow:1}];el._lastWeatherKey=null;el._renderWeather();
    const e=el.shadowRoot.querySelector('.wx .a-spin');return getComputedStyle(e).animationName;});
  console.log('reduced motion ->',rm,'ERR',JSON.stringify(errs)); await b.close();
})();
