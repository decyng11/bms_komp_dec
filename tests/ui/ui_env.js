// Wspólne środowisko testów przeglądarkowych: prawdziwy origin http (jak w HA), serwowanie plików modułów z dysku.
const fs = require('fs'); const { chromium } = require('playwright');
const FR = require('path').resolve(__dirname, '../../custom_components/bms_komp_dec/frontend') + '/';
function loadFixture(){
const raw=fs.readFileSync(require('path').join(__dirname, 'fixtures', 'deye_entities.txt'),'utf8').split('\n');
const ents=[];
for(const l of raw){const p=l.split(' | ');if(p.length<4||!/^(number|select|switch|time|button)\./.test(p[0]))continue;
  const [eid,state,rng,name]=p; const o={eid,state,name:name.trim()};
  if(eid.startsWith('number.')){const m=rng.split('–');
    const mn=m.length===3?'-'+m[1]:m[0]; const mx=m[m.length-1]; o.min=parseFloat(mn);o.max=parseFloat(mx);o.step=/\./.test(mn+mx)?0.1:1;}
  ents.push(o);}

  return ents;
}

const readFile = (n) => fs.readFileSync(FR + n, 'utf8');
const CARD = (readFile('bms-panel.js').match(/const CARD_VERSION = '([^']+)'/) || [])[1] || '0.0.0';
function htmlPage(ver, mobile, extraHead, loadAs) {
  return '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' + (extraHead || '') +
    '<script>window.__charts=[];window.Chart=class{constructor(c,cfg){this.cfg=cfg;window.__charts.push(cfg)}destroy(){}};window.Chart._adapters={_date:class{formats(){return{}}}}</script>' +
    '</head><body style="margin:0;background:#000"><div id="h" style="width:' + (mobile ? 390 : 1060) + 'px;margin:0 auto"></div>' +
    (loadAs === 'import' ? '<script type="module">import("/bms_komp_dec/bms-panel.js?v=' + ver + '")</script>'
      : loadAs === 'module' ? '<script type="module" src="/bms_komp_dec/bms-panel.js?v=' + ver + '"></script>'
      : '<script src="/bms_komp_dec/bms-panel.js?v=' + ver + '"></script>') + '</body></html>';
}
// opts: {admin, mobile, ver, override:{ 'bms-diag.js': (route)=>..., ... }, preload:[files], noCore}
async function openCard(browser, opts = {}) {
  const ver = opts.ver || (CARD + '.1700000000');
  const ctx = await browser.newContext({ viewport: opts.mobile ? { width: 390, height: 844 } : { width: 1100, height: 900 }, deviceScaleFactor: +process.env.DSF || 1 });
  const p = await ctx.newPage();
  const errs = [], reqs = [];
  p.on('pageerror', e => errs.push(e.message));
  p.on('console', m => { if (m.type() === 'error') errs.push('console: ' + m.text()); });
  await p.route('**/*', async (r) => {
    const u = new URL(r.request().url());
    if (u.hostname !== 'bms.test') return /^(data|about):/.test(u.protocol) ? r.continue() : r.abort();
    reqs.push(u.pathname + u.search);
    if (u.pathname === '/') return r.fulfill({ contentType: 'text/html', body: htmlPage(ver, opts.mobile, opts.head, opts.loadAs) });
    const m = u.pathname.match(/^\/bms_komp_dec\/([\w.-]+\.js)$/);
    const name = m && m[1];
    if (name && opts.override && opts.override[name]) return opts.override[name](r);
    if (name && fs.existsSync(FR + name)) return r.fulfill({ contentType: 'application/javascript', body: readFile(name) });
    return r.fulfill({ status: 404, body: 'nie ma' });
  });
  if (opts.preload) await p.addInitScript(opts.preload.map(readFile).join('\n'));
  await p.goto('http://bms.test/');
  await p.waitForFunction(() => !!customElements.get('bms-panel-card'));
  const ents = loadFixture();
  await p.evaluate((a) => { window.__admin = a; }, opts.admin !== false);
  await p.evaluate((ents)=>{
    const S=(v,a)=>({state:String(v),attributes:a||{},last_updated:new Date().toISOString()});
    const states={};
    const sel={work_mode:['Selling First','Zero Export To Load','Zero Export To CT'],energy_pattern:['Battery First','Load First'],time_of_use:['Disabled','Week','Mon'],battery_control_mode:['Lithium','Voltage'],battery_operation_mode:['Capacity','Voltage']};
    ents.forEach(e=>{const key=e.eid.replace(/^[a-z_]+\.inverter_?/,'');const a={friendly_name:e.name};
      if(e.eid.startsWith('number.')){a.min=e.min;a.max=e.max;a.step=e.step;a.unit_of_measurement=/voltage/.test(e.eid)?'V':/current/.test(e.eid)?'A':/soc|start$|_off$|_on$/.test(e.eid)?'%':/power/.test(e.eid)?'W':'';}
      if(e.eid.startsWith('select.')){a.options=sel[key]||(/program_\d_charging/.test(e.eid)?['Disabled','Allow Grid','Allow Gen','Allow Grid & Gen']:[e.state]);}
      states[e.eid]=S(e.state,a);});
    const sens=(id,v,u,n)=>states['sensor.'+id]=S(v,{unit_of_measurement:u,friendly_name:n,state_class:'measurement'});
    sens('inverter_pv_power',3200,'W','Inverter PV Power');sens('inverter_load_power',1100,'W','Inverter Load Power');sens('inverter_grid_power',-800,'W','Inverter Grid Power');
    sens('inverter_battery_power',-1500,'W','Inverter Battery Power');sens('inverter_battery',67,'%','Inverter Battery');sens('inverter_battery_voltage',52.4,'V','Inverter Battery Voltage');
    sens('inverter_battery_current',-18,'A','Inverter Battery Current');sens('inverter_battery_temperature',23,'°C','Inverter Battery Temperature');
    sens('inverter_pv1_voltage',312,'V','Inverter PV1 Voltage');sens('inverter_pv1_current',5.1,'A','Inverter PV1 Current');sens('inverter_pv1_power',1700,'W','Inverter PV1 Power');
    sens('inverter_grid_voltage_l1',231,'V','Inverter Grid Voltage L1');sens('inverter_grid_frequency',50,'Hz','Inverter Grid Frequency');sens('inverter_dc_temperature',41,'°C','Inverter DC Temperature');
    sens('inverter_today_production',8.2,'kWh','Inverter Today Production');
    states['sensor.inverter_fault']=S('None',{friendly_name:'Inverter Fault'});states['sensor.inverter_alert']=S('F35',{friendly_name:'Inverter Alert'});
    window.__calls=[];window.__ws=[];window.__states=states;
    const mk=()=>({states:JSON.parse(JSON.stringify(window.__states)),entities:{},user:{name:'Admin',is_admin:window.__admin!==false},language:'pl',
      callService:async(d,s,data)=>{window.__calls.push([d,s,data]);const eid=data.entity_id;const st=window.__states[eid];
        setTimeout(()=>{ if(window.__noconfirm) return; if(d==='number')st.state=String(data.value);else if(d==='select')st.state=data.option;else if(d==='switch')st.state=s==='turn_on'?'on':'off';else if(d==='time')st.state=data.time;
          st.last_updated=new Date().toISOString(); window.__el.hass=mk();},300);},
      callWS:async(m)=>{window.__ws.push(m.type);
        if(m.type==='history/history_during_period'){const out={};const t1=Date.now(),t0=new Date(m.start_time).getTime();(m.entity_ids||[]).forEach(e=>{out[e]=[];for(let i=0;i<200;i++){const t=t0+(t1-t0)*i/200;out[e].push({s:String(50+30*Math.sin(i/12)),lu:t/1000});}});
          if(String(m.entity_ids).includes('inverter_alert')){out['sensor.inverter_alert']=[{s:'None',lu:t0/1000},{s:'F35',lu:(t1-3600e3)/1000}];}return out;}
        if(m.type==='recorder/statistics_during_period'){const out={};m.statistic_ids.forEach(e=>{out[e]=[];for(let i=0;i<100;i++)out[e].push({start:new Date(m.start_time).getTime()+i*3600e3,mean:10+i%7});});return out;}
        if(m.type==='call_service'&&window.__svc&&window.__svc[m.domain+'.'+m.service])return window.__svc[m.domain+'.'+m.service](m);
        if(m.type==='call_service'){return{response:{value:[1234]}}}
        if(m.type==='config/entity_registry/get')return{device_id:'dev123'};
        return{};}});
    window.__mk=mk;
    const el=document.createElement('bms-panel-card');el.setConfig({type:'custom:bms-panel-card'});document.getElementById('h').appendChild(el);el.hass=mk();window.__el=el;
  },ents);
  return { page: p, ctx, errs, reqs, q: (f, a) => p.evaluate(f, a) };
}
module.exports = { CARD, openCard, FR, readFile, htmlPage, loadFixture, chromium };
