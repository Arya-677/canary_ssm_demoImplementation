// DOM-state checks of the actual renderer plus real authenticated backend HTTP.
import vm from 'node:vm';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
const base=process.argv[2]??'http://127.0.0.1:8776',output=process.argv[3];
const elements=new Map();
const el=id=>{if(!elements.has(id))elements.set(id,{id,textContent:'',innerHTML:'',className:'',value:'',hidden:false,disabled:false,listeners:{},addEventListener(n,f){this.listeners[n]=f;}});return elements.get(id);};
el('detector-setting').value='strong';
const document={getElementById:el,createElement:()=>({click(){}})};
const context=vm.createContext({document,Date,Math,Number,String,Object,JSON,console,crypto:webcrypto,URL,AbortSignal,
  fetch:(url,opts)=>fetch(new URL(url,base),opts),setTimeout:()=>0,setInterval:()=>0});
vm.runInContext(await fs.readFile(new URL('../canary_ssm/web/detectors.js',import.meta.url),'utf8'),context);
// Initial poll is async; wait on HTTP and microtask completion, not a simulation loop.
for(let i=0;i<30&&!el('detector-sample').innerHTML.includes('demo-01');i++)await new Promise(r=>setTimeout(r,20));
assert.ok(el('detector-sample').innerHTML.includes('demo-01'));
el('detector-sample').value='demo-01';await el('detector-load').listeners.click();
assert.match(el('detector-status').textContent,/OBSERVATIONS AVAILABLE.*UNCALIBRATED/);
assert.match(el('detector-meta').innerHTML,/detector-replay-01/);
for(const id of ['detector-raw','detector-residual','detector-effect','detector-risk','detector-group','detector-deviation'])assert.match(el(id).innerHTML,/<svg/);
assert.match(el('detector-effect').innerHTML,/<polygon/);
assert.equal((el('detector-effect').innerHTML.match(/<path/g)||[]).length,3);
assert.match(el('detector-risk-summary').innerHTML,/not a joint release probability/);
assert.ok(!el('detector-meta').innerHTML.includes('fault_type'));
const first=el('detector-effect').innerHTML;
el('detector-setting').value='weak';await el('detector-setting').listeners.change();
assert.notEqual(el('detector-effect').innerHTML,first);
el('detector-seek').value='90';await el('detector-seek').listeners.change();
assert.match(el('detector-status').textContent,/INSUFFICIENT DATA/);
el('detector-seek').value='100';await el('detector-seek').listeners.change();
const a=await(await fetch(base+'/api/detectors')).json();
el('detector-host').value=a.metadata.host_roster[2].host_id;await el('detector-host').listeners.change();
assert.equal(el('detector-host').value,a.metadata.host_roster[2].host_id);
await el('detector-pause').listeners.click();assert.equal(el('detector-host').value,a.metadata.host_roster[2].host_id);
el('detector-sample').value='demo-04';await el('detector-load').listeners.click();
assert.match(el('detector-meta').innerHTML,/detector-replay-04/);
await el('detector-recipe-load').listeners.click();assert.match(el('detector-recipe').textContent,/EVALUATOR.*TRUTH ONLY/);
assert.ok(!el('detector-risk-summary').innerHTML.includes('targets'));
// Reconnect failure: inject a network error into the read-only fetch path.
const fetchOK=context.fetch;context.fetch=async()=>{throw Error('test disconnected')};
el('detector-host').value=a.metadata.host_roster[0].host_id;await el('detector-host').listeners.change();
assert.match(el('detector-status').textContent,/DISCONNECTED/);
context.fetch=fetchOK;await el('detector-host').listeners.change();
assert.match(el('detector-status').textContent,/UNCALIBRATED/);
// Incremental external posterior stream: render waiting/fresh/stale/recovered states.
const recording=await(await fetch(base+'/api/detectors/export')).json();
async function post(command,args){const state=await(await fetch(base+'/api/state')).json();const r=await fetch(base+'/api/commands',{method:'POST',headers:{'Content-Type':'application/json','X-World-Token':state.command_token},body:JSON.stringify({command_id:webcrypto.randomUUID(),run_id:state.run_id,epoch:state.epoch,command,args})});assert.equal(r.status,200);}
const metadata=Object.fromEntries(Object.entries(recording).filter(([k])=>!['frames','artifact_sha256'].includes(k)));metadata.source_kind='external-detector-stream';
await post('monitor_begin',{metadata});await post('monitor_append',{frame:recording.frames[130]});await el('detector-host').listeners.change();
assert.match(el('detector-message').textContent,/External detector output stream/);
await new Promise(resolve=>setTimeout(resolve,5150));await el('detector-host').listeners.change();
assert.match(el('detector-status').textContent,/STALE STREAM/);
await post('monitor_append',{frame:recording.frames[131]});await el('detector-host').listeners.change();
assert.match(el('detector-status').textContent,/OBSERVATIONS AVAILABLE/);
const result={passed:true,checks:{six_charts:true,three_same_replay_effect_lines:true,uncertainty_band:true,setting_switch:true,
  insufficient_distinct:true,stable_host_selection:true,explicit_run_identity:true,truth_separate:true,disconnect_reconnect:true,streamed_frames:true,stale_stream_recovery:true},
  verification:'Node DOM-state harness plus real HTTP. Browser visual verification unavailable.'};
if(output)await fs.writeFile(output,JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result,null,2));
