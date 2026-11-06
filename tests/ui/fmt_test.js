const { chromium } = require('playwright'); const fs=require('fs');
(async()=>{
  const js=fs.readFileSync(require('path').resolve(__dirname, '../../custom_components/bms_komp_dec/frontend') + '/bms-panel.js','utf8');
  const b=await chromium.launch(); const p=await b.newPage(); const errs=[]; p.on('pageerror',e=>errs.push(e.message));
  await p.route('**/*',r=>r.request().url().startsWith('data:')||r.request().url().startsWith('about:')?r.continue():r.abort());
  await p.setContent('<html><body><div id="h"></div></body></html>');
  await p.evaluate(()=>{window.Chart=class{constructor(){}destroy(){}};window.Chart._adapters={_date:class{formats(){return{}}}}});
  await p.addScriptTag({content:js});
  const out=await p.evaluate(()=>{
    const el=document.createElement('bms-panel-card'); el.setConfig({type:'custom:bms-panel-card'});
    const real=Date.now; const fake=new Date(2026,10,1,21,21,0).getTime(); Date.now=()=>fake;
    const OD=Date; // _fmtAt używa new Date(Date.now()+..) oraz new Date() — podmieniamy konstruktor bez argumentów
    window.Date=class extends OD{constructor(...a){if(a.length===0)super(fake);else super(...a)} static now(){return fake}};
    const r={}; for(const h of [0.5,2,3,8.5,10,31.95,26,47,50]) r[h]=[el._fmtDur(h), el._fmtAt(h)];
    window.Date=OD; Date.now=real; return r;
  });
  console.log(JSON.stringify(out,null,1)); console.log('ERR',JSON.stringify(errs)); await b.close();
})();
