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
 for (const mobile of [false]) {
  const ctx=await b.newContext({viewport:mobile?{width:390,height:844}:{width:1100,height:900},deviceScaleFactor:1.5}); const p=await ctx.newPage();
  const errs=[]; p.on('pageerror',e=>errs.push(e.message)); p.on('console',m=>{if(m.type()==='error')errs.push('console: '+m.text())});
  await p.route('**/*',r=>/^(data|about):/.test(r.request().url())?r.continue():r.abort());
  await p.setContent('<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0;background:#000"><div id="h" style="width:'+(mobile?390:1060)+'px;margin:0 auto"></div></body></html>');
  await p.evaluate(()=>{window.__charts=[];window.Chart=class{constructor(c,cfg){this.cfg=cfg;window.__charts.push(cfg)}destroy(){}};window.Chart._adapters={_date:class{formats(){return{}}}}});
  await p.addScriptTag({content:jsDiag}); await p.addScriptTag({content:js});
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
        if(m.type==='call_service'){return{response:{value:[1234]}}}
        if(m.type==='config/entity_registry/get')return{device_id:'dev123'};
        return{};}});
    window.__mk=mk;
    const el=document.createElement('bms-panel-card');el.setConfig({type:'custom:bms-panel-card'});document.getElementById('h').appendChild(el);el.hass=mk();window.__el=el;
  },ents);

  const tag='d'; const q=(f,a)=>p.evaluate(f,a);
  await q(()=>__el.shadowRoot.getElementById('tabDiag').click());
  await q(()=>{const e=__el.shadowRoot;e.getElementById('dgPw').value='slonce';e.querySelector('[data-act=unlock]').click();});
  await q(()=>__el.shadowRoot.querySelector('[data-sec=config]').click());
  const ZE='number.inverter_zero_export_power';
  const setv=(eid,v)=>q(([eid,v])=>{const i=__el.shadowRoot.querySelector(`[data-eid="${eid}"]`);i.value=v;i.dispatchEvent(new Event('input',{bubbles:true}));},[eid,v]);
  const toast=()=>q(()=>__el.shadowRoot.getElementById('dgToast').textContent);
  const saveRow=(eid)=>q((eid)=>__el.shadowRoot.querySelector(`[data-eid="${eid}"]`).closest('.dg-row').querySelector('[data-act=save-row]').click(),eid);
  // 1) wiersz: rekomendacja + znacznik "wg instrukcji"
  const rowTxt=await q((eid)=>__el.shadowRoot.querySelector(`[data-eid="${eid}"]`).closest('.dg-row').innerText,ZE);
  ok(/20–100 W/.test(rowTxt)&&/wg instrukcji/.test(rowTxt),'zero export: rekomendacja 20–100 W + znacznik instrukcji');
  ok(!/ujemna = lekki eksport/.test(rowTxt),'fałszywa podpowiedź o ujemnej wartości usunięta');
  // 2) -20 zablokowane (dokładnie błąd użytkownika; encja deklaruje min -20)
  await setv(ZE,'-20'); await saveRow(ZE);
  ok(/bez znaku|ujemna/i.test(await toast()),'wpisanie −20 zablokowane: '+(await toast()).slice(0,80));
  ok((await q(()=>__calls.filter(c=>c[1]==='set_value').length))===0,'−20 nie wysłane do falownika');
  // 3) 30 W dozwolone, bez ostrzeżeń, potwierdzenie -> zapis
  await setv(ZE,'30'); await saveRow(ZE);
  ok(await q(()=>!!__el.shadowRoot.querySelector('.dg-modal')),'30 W: modal potwierdzenia');
  ok(await q(()=>!__el.shadowRoot.querySelector('.dg-modal .dg-redbox')),'30 W: bez czerwonych ostrzeżeń');
  await q(()=>__el.shadowRoot.querySelector('.dg-modal [data-id=ok]').click());
  await p.waitForTimeout(1500);
  ok((await q(()=>__calls.filter(c=>c[1]==='set_value'&&c[2].value===30).length))===1,'30 W zapisane');
  ok(/Kontrola odczytu/.test(await toast()),'komunikat bez przesadnego "falownik potwierdził": '+(await toast()).slice(0,70));
  const w1=await q(()=>__el._dgLS().get('bms_diag_watch',[]));
  ok(w1.length===1&&w1[0].eid===ZE&&w1[0].prev==='20','kontrola po zapisie zaplanowana (prev=20)');
  // 4) symulacja: po 3 min rejestr raportuje 65515 -> alarm
  await q(()=>{__states['number.inverter_zero_export_power'].state='65515';__el.hass=__mk();});
  await q(()=>{const real=Date.now;window.__realNow=real;Date.now=()=>real()+200e3;});
  await q(()=>{__el._dgS()._wcAt=0;__el._dgSyncTab();__el._dgS()._tickAt=0;__el._dgTick();});
  const al=await q(()=>__el._dgLS().get('bms_diag_alarms',[]));
  ok(al.length===1&&al[0].read==='65515'&&al[0].wrote===30,'alarm rozbieżności: zapisano 30, odczyt 65515');
  ok(await q(()=>/Kontrola po zapisie wykryła rozbieżność/.test(__el.shadowRoot.getElementById('dgAlarmBox').innerText)),'baner alarmu widoczny');
  ok(/⚠/.test(await q(()=>__el.shadowRoot.getElementById('tabDiag').textContent)),'znacznik ⚠ na zakładce');
  const rt2=await q((eid)=>__el.shadowRoot.querySelector(`[data-eid="${eid}"]`).closest('.dg-row').innerText,ZE);
  ok(/podejrzanie duży|powyżej zakresu/.test(rt2),'wiersz ostrzega o podejrzanym odczycie 65515');
  await p.screenshot({path:SC+'diag_alarm.png'});
  // 5) przywrócenie 20
  await q(()=>{Date.now=window.__realNow;});
  await q(()=>__el.shadowRoot.querySelector('[data-act=alarm-restore]').click());
  await p.waitForTimeout(200);
  ok(await q(()=>!!__el.shadowRoot.querySelector('.dg-modal')),'przywracanie: modal');
  await q(()=>{const m=__el.shadowRoot.querySelector('.dg-modal');const n=m.querySelector('#dgNeed');if(n)n.click();m.querySelector('[data-id=ok]').click();});
  await p.waitForTimeout(1500);
  ok((await q(()=>__calls.filter(c=>c[1]==='set_value'&&c[2].value===20).length))===1,'przywrócono 20 W');
  ok((await q(()=>__el._dgLS().get('bms_diag_alarms',[]).length))===0,'alarm zdjęty po przywróceniu');
  // 6) stabilna wartość -> kontrola kończy się OK i wpis w dzienniku
  await setv('number.inverter_battery_shutdown_soc','15'); await saveRow('number.inverter_battery_shutdown_soc');
  await q(()=>{const m=__el.shadowRoot.querySelector('.dg-modal');if(m){m.querySelector('#dgNeed').click();m.querySelector('[data-id=ok]').click();}});
  await p.waitForTimeout(1500);
  await q(()=>{const real=Date.now;window.__realNow=real;Date.now=()=>real()+400e3;});
  await q(()=>{__el._dgS()._wcAt=0;__el._dgSyncTab();});
  await q(()=>{Date.now=window.__realNow;});
  const lg=await q(()=>__el._dgLS().get('bms_diag_log',[]).filter(r=>r.eid==='number.inverter_battery_shutdown_soc'));
  ok(lg.length&&lg[0].ver==='ok','stabilna wartość: wpis w dzienniku ver=ok ('+(lg[0]&&lg[0].ver)+')');
  // 7) % > 100 zablokowane
  await setv('number.inverter_battery_shutdown_soc','150'); await saveRow('number.inverter_battery_shutdown_soc');
  ok(/0–100|Maks/.test(await toast()),'SOC 150% zablokowane: '+(await toast()).slice(0,60));
  // 8) nierozpoznany parametr z min<0: ostrzeżenie zamiast błędu; ujemny bez min<0: blokada
  await q(()=>{__states['number.inverter_mystery_offset']={state:'5',attributes:{friendly_name:'Inverter Mystery Offset',min:-50,max:50,step:1,unit_of_measurement:'W'},last_updated:'x'};__el.hass=__mk();__el._dgRenderSection();});
  await setv('number.inverter_mystery_offset','-5'); await saveRow('number.inverter_mystery_offset');
  ok(await q(()=>/nie rozpoznaje/.test((__el.shadowRoot.querySelector('.dg-modal')||{innerText:''}).innerText)),'nieznany parametr z min<0: ostrzeżenie w modalu');
  await q(()=>__el.shadowRoot.querySelector('.dg-modal [data-id=cancel]').click());
  const chk=await q(()=>({a:__el._dgCheckValue('number.inverter_zero_export_power',-1),b:__el._dgCheckValue('number.inverter_battery_temperature_compensation',-5),c:__el._dgCheckValue('number.inverter_zero_export_power',2000),d:__el._dgCheckValue('number.inverter_zero_export_power',30)}));
  ok(!!chk.a.err,'reguła: -1 W blokada'); ok(!chk.b.err,'reguła: kompensacja temp. dopuszcza minus (zakres encji 0–50 → min check osobno)'); ok(!chk.c.err&&chk.c.warn.length>=1,'reguła: 2000 W ostrzeżenie'); ok(!chk.d.err&&!chk.d.warn.length,'reguła: 30 W czysto');
  // 9) import z -20: pominięty
  await q(()=>__el._dgApplyValues({'number.inverter_zero_export_power':'-20'},'Import test'));
  ok(/Pominięto 1/.test(await toast()),'import: wartość −20 pominięta: '+(await toast()).slice(0,70));
  // 10) ściągawka
  ok(await q(()=>/Co można ustawiać/.test(__el.shadowRoot.querySelector('.dg-cheat').innerText)),'ściągawka obecna');
  // 11) log status
  await q(()=>__el.shadowRoot.querySelector('[data-sec=log]').click());
  ok(await q(()=>/kontrola odczytu OK|zmieniła się po zapisie/.test(__el.shadowRoot.getElementById('dgBody').innerText)),'dziennik pokazuje status kontroli');
  console.log('ERR',JSON.stringify(errs));
  if(errs.length) fails++;
  await ctx.close();
 }
 await b.close(); console.log(fails?('FAILS '+fails):'ALL OK'); process.exit(fails?1:0);
})();
