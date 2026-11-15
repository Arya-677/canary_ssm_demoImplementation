// DOM-state/API integration checks without a browser dependency. Not visual QA.
import vm from "node:vm";
import fs from "node:fs/promises";
import assert from "node:assert/strict";
import {webcrypto} from "node:crypto";
import {fileURLToPath} from "node:url";
import path from "node:path";

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"..");
const base=process.argv[2] ?? "http://127.0.0.1:8765";
const output=process.argv[3];
const source=await fs.readFile(path.join(root,"canary_ssm/web/app.js"),"utf8");
const checks={};
function harness(search="") {
  const elements=new Map(), requests=[];let clock=100;
  const document={listeners:{},getElementById(id){if(!elements.has(id))elements.set(id,{id,textContent:"",innerHTML:"",className:"",disabled:false,hidden:false,value:"",listeners:{},addEventListener(name,fn){this.listeners[name]=fn;}});return elements.get(id);},addEventListener(name,fn){this.listeners[name]=fn;}};
  const context=vm.createContext({document,location:{search},URLSearchParams,AbortSignal,crypto:webcrypto,
    performance:{now:()=>clock},Date,console,setTimeout:()=>0,setInterval:()=>0,
    fetch:(url,opts)=>{requests.push(String(url));return fetch(new URL(url,base),opts);}});
  vm.runInContext(source,context);
  return {context,e:id=>document.getElementById(id),run:code=>vm.runInContext(code,context),requests,
    age(ms){clock+=ms;},select(host){document.listeners.click({target:{closest(selector){return selector==="[data-host]"?{dataset:{host}}:null;}}});}};
}
if(process.argv[4]!=="--recorded-only") {
const live=harness();
await live.run("fetchState()");
await live.run("send('reset')");
assert.equal(live.e("connection").textContent,"Connected");
assert.equal((live.e("rack-grid").innerHTML.match(/class="host-tile/g)||[]).length,20);
assert.match(live.e("tree").innerHTML,/dc-01/);
checks.topology_rendered=true;

await live.run("send('step')");
assert.equal(live.run("packet.snapshot.tick"),1);
assert.equal(live.e("clock-state").textContent,"PAUSED");
assert.match(live.e("cpu-chart").innerHTML,/<svg/);
live.select("host-02-03");
await live.run("fetchState()");
assert.equal(live.e("host-title").textContent,"host-02-03");
assert.match(live.e("host-path").textContent,/rack-02/);
assert.equal(live.run("packet.history.host_id"),"host-02-03");
assert.equal(live.run("historyForHost().at(-1).host_id"),"host-02-03");
checks.selected_host_backend_trace=true;

await live.run("send('reset')");
await live.run("send('speed',8)");
assert.equal(live.run("packet.speed"),8);
await live.run("send('start')");
assert.equal(live.run("packet.snapshot.state"),"running");
await live.run("send('pause')");
const frozen=live.run("packet.snapshot.tick");
await live.run("fetchState()");
assert.equal(live.run("packet.snapshot.tick"),frozen);
await live.run("send('step')");
assert.equal(live.run("packet.snapshot.tick"),frozen+1);
checks.controls_and_speed=true;

const runId=live.run("packet.run_id");
const another=harness();await another.run("fetchState()");
assert.equal(another.run("packet.run_id"),runId);
checks.refresh_reuses_run=true;

live.age(3000);live.run("connection()");
assert.equal(live.e("connection").textContent,"Stale data");
assert.equal(live.e("step").disabled,true);
checks.stale_state=true;
const originalFetch=live.context.fetch;
live.context.fetch=async()=>{throw new Error("test network loss");};
await live.run("poll()");
assert.equal(live.e("connection").textContent,"Disconnected");
assert.equal(live.e("reset").disabled,true);
assert.equal(live.e("host-title").textContent,"host-02-03");
live.context.fetch=originalFetch;
await live.run("poll()");
assert.equal(live.e("connection").textContent,"Connected");
checks.disconnect_reconnect_preserves_last_view=true;
await live.run("send('reset')");

}
const recording=harness("?recorded=1");await recording.run("fetchState()");
assert.equal(recording.e("connection").textContent,"Recorded snapshot");
assert.equal(recording.e("step").disabled,true);
assert.equal(recording.e("start").disabled,true);
recording.select("host-04-05");
assert.equal(recording.e("host-title").textContent,"host-04-05");
assert.equal(recording.run("historyForHost().at(-1).host_id"),"host-04-05");
assert.ok(recording.requests.every(url=>url==="/recorded_snapshot.json"));
checks.recorded_mode_has_no_engine_api_calls=true;
assert.ok(!source.includes("Math.random"));
assert.match(await fs.readFile(path.join(root,"canary_ssm/web/index.html"),"utf8"),/Monitoring not connected/);
checks.no_frontend_simulator_or_detector=true;
const result={checks,passed:Object.values(checks).every(Boolean),browser_layout_verified:false,
  verification:"Node DOM-state harness plus real local HTTP API; browser startup unavailable"};
if(output)await fs.writeFile(output,JSON.stringify(result,null,2)+"\n");
console.log(JSON.stringify(result,null,2));
