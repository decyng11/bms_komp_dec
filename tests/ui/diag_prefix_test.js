const { chromium } = require('playwright'); const fs=require('fs');
const SC=require('path').join(__dirname, 'shots') + '/';
const js=fs.readFileSync(require('path').resolve(__dirname, '../../custom_components/bms_komp_dec/frontend') + '/bms-panel.js','utf8');
const jsDiag=fs.readFileSync(require('path').resolve(__dirname, '../../custom_components/bms_komp_dec/frontend') + '/bms-diag.js','utf8');
const raw=fs.readFileSync(require('path').join(__dirname, 'fixtures', 'deye_entities.txt'),'utf8').split('\n');
const ents=[];
for(const l of raw){const p=l.split(' | ');if(p.length<4||!/^(number|select|switch|time|button)\./.test(p[0]))continue;
  const [eid,state,rng,name]=p; const o={eid,state,name:name.trim()};
  if(eid.startsWith('number.')){const m=rng.split('–');
    const mn=m.length===3?'-'+m[1]:m[0]; const mx=m[m.length-1]; o.min=parseFloat(mn);o.max=parseFloat(mx);o.step=/\./.test(mn+mx)?0.1:1;}
  ents.push(o);}
console.log('fixture entities',ents.length);
let fails=0; const ok=(c,m)=>{if(!c){fails++;console.log('FAIL',m)}else console.log('ok  ',m)};
(async()=>{
 const b=await chromium.launch();
 for (const mobile of [false,true]) {
  const ctx=await b.newContext({viewport:mobile?{width:390,height:844}:{width:1100,height:900},deviceScaleFactor:1.5}); const p=await ctx.newPage();
  const errs=[]; p.on('pageerror',e=>errs.push(e.message)); p.on('console',m=>{if(m.type()==='error')errs.push('console: '+m.text())});
  await p.route('**/*',r=>/^(data|about):/.test(r.request().url())?r.continue():r.abort());
  await p.setContent('<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0;background:#000"><div id="h" style="width:'+(mobile?390:1060)+'px;margin:0 auto"></div></body></html>');
  await p.evaluate(()=>{window.__charts=[];window.Chart=class{constructor(c,cfg){this.cfg=cfg;window.__charts.push(cfg)}destroy(){}};window.Chart._adapters={_date:class{formats(){return{}}}}});
  await p.addScriptTag({content:jsDiag}); await p.addScriptTag({content:js});
  await p.evaluate((ents)=>{
    const S=(v,a)=>({state:String(v),attributes:a||{},last_updated:new Date().toISOString()});
    const states={};
    ents.forEach(e=>{});
    const sel={work_mode:['Selling First','Zero Export To Load','Zero Export To CT'],energy_pattern:['Battery First','Load First'],time_of_use:['Disabled','Week','Mon'],battery_control_mode:['Lithium','Voltage'],battery_operation_mode:['Capacity','Voltage']};
    ents.forEach(e=>{e.eid=e.eid;const key=e.eid.replace(/^[a-z_]+\.inverter_?/,'');const a={friendly_name:e.name};
      if(e.eid.startsWith('number.')){a.min=e.min;a.max=e.max;a.step=e.step;a.unit_of_measurement=/voltage/.test(e.eid)?'V':/current/.test(e.eid)?'A':/soc|start$|_off$|_on$/.test(e.eid)?'%':/power/.test(e.eid)?'W':'';}
      if(e.eid.startsWith('select.')){a.options=sel[key]||(/program_\d_charging/.test(e.eid)?['Disabled','Allow Grid','Allow Gen','Allow Grid & Gen']:[e.state]);}
      states[e.eid]=S(e.state,a);});
    const sens=(id,v,u,n)=>states['sensor.'+id]=S(v,{unit_of_measurement:u,friendly_name:n,state_class:'measurement'});
    sens('mojdeye_pv_power',3200,'W','Inverter PV Power');sens('mojdeye_load_power',1100,'W','Inverter Load Power');sens('mojdeye_grid_power',-800,'W','Inverter Grid Power');
    sens('mojdeye_battery_power',-1500,'W','Inverter Battery Power');sens('mojdeye_battery',67,'%','Inverter Battery');sens('mojdeye_battery_voltage',52.4,'V','Inverter Battery Voltage');
    sens('mojdeye_battery_current',-18,'A','Inverter Battery Current');sens('mojdeye_battery_temperature',23,'°C','Inverter Battery Temperature');
    sens('mojdeye_pv1_voltage',312,'V','Inverter PV1 Voltage');sens('mojdeye_pv1_current',5.1,'A','Inverter PV1 Current');sens('mojdeye_pv1_power',1700,'W','Inverter PV1 Power');
    sens('mojdeye_grid_voltage_l1',231,'V','Inverter Grid Voltage L1');sens('mojdeye_grid_frequency',50,'Hz','Inverter Grid Frequency');sens('mojdeye_dc_temperature',41,'°C','Inverter DC Temperature');
    sens('mojdeye_today_production',8.2,'kWh','Inverter Today Production');
    states['sensor.mojdeye_fault']=S('None',{friendly_name:'Inverter Fault'});states['sensor.mojdeye_alert']=S('F35',{friendly_name:'Inverter Alert'});
    const ren={};Object.keys(states).forEach(k=>{ren[k.replace('.inverter','.mojdeye')]=states[k];});Object.keys(states).forEach(k=>delete states[k]);Object.assign(states,ren);
    states['sensor.licznik_moc']=S(500,{unit_of_measurement:'W',friendly_name:'Licznik moc'});
    window.__reg={};Object.keys(states).forEach(k=>{ if(/\.mojdeye/.test(k)) window.__reg[k]={platform:'solarman',device_id:'d1'}; else if(k.startsWith('sensor.licznik')) window.__reg[k]={platform:'solarman',device_id:'d2'};});
    window.__calls=[];window.__ws=[];window.__states=states;
    const mk=()=>({states:JSON.parse(JSON.stringify(window.__states)),entities:window.__reg,user:{name:'Admin',is_admin:window.__admin!==false},language:'pl',
      callService:async(d,s,data)=>{window.__calls.push([d,s,data]);const eid=data.entity_id;const st=window.__states[eid];
        setTimeout(()=>{ if(window.__noconfirm) return; if(d==='number')st.state=String(data.value);else if(d==='select')st.state=data.option;else if(d==='switch')st.state=s==='turn_on'?'on':'off';else if(d==='time')st.state=data.time;
          st.last_updated=new Date().toISOString(); window.__el.hass=mk();},300);},
      callWS:async(m)=>{window.__ws.push(m.type);
        if(m.type==='history/history_during_period'){const out={};const t1=Date.now(),t0=new Date(m.start_time).getTime();(m.entity_ids||[]).forEach(e=>{out[e]=[];for(let i=0;i<200;i++){const t=t0+(t1-t0)*i/200;out[e].push({s:String(50+30*Math.sin(i/12)),lu:t/1000});}});
          (m.entity_ids||[]).filter(e=>/_alert$/.test(e)).forEach(e=>{out[e]=[{s:'None',lu:t0/1000},{s:'F35',lu:(t1-3600e3)/1000}];});return out;}
        if(m.type==='recorder/statistics_during_period'){const out={};m.statistic_ids.forEach(e=>{out[e]=[];for(let i=0;i<100;i++)out[e].push({start:new Date(m.start_time).getTime()+i*3600e3,mean:10+i%7});});return out;}
        if(m.type==='call_service'){return{response:{value:[1234]}}}
        if(m.type==='config/entity_registry/get')return{device_id:'dev123'};
        return{};}});
    window.__mk=mk;
    const el=document.createElement('bms-panel-card');el.setConfig({type:'custom:bms-panel-card'});document.getElementById('h').appendChild(el);el.hass=mk();window.__el=el;
  },ents);
  const tag=mobile?'m':'d';
  const q=(f,a)=>p.evaluate(f,a);
  // --- tab widoczny dla admina
  ok(await q(()=>getComputedStyle(__el.shadowRoot.getElementById('tabDiag')).display!=='none'),tag+' zakładka widoczna dla admina');
  // --- brak admina
  await q(()=>{__admin=false;__el.hass=__mk();});
  ok(await q(()=>getComputedStyle(__el.shadowRoot.getElementById('tabDiag')).display==='none'),tag+' zakładka ukryta dla nie-admina');
  await q(()=>{__admin=true;__el.hass=__mk();});
  await q(()=>__el.shadowRoot.getElementById('tabDiag').click());
  ok(await q(()=>!!__el.shadowRoot.getElementById('dgPw')),tag+' bramka hasła');
  await q(()=>{const e=__el.shadowRoot;e.getElementById('dgPw').value='zle';e.querySelector('[data-act=unlock]').click();});
  ok(await q(()=>/Nieprawidłowe/.test(__el.shadowRoot.getElementById('dgGateMsg').textContent)),tag+' złe hasło odrzucone');
  ok(await q(()=>!!__el.shadowRoot.getElementById('dgPw')),tag+' po złym haśle nadal blokada');
  await q(()=>{const e=__el.shadowRoot;e.getElementById('dgPw').value='slonce';e.querySelector('[data-act=unlock]').click();});
  ok(await q(()=>!!__el.shadowRoot.getElementById('dgBody')),tag+' hasło slonce odblokowuje');
  await p.screenshot({path:SC+`diag_${tag}_overview.png`,fullPage:true});
  const tiles=await q(()=>__el.shadowRoot.querySelectorAll('#dgLive .dg-tile').length); ok(tiles>=5,tag+' kafelki przeglądu: '+tiles);
  ok(await q(()=>/F35|Alarmy/.test(__el.shadowRoot.getElementById('dgLive').textContent)),tag+' alarm w przeglądzie');
  // --- konfiguracja
  await q(()=>__el.shadowRoot.querySelector('[data-sec=config]').click());
  const rows=await q(()=>__el.shadowRoot.querySelectorAll('#dgCfgList .dg-row').length);
  const expected=ents.filter(e=>!/_program_\d_/.test(e.eid)).length; ok(rows===expected,tag+` wiersze konfiguracji ${rows}/${expected}`);
  await p.screenshot({path:SC+`diag_${tag}_config.png`,fullPage:false});
  // filtr
  await q(()=>{const i=__el.shadowRoot.getElementById('dgCfgQ');i.value='shutdown';i.dispatchEvent(new Event('input',{bubbles:true}));});
  ok(await q(()=>[...__el.shadowRoot.querySelectorAll('#dgCfgList .dg-row')].filter(r=>r.style.display!=='none').length)===2,tag+' filtr "shutdown" -> 2 wiersze');
  await q(()=>{const i=__el.shadowRoot.getElementById('dgCfgQ');i.value='';i.dispatchEvent(new Event('input',{bubbles:true}));});
  // zapis poza zakresem
  const setIn=(eid,v)=>q(([eid,v])=>{const i=__el.shadowRoot.querySelector(`[data-eid="${eid}"]`);i.value=v;i.dispatchEvent(new Event('input',{bubbles:true}));return i.classList.contains('dirty')},[eid,v]);
  ok(await setIn('number.mojdeye_battery_shutdown_soc','150'),tag+' pole oznaczone jako zmienione');
  await q(()=>__el.shadowRoot.querySelector('[data-eid="number.mojdeye_battery_shutdown_soc"]').closest('[data-scope=row]').querySelector('[data-act=save-row]').click());
  await p.waitForTimeout(100);
  ok(await q(()=>!__el.shadowRoot.querySelector('.dg-modal')&&/Maks\. 100/.test(__el.shadowRoot.getElementById('dgToast').textContent)),tag+' wartość poza zakresem odrzucona');
  ok((await q(()=>__calls.length))===0,tag+' brak wywołania usługi dla złej wartości');
  // zapis poprawny
  await setIn('number.mojdeye_battery_shutdown_soc','25');
  await q(()=>__el.shadowRoot.querySelector('[data-eid="number.mojdeye_battery_shutdown_soc"]').closest('[data-scope=row]').querySelector('[data-act=save-row]').click());
  await p.waitForTimeout(100);
  ok(await q(()=>!!__el.shadowRoot.querySelector('.dg-modal .dg-redbox')),tag+' modal z ostrzeżeniem ryzyka');
  ok(await q(()=>[...__el.shadowRoot.querySelectorAll('.dg-modal button')].find(b=>b.dataset.id==='ok').disabled),tag+' przycisk zapisu zablokowany do zaznaczenia zgody');
  await p.screenshot({path:SC+`diag_${tag}_modal.png`});
  await q(()=>{const m=__el.shadowRoot.querySelector('.dg-modal');m.querySelector('#dgNeed').click();m.querySelector('[data-id=ok]').click();});
  await p.waitForTimeout(1500);
  const call=await q(()=>JSON.stringify(__calls[0])); ok(/"number","set_value".*"value":25/.test(call),tag+' number.set_value value=25: '+call);
  ok(await q(()=>/✅/.test(__el.shadowRoot.getElementById('dgToast').textContent)),tag+' potwierdzenie odczytem');
  ok(await q(()=>__el._dgLS().get('bms_diag_log')[0].ok===true),tag+' wpis w dzienniku');
  ok(await q(()=>__el._dgLS().get('bms_diag_auto').length===1),tag+' automatyczna kopia przed zmianą');
  // przełącznik
  await q(()=>__el.shadowRoot.querySelector('[data-act=toggle][data-eid="switch.mojdeye_battery_grid_charging"]').click());
  await p.waitForTimeout(100);
  await q(()=>{const m=__el.shadowRoot.querySelector('.dg-modal');m.querySelector('[data-id=ok]').click();});
  await p.waitForTimeout(1500);
  ok(await q(()=>__calls.some(c=>c[0]==='switch'&&c[1]==='turn_off')),tag+' switch.turn_off');
  // niedostępna encja
  ok(await q(()=>__el.shadowRoot.querySelector('[data-eid="select.mojdeye_cloud"]').disabled),tag+' niedostępna encja zablokowana');
  // --- strefy czasowe
  await q(()=>__el.shadowRoot.querySelector('[data-sec=tou]').click());
  ok(await q(()=>__el.shadowRoot.querySelectorAll('#dgTou input[type=time]').length===6),tag+' 6 pól czasu');
  ok(await q(()=>__el.shadowRoot.querySelectorAll('#dgTl .dg-tl > div:not(.now)').length>=6),tag+' oś doby');
  await q(()=>{const i=__el.shadowRoot.querySelector('[data-eid="time.mojdeye_program_3_time"]');i.value='00:10';i.dispatchEvent(new Event('input',{bubbles:true}));});
  ok(await q(()=>/Czasy powinny rosnąć/.test(__el.shadowRoot.getElementById('dgTouWarn').textContent)),tag+' ostrzeżenie o kolejności czasów');
  await p.screenshot({path:SC+`diag_${tag}_tou.png`,fullPage:true});
  await q(()=>{const i=__el.shadowRoot.querySelector('[data-eid="time.mojdeye_program_3_time"]');i.value='09:00';i.dispatchEvent(new Event('input',{bubbles:true}));
     const s=__el.shadowRoot.querySelector('[data-eid="number.mojdeye_program_2_soc"]');s.value='80';s.dispatchEvent(new Event('input',{bubbles:true}));});
  await q(()=>__el.shadowRoot.querySelector('[data-act=save-scope][data-scope=tou]').click());
  await p.waitForTimeout(100);
  ok(await q(()=>__el.shadowRoot.querySelectorAll('.dg-modal .dg-diff tr').length===2),tag+' diff TOU = 2 zmiany');
  await q(()=>{const m=__el.shadowRoot.querySelector('.dg-modal');m.querySelector('[data-id=ok]').click();});
  await p.waitForTimeout(2000);
  ok(await q(()=>__calls.some(c=>c[0]==='time'&&c[2].time==='09:00:00')),tag+' time.set_value 09:00:00');
  // --- wykresy
  await q(()=>__el.shadowRoot.querySelector('[data-sec=charts]').click()); await p.waitForTimeout(500);
  let cfg=await q(()=>JSON.stringify(__charts.slice(-1)[0].data.datasets.map(d=>[d.label,d.data.length,d.yAxisID])));
  console.log('   datasets:',cfg.slice(0,260));
  ok(JSON.parse(cfg).length>=3,tag+' wykres: serie domyślne');
  for(const r of ['1h','7d','30d','365d']){
    await q((r)=>__el.shadowRoot.querySelector(`[data-act=range][data-r="${r}"]`).click(),r); await p.waitForTimeout(400);
  }
  ok(await q(()=>__ws.includes('recorder/statistics_during_period')),tag+' długie zakresy używają statystyk');
  await q(()=>{const c=__el.shadowRoot.getElementById('dgCmp');c.checked=true;c.dispatchEvent(new Event('change',{bubbles:true}));}); await p.waitForTimeout(500);
  ok(await q(()=>__charts.slice(-1)[0].data.datasets.some(d=>/poprzedni okres/.test(d.label))),tag+' porównanie z poprzednim okresem');
  await q(()=>__el.shadowRoot.querySelector('[data-act=preset][data-p=battery]').click()); await p.waitForTimeout(500);
  ok(await q(()=>Object.keys(__charts.slice(-1)[0].options.scales).filter(k=>/^y/.test(k)).length>=3),tag+' osie według jednostek');
  ok(await q(()=>/min/.test(__el.shadowRoot.getElementById('dgChSum').textContent)),tag+' tabela min/śr/maks');
  await p.screenshot({path:SC+`diag_${tag}_charts.png`,fullPage:true});
  // --- alarmy
  await q(()=>__el.shadowRoot.querySelector('[data-sec=alarms]').click());
  ok(await q(()=>/F35: Brak sieci AC/.test(__el.shadowRoot.getElementById('dgAlLive').textContent)),tag+' opis kodu F35');
  await q(()=>__el.shadowRoot.querySelector('[data-act=alarm-hist]').click()); await p.waitForTimeout(400);
  ok(await q(()=>/F35/.test(__el.shadowRoot.getElementById('dgAlHist').textContent)),tag+' historia alarmów');
  // --- kopie i profile
  await q(()=>__el.shadowRoot.querySelector('[data-sec=backup]').click());
  await q(()=>{__el.shadowRoot.getElementById('dgProfName').value='zima';__el.shadowRoot.querySelector('[data-act=profile-save]').click();});
  ok(await q(()=>!!__el._dgLS().get('bms_diag_profiles').zima),tag+' profil zapisany');
  const cnt=await q(()=>Object.keys(__el._dgLS().get('bms_diag_profiles').zima.values).length); ok(cnt>80,tag+' profil zawiera '+cnt+' parametrów');
  await q(()=>{const i=__el.shadowRoot.querySelector('[data-act=profile-load][data-name=zima]');});
  // zmień wartość i wczytaj profil -> diff
  await q(()=>{__states['number.mojdeye_battery_float'].state='54';__el.hass=__mk();});
  await q(()=>__el.shadowRoot.querySelector('[data-act=profile-load][data-name=zima]').click()); await p.waitForTimeout(150);
  ok(await q(()=>__el.shadowRoot.querySelectorAll('.dg-modal .dg-diff tr').length===1),tag+' wczytanie profilu pokazuje 1 różnicę');
  await q(()=>__el.shadowRoot.querySelector('.dg-modal [data-id=cancel]').click());
  // --- dziennik
  await q(()=>__el.shadowRoot.querySelector('[data-sec=log]').click());
  ok(await q(()=>__el.shadowRoot.querySelectorAll('#dgBody tbody tr').length>=3),tag+' dziennik ma wpisy');
  await p.screenshot({path:SC+`diag_${tag}_log.png`,fullPage:true});
  // --- zaawansowane
  await q(()=>__el.shadowRoot.querySelector('[data-sec=adv]').click());
  await q(()=>{__el._hass.services={solarman:{read_holding_registers:{fields:{device:{},address:{},count:{}},response:{optional:true}}}};__el.shadowRoot.getElementById('dgMbReg').value='0x0100';__el.shadowRoot.querySelector('[data-act=mb-read]').click();}); await p.waitForTimeout(400);
  ok(await q(()=>/1234/.test(__el.shadowRoot.getElementById('dgMbOut').textContent)),tag+' odczyt rejestru');
  ok(await q(()=>/wykryty z integracji Solarman/.test(__el.shadowRoot.getElementById('dgBody').textContent)&&/mojdeye/.test(__el.shadowRoot.getElementById('dgBody').textContent)&&/licznik/.test(__el.shadowRoot.getElementById('dgBody').textContent)),tag+' prefiks mojdeye wykryty z rejestru, 2 urządzenia');
  ok(await q(()=>__el._dgRisk('jakis_nieznany_parametr')===2&&__el._dgRisk('program_2_soc')===1&&__el._dgRisk('battery_float')===2),tag+' ryzyko: nieznany=2, program=1');
  ok(await q(()=>__el._dgGuessGroup('max_charge_current')==='battery'&&__el._dgGuessGroup('export_limit')==='grid'),tag+' grupowanie po słowach kluczowych');
  // --- blokada
  await q(()=>__el.shadowRoot.querySelector('[data-act=lock]').click());
  ok(await q(()=>!!__el.shadowRoot.getElementById('dgPw')),tag+' ręczna blokada');
  console.log(tag,'BŁĘDY JS:',JSON.stringify(errs));
  if(errs.length) fails++;
  await ctx.close();
 }
 console.log('FAILS',fails); await b.close();
})();
