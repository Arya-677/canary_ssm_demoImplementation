// Execute the actual seven-view app against a real backend. No simulated values.
import vm from 'node:vm';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
const [base,out]=process.argv.slice(2),store=new Map();
const markup=await fs.readFile(new URL('../canary_ssm/web/index.html',import.meta.url),'utf8');
const htmlIds=new Set([...markup.matchAll(/\bid=["']([^"']+)["']/g)].map(x=>x[1]));
let loseResponse=false,dropRequest=false;
function app(){
  const elements=new Map();
  const el=id=>{assert.ok(htmlIds.has(id),'Renderer requested missing HTML ID: '+id);if(!elements.has(id))elements.set(id,{id,textContent:id==='latest-command-id'?'—':'',innerHTML:'',className:'',value:'',checked:false,hidden:false,disabled:false,files:[],listeners:{},addEventListener(n,f){this.listeners[n]=f;},setAttribute(){}});return elements.get(id);};
  const context=vm.createContext({document:{getElementById:el,addEventListener(){}},URLSearchParams,URL,location:{search:'',hash:''},sessionStorage:{getItem:k=>store.get(k)??null,setItem:(k,v)=>store.set(k,v),removeItem:k=>store.delete(k)},performance:{now:()=>100},Date,Math,Number,String,Object,JSON,console,crypto:webcrypto,AbortSignal,fetch:async(url,opts)=>{
    if(opts?.method==='POST'&&dropRequest){dropRequest=false;throw Error('Disconnected before delivery');}
    const result=await fetch(new URL(url,base),opts);
    if(opts?.method==='POST'&&loseResponse){loseResponse=false;throw Error('Response lost after backend commit');}
    return result;
  },setInterval:()=>0,setTimeout:()=>0,Uint8Array,btoa:s=>Buffer.from(s,'binary').toString('base64')});
  return {el,context,run:s=>vm.runInContext(s,context)};
}
const a=app(),{el,run}=a;
for(const file of ['app.js','console.js'])vm.runInContext(await fs.readFile(new URL('../canary_ssm/web/'+file,import.meta.url),'utf8'),a.context);
await run('fetchState()');await run('fetchCatalog()');
const initialRun=await run('packet.run_id');
for(const name of ['world','host','faults','releases','rollout','monitoring','history']){
  await run(`selectView('${name}')`);assert.equal(el('view-'+name).hidden,false);
  assert.equal(el('shared-topology').hidden,!['world','rollout'].includes(name));
}
await run("selectView('rollout')");
el('release-select').value='release-001';el('canary-count').value='1';el('rollout-fraction').value='.35';el('rollout-baseline-seconds').value='2';el('rollout-horizon-seconds').value='10';
await el('rollout-preview').onclick();assert.match(el('rollout-allocation').innerHTML,/BACKEND-VALIDATED.*host-01/s);
await el('rollout-create').onclick();assert.match(el('rollout-current').textContent,/CREATED/);
await el('rollout-baseline').onclick();assert.match(el('rollout-current').textContent,/PENDING rollout_baseline/);
await run("send('step')");await run("send('step')");await el('rollout-expose').onclick();await run("send('step')");
assert.match(el('world-replicas').innerHTML,/release-001/);assert.match(el('world-replicas').innerHTML,/8.8%/);
assert.match(el('decision-reason').textContent,/No compatible policy/);assert.match(el('context-calibration').textContent,/UNCALIBRATED/);
await el('rollout-pause').onclick();await run("send('step')");assert.match(el('rollout-current').textContent,/PAUSED/);
await el('rollout-rollback').onclick();await run("send('step')");assert.match(el('rollout-current').textContent,/ROLLED_BACK/);
assert.match(el('event-timeline').innerHTML,/manual_rollback_restart/);
assert.ok(el('latest-command-id').textContent.length>30);
el('release-manifest-json').value=JSON.stringify({schema_version:1,release_id:'integrated-ui-release',service_id:'demo-service',version:'8.0.0',creation_metadata:{author:'UI-check'},behavior_manifest:{schema_version:1,profiles:[{kind:'healthy'}]}});
await el('register-manifest').listeners.click();assert.match(el('registry-list').innerHTML,/integrated-ui-release/);
el('release-manifest-json').value='{"bad":true}';await el('register-manifest').listeners.click();assert.match(el('manifest-registration-status').textContent,/rejected|failed/i);
const before=await run('packet.snapshot.tick');loseResponse=true;await run("Promise.all([send('step'),send('step')])");
assert.equal(await run('packet.snapshot.tick'),before+1);assert.equal(el('step').disabled,true);
await run('recoverUnconfirmed()');assert.equal(await run('unconfirmed'),null);assert.match(el('command-status').textContent,/SUCCESS recovered/);
dropRequest=true;await run("send('step')");const unknown=await run('unconfirmed.command_id');await run('recoverUnconfirmed()');
assert.equal(el('retry-command').hidden,false);await el('retry-command').onclick();assert.equal(await run('unconfirmed'),null);
const receipt=await(await fetch(base+'/api/commands?command_id='+unknown)).json();assert.equal(receipt.known,true);
await el('history-save').onclick();assert.match(el('history-list').innerHTML,/backend JSON/);
const rows=await(await fetch(base+'/api/history')).json();const checkpoint=rows.checkpoints[0].checkpoint_id;
await run(`send('history_load',null,{checkpoint_id:'${checkpoint}'})`);assert.equal(await run('packet.read_only'),true);
const replayTick=await run('packet.snapshot.tick');
const refreshed=app();for(const file of ['app.js','console.js'])vm.runInContext(await fs.readFile(new URL('../canary_ssm/web/'+file,import.meta.url),'utf8'),refreshed.context);
await refreshed.run('fetchState()');assert.equal(await refreshed.run('packet.run_id'),initialRun);assert.equal(await refreshed.run('packet.snapshot.tick'),replayTick);
assert.equal(refreshed.el('step').disabled,true);
const saved=await(await fetch(base+'/api/run')).json();assert.equal(saved.engine.final_snapshot.tick,replayTick);
const result={passed:true,checks:{seven_views:true,shared_topology_world_and_rollout:true,backend_host_cohort_preview:true,baseline_exposure_pause_rollback:true,active_versions_and_traffic:true,manifest_registration_and_validation_errors:true,full_command_ids:true,lost_response_same_id_recovery:true,duplicate_click_suppressed:true,undelivered_retry_same_id:true,backend_checkpoint_replay_export:true,refresh_same_run_and_tick:true},scope:'Actual HTTP commands and unchanged backend simulation through the real DOM render functions; no numerical browser simulation.'};
if(out)await fs.writeFile(out,JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result,null,2));
