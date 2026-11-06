const { chromium } = require('playwright'); const fs=require('fs');
const js=fs.readFileSync(require('path').resolve(__dirname, '../../custom_components/bms_komp_dec/frontend') + '/bms-panel.js','utf8');
const CHART="window.__order=(window.__order||[]).concat(['chart']);window.Chart=class{};window.Chart._adapters={_date:class{formats(){throw new Error('base')}}};";
const ADAPT="window.__order=(window.__order||[]).concat(['adapter']);if(!window.Chart)throw new Error('adapter before chart');window.Chart._adapters._date=class{formats(){return {}}};";
async function run(name, handler){
  const b=await chromium.launch(); const p=await b.newPage(); const errs=[]; const hits=[];
  p.on('pageerror',e=>errs.push(e.message.slice(0,60)));
  await p.route('**/*', async r=>{ const u=r.request().url(); hits.push(u.replace('http://ha.local','').replace('https://cdn.jsdelivr.net/npm/','CDN:'));
    if(u==='http://ha.local/') return r.fulfill({status:200,contentType:'text/html',body:'<html><body></body></html>'});
    const h=handler(u); if(h) return r.fulfill(h); return r.abort(); });
  await p.goto('http://ha.local/'); await p.addScriptTag({content:js}); await p.waitForTimeout(800);
  const r=await p.evaluate(()=>{let ok=false;try{new window.Chart._adapters._date({}).formats();ok=true}catch(e){}; return {ok, order:window.__order};});
  console.log(name, JSON.stringify(r), 'requests:', JSON.stringify(hits.slice(1)), 'errs:', JSON.stringify(errs)); await b.close();
}
const V='http://ha.local/bms_komp_dec/vendor/';
(async()=>{
  await run('A lokalne',u=>u===V+'chart.umd.min.js'?{status:200,contentType:'application/javascript',body:CHART}:u===V+'chartjs-adapter-date-fns.bundle.min.js'?{status:200,contentType:'application/javascript',body:ADAPT}:null);
  await run('B brak lokalnych -> CDN',u=>u.startsWith(V)?{status:404,body:'nf'}:u.includes('chart.umd')?{status:200,contentType:'application/javascript',body:CHART}:u.includes('adapter-date-fns')?{status:200,contentType:'application/javascript',body:ADAPT}:null);
  await run('C lokalny zwraca HTML -> CDN',u=>u.startsWith(V)?{status:200,contentType:'text/html',body:'<html>index</html>'}:u.includes('chart.umd')?{status:200,contentType:'application/javascript',body:CHART}:u.includes('adapter-date-fns')?{status:200,contentType:'application/javascript',body:ADAPT}:null);
  await run('D adapter lokalny wolniejszy niz chart',u=>u===V+'chart.umd.min.js'?{status:200,contentType:'application/javascript',body:CHART}:u===V+'chartjs-adapter-date-fns.bundle.min.js'?new Promise(()=>{}):null);
})();
