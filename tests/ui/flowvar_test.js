const { chromium } = require('playwright'); const fs=require('fs');
(async()=>{
  const js=fs.readFileSync(require('path').resolve(__dirname, '../../custom_components/bms_komp_dec/frontend') + '/bms-panel.js','utf8');
  const b=await chromium.launch(); const errs=[];
  for (const V of ['0','A','B','C']) {
    const p=await (await b.newContext({viewport:{width:390,height:700},deviceScaleFactor:2})).newPage();
    p.on('pageerror',e=>errs.push(e.message));
    await p.route('**/*',r=>/^(data|about):/.test(r.request().url())?r.continue():r.abort());
    await p.setContent(`<html><body style="margin:0;background:#000"><div id="h" style="width:370px;margin:10px"></div></body></html>`);
    await p.evaluate(()=>{window.Chart=class{constructor(){}destroy(){}};window.Chart._adapters={_date:class{formats(){return{}}}}});
    await p.addScriptTag({content:js});
    await p.evaluate((V)=>{
      const S=(v,a)=>({state:String(v),attributes:a||{},last_updated:'x'});
      const el=document.createElement('bms-panel-card');el.setConfig({type:'custom:bms-panel-card'});document.getElementById('h').appendChild(el);
      el._flowVariant=V;
      el.hass={states:{'sensor.bms_soc':S(87),'sensor.bms_pv_power':S(855),'sensor.bms_load_power':S(196),'sensor.bms_grid_power':S(3160),'sensor.bms_battery_power':S(3730),
       'sensor.bms_energy_pv_today':S(5.0),'sensor.bms_energy_load_today':S(5.0),'sensor.bms_energy_grid_import_today':S(7.4),'sensor.bms_energy_grid_export_today':S(0.0),'sensor.bms_energy_battery_charge_today':S(9.8),'sensor.bms_energy_battery_discharge_today':S(3.3)},entities:{},language:'pl',callService:async()=>{},callWS:async()=>({})};
      el.setAttribute('data-theme','dark'); window.__el=el;
    },V);
    await p.waitForTimeout(600);
    await p.evaluate(()=>{__el._lastFlowKey=null;__el._drawPowerflow();});
    await p.locator('bms-panel-card >> #nodesBox').screenshot({path:`shots/fv_${V}.png`});
  }
  console.log('ERR',JSON.stringify(errs)); await b.close();
})();
