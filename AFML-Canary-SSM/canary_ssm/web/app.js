"use strict";
const $ = id => document.getElementById(id);
const recorded = new URLSearchParams(location.search).get("recorded") === "1";
let packet = null, selectedHost = null, scope = {kind:"all", id:null};
let lastContact = 0, disconnected = false, pending = false, requestNumber = 0, appliedRequest = 0;
let unconfirmed=null;
let activeView="world", releaseCatalog=[], catalogLoaded=false, allocation=null;
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const finite = v => typeof v === "number" && Number.isFinite(v);
const fmt = (v, suffix="", digits=1) => finite(v) ? v.toLocaleString(undefined,{maximumFractionDigits:digits})+suffix : "—";
function simulatedTime(seconds) {
  const n = Math.max(0,Math.floor(seconds));
  return [Math.floor(n/3600), Math.floor(n/60)%60, n%60].map(x=>String(x).padStart(2,"0")).join(":");
}
function notice(text, kind="") {
  $("notice").hidden = !text; $("notice").textContent = text; $("notice").className = "notice "+kind;
}
function connection() {
  let label = "Connecting", kind = "stale";
  const elapsed = lastContact ? performance.now()-lastContact : Infinity;
  const backendOld = packet && !recorded && finite(packet.server_time_unix_ms) && Date.now()-packet.server_time_unix_ms > 5000;
  if (recorded && packet) {label="Recorded snapshot";kind="recorded";}
  else if (disconnected) {label="Disconnected";kind="disconnected";}
  else if (packet?.read_only) {label="Saved run replay";kind="recorded";}
  else if (packet && (elapsed>2500 || backendOld || packet.driver_error)) {label="Stale data";kind="stale";}
  else if (packet) {label="Connected";kind="connected";}
  $("connection").textContent=label; $("connection").className="connection "+kind;
  if (recorded && packet) notice("Recorded snapshot · fixed backend outputs for UI development. Simulation controls are disabled.","recorded");
  else if (packet?.read_only && !disconnected) notice("Verified saved-run replay · backend-reconstructed world and recorded telemetry. Reset to return to a live world.","recorded");
  else if (packet?.driver_error) notice("Backend clock stopped: "+packet.driver_error+". Reset to recover.","error");
  else if (disconnected) notice("Disconnected from the backend. Showing the last received snapshot; controls are unavailable.","error");
  else if (kind==="stale" && packet) notice("Snapshot updates are delayed. Displayed values may be stale; waiting for the backend.");
  else if (!pending) notice("");
  const blocked = recorded || packet?.read_only || pending || !!unconfirmed || !packet || disconnected || kind==="stale";
  if(packet){renderRollout();renderReleasePolicy();}
  const state=packet?.snapshot.state;
  $("start").disabled=blocked || state!=="ready";
  $("pause").disabled=blocked || state!=="running";
  $("resume").disabled=blocked || state!=="paused";
  $("step").disabled=blocked || state==="running";
  $("reset").disabled=recorded || pending || !packet || disconnected || (kind==="stale" && !packet?.driver_error);
  $("speed").disabled=blocked;
  $("restart-process").disabled=blocked || !packet?.snapshot.resources?.replicas.some(r=>r.host_id===selectedHost);
  for(const id of ["register-release","preview-release","schedule-fault","random-faults","background-enable","background-disable","background-preview","register-manifest","build-release-manifest","release-manifest-upload","manifest-source"]) $(id).disabled=blocked || !packet?.console_available;
  const status=packet?.snapshot.deployment?.status ?? "idle";
  $("deploy-release").disabled=blocked || !allocation || !["idle","rolled_back"].includes(status);
  $("rollback-release").disabled=blocked || !["deploy_pending","canary","rollback_pending"].includes(status);
  $("save-run").disabled=recorded || pending || !packet || disconnected || kind==="stale";
  $("load-run").disabled=recorded || pending || !packet || disconnected || kind==="stale";
  if(blocked)for(const id of ["rollout-create","rollout-baseline","rollout-expose","rollout-pause","rollout-resume","rollout-promote","rollout-rollback","policy-attach","rollout-preview","history-save"])$(id).disabled=true;
  if(typeof document.querySelectorAll==="function")for(const button of document.querySelectorAll("[data-history-load]"))button.disabled=blocked||state==="running";
  if (packet) $("sample-age").textContent=recorded ? "Fixed recording" : `Last contact ${fmt(elapsed/1000,"s")} ago`;
}
function historyForHost() {
  if (!packet) return [];
  return recorded ? packet.recorded_history?.[selectedHost] ?? [] : packet.history.host_id===selectedHost ? packet.history.rows : [];
}
function drawChart(id, rows, key, {max=null, peak=null}={}) {
  const samples=rows.filter(r=>finite(r.simulated_seconds));
  if (!samples.length || !samples.some(r=>finite(r[key]))) {$(id).innerHTML='<p class="empty">No observations yet</p>'; return;}
  const values=samples.flatMap(r=>[r[key],peak?r[peak]:null]).filter(finite);
  const top=max ?? Math.max(1,...values)*1.12;
  const first=samples[0].simulated_seconds,last=samples.at(-1).simulated_seconds;
  const x=t=>32+(t-first)/Math.max(1,last-first)*248, y=v=>108-Math.max(0,v)/top*92;
  function path(field) {
    let active=false; return samples.map(r=>{if(!finite(r[field])){active=false;return "";}const s=`${active?"L":"M"}${x(r.simulated_seconds).toFixed(2)},${y(r[field]).toFixed(2)}`;active=true;return s;}).join(" ");
  }
  const line=`<path class="series" d="${path(key)}"/>`;
  const extra=peak?`<path class="series peak" d="${path(peak)}"/>`:"";
  const points=samples.filter(r=>finite(r[key]));const lastPoint=points.at(-1);
  $(id).innerHTML=`<svg viewBox="0 0 292 140" role="img" aria-label="${esc(key)} over simulated seconds"><title>Latest ${esc(key)}: ${esc(fmt(lastPoint[key]))}; simulated second ${lastPoint.simulated_seconds}</title><line class="grid-line" x1="32" x2="280" y1="16" y2="16"/><line class="grid-line" x1="32" x2="280" y1="62" y2="62"/><line class="grid-line" x1="32" x2="280" y1="108" y2="108"/><text class="axis-label" x="0" y="19">${esc(fmt(top,"",0))}</text><text class="axis-label" x="7" y="111">0</text>${extra}${line}<circle cx="${x(lastPoint.simulated_seconds)}" cy="${y(lastPoint[key])}" r="2.5" fill="#168b87"/><text class="axis-label" x="32" y="133">${first}s</text><text class="axis-label" x="280" y="133" text-anchor="end">${last}s</text></svg>`;
}
function render() {
  if (!packet) return;
  const {snapshot,summary}=packet, world=snapshot.world;
  if (!world.hosts.some(h=>h.host_id===selectedHost)) selectedHost=world.hosts[0]?.host_id ?? null;
  const obs=new Map(snapshot.observations.map(o=>[o.host_id,o]));
  $("world-detector-status").textContent=packet.detector_status;
  $("run-id").textContent=packet.run_id; $("epoch").textContent=`Epoch ${packet.epoch}`;
  $("clock-state").textContent=snapshot.state.toUpperCase(); $("tick").textContent=`Tick ${snapshot.tick}`;
  $("sim-time").textContent=simulatedTime(snapshot.simulated_seconds);$("speed").value=String(packet.speed);
  $("center-count").textContent=summary.data_centers; $("rack-count").textContent=summary.racks;
  $("ready-count").textContent=summary.ready; $("host-count").textContent=`of ${summary.hosts} hosts ready`;
  $("mode-label").textContent=recorded?"Recorded synthetic fixture":"Live synthetic simulation · backend clock";
  $("mode-link").textContent=recorded?"Return to live world ↗":"Open recorded snapshot ↗";
  $("mode-link").href=recorded?"/":"/?recorded=1";
  let tree=`<button class="center-button ${scope.kind==="all"?"active":""}" data-scope="all" data-id="">All infrastructure</button>`;
  for(const dc of world.data_centers) {
    tree+=`<button class="center-button ${scope.kind==="center"&&scope.id===dc.data_center_id?"active":""}" data-scope="center" data-id="${esc(dc.data_center_id)}">▦ ${esc(dc.data_center_id)}</button>`;
    for(const rack of world.racks.filter(r=>r.data_center_id===dc.data_center_id)) {
      tree+=`<button class="rack-button ${scope.kind==="rack"&&scope.id===rack.rack_id?"active":""}" data-scope="rack" data-id="${esc(rack.rack_id)}">▤ ${esc(rack.rack_id)}</button>`;
      for(const host of world.hosts.filter(h=>h.rack_id===rack.rack_id)) tree+=`<button class="host-button ${selectedHost===host.host_id?"active":""}" data-host="${esc(host.host_id)}"><span class="tree-dot ${esc(host.lifecycle)}"></span>${esc(host.host_id)}</button>`;
    }
  }
  $("tree").innerHTML=tree || '<p class="empty">No infrastructure configured</p>';
  const racks=world.racks.filter(r=>scope.kind==="all" || (scope.kind==="rack"?r.rack_id===scope.id:r.data_center_id===scope.id));
  $("scope-title").textContent=scope.kind==="all"?"All infrastructure":scope.id;
  $("scope-count").textContent=`${racks.length} racks · ${world.hosts.filter(h=>racks.some(r=>r.rack_id===h.rack_id)).length} hosts`;
  $("rack-grid").innerHTML=racks.map(r=>{
    const hosts=world.hosts.filter(h=>h.rack_id===r.rack_id);
    return `<article class="rack-card"><div class="rack-heading"><button data-scope="rack" data-id="${esc(r.rack_id)}">${esc(r.rack_id)}</button><span>${hosts.filter(h=>h.lifecycle==="ready" && obs.get(h.host_id)?.available!==false).length}/${hosts.length} ready</span></div><div class="hosts">${hosts.map(h=>{
      const cpu=100*h.usage.cpu_cores/h.capacity.cpu_cores;
      const versions=world.replicas.filter(r=>r.host_id===h.host_id).map(r=>r.release_id).join(", ");
      const available=obs.get(h.host_id)?.available!==false;
      return `<button class="host-tile ${h.host_id===selectedHost?"selected":""}" data-host="${esc(h.host_id)}" title="${esc(h.host_id)} · ${esc(available?h.lifecycle:"unavailable")} · ${esc(versions)}" aria-label="Select ${esc(h.host_id)}"><strong><span class="dot ${esc(available?h.lifecycle:"offline")}"></span>${esc(h.host_id.replace(/^host-/,""))}</strong><span class="version-badge">${esc(versions || "No replica")}</span><small>${esc(fmt(cpu,"% CPU",0))}</small><small>${esc(fmt(h.usage.memory_mb," MB",0))}</small><meter min="0" max="100" value="${cpu}" aria-label="CPU utilization"></meter></button>`;
    }).join("")}</div></article>`;
  }).join("") || '<p class="empty">No racks in this view</p>';
  const host=world.hosts.find(h=>h.host_id===selectedHost);
  if(host) {
    const o=obs.get(host.host_id);
    $("host-title").textContent=host.host_id; $("host-path").textContent=`${host.data_center_id} / ${host.rack_id} / Class ${host.class_id}`;
    const status=o?.available===false?"unavailable":host.lifecycle;
    $("host-status").textContent=status;$("host-status").className="status-chip "+(status==="unavailable"?"offline":status);
    $("host-cpu").textContent=fmt(100*host.usage.cpu_cores/host.capacity.cpu_cores,"%");
    $("host-memory").textContent=fmt(host.usage.memory_mb," MB",0);
    $("host-latency").textContent=fmt(o?.latency_proxy_ms," ms");$("host-queue").textContent=fmt(o?.queue_end,"",0);
    const history=historyForHost();
    drawChart("cpu-chart",history.map(r=>({...r,cpu_percent:r.cpu_utilization*100})),"cpu_percent",{max:100});
    drawChart("memory-chart",history,"memory_mb",{peak:"memory_peak_mb"});drawChart("latency-chart",history,"latency_proxy_ms");
    const replicas=world.replicas.filter(r=>r.host_id===host.host_id);
    $("replicas").innerHTML=`<strong>${host.capacity.cpu_cores} cores · ${esc(fmt(host.capacity.memory_mb," MB",0))} capacity</strong><br>`+replicas.map(r=>`${esc(r.service_id)} / ${esc(r.replica_id)} · ${esc(r.release_id)}`).join("<br>");
  }
  renderConsole();
  if(typeof renderDashboard==="function")renderDashboard();
  connection();
}
async function fetchState() {
  const number=++requestNumber;
  const response=await fetch(recorded?"/recorded_snapshot.json":"/api/state"+(selectedHost?"?host_id="+encodeURIComponent(selectedHost):""),{cache:"no-store",signal:AbortSignal.timeout(3000)});
  if(!response.ok)throw new Error("Snapshot request failed ("+response.status+")");
  const data=await response.json();
  if(data.schema_version!==1 || !data.snapshot || !data.summary || !data.history || !["Monitoring not connected","Uncalibrated output stream","Calibrated policy input","Stale calibrated policy input","Closed calibrated policy evaluation","Saved calibrated policy replay"].includes(data.monitoring))throw new Error("Unsupported snapshot format");
  if(number<appliedRequest || (packet && packet.run_id===data.run_id && data.revision<packet.revision))return;
  if(packet && (packet.run_id!==data.run_id || packet.epoch!==data.epoch)){allocation=null;catalogLoaded=false;}
  appliedRequest=number; packet=data;lastContact=performance.now();disconnected=false; render();
  if(typeof recoverUnconfirmed==="function")recoverUnconfirmed();
}
async function poll() {
  try{await fetchState();if(!recorded && !catalogLoaded && packet.console_available)await fetchCatalog();if(activeView==="faults"&&!recorded)await fetchFaultTruth();if(activeView==="monitoring"&&!recorded)await fetchPublicTelemetry();if(activeView==="history"&&!recorded&&typeof fetchRunHistory==="function")await fetchRunHistory();}catch(error){disconnected=true;connection();}
  if(!recorded)setTimeout(poll,750);
}
async function send(command, speed=null, args=null, retryPayload=null) {
  if(!packet || pending || recorded || (unconfirmed && !retryPayload))return;
  const payload=retryPayload??{command_id:crypto.randomUUID(),run_id:packet.run_id,epoch:packet.epoch,command};
  if(!retryPayload){if(command==="speed")payload.speed=Number(speed);if(args!==null)payload.args=args;}
  $("latest-command-id").textContent=payload.command_id;
  pending=true;$("command-status").textContent=`PENDING ${command} · ${payload.command_id}`;
  if(typeof rememberCommand==="function")rememberCommand(payload);connection();
  let outcome=null,confirmed=false;
  try {
    const response=await fetch("/api/commands",{method:"POST",headers:{"Content-Type":"application/json","X-World-Token":packet.command_token},body:JSON.stringify(payload),signal:AbortSignal.timeout(["load_run","history_load"].includes(command)?60000:10000)});
    const result=await response.json();confirmed=true;
    unconfirmed=null;if(typeof forgetCommand==="function")forgetCommand();
    if(!response.ok)throw new Error(result.error || "Command failed");
    $("command-status").textContent=`SUCCESS ${command} accepted · ${result.receipt.command_id}${result.receipt.result?.pending_action?' · queued for next tick':''}`;
    outcome=result.receipt.result ?? result.receipt;
    try{await fetchState();}catch{disconnected=true;}
  } catch(error) {
    if(!confirmed){unconfirmed=payload;$("command-status").textContent=`UNCONFIRMED ${command} · ${payload.command_id} · ${error.message}`;}
    else $("command-status").textContent=`ERROR ${command} · ${payload.command_id} · ${error.message}`;
    notice(error.message+(confirmed?"":". Reconnect to resolve the same command ID before retrying."),"error");
    try{await fetchState();}catch{disconnected=true;}
  } finally {pending=false;connection();if(typeof renderDashboard==="function")renderDashboard();}
  return outcome;
}
document.addEventListener("click",event=>{
  const host=event.target.closest("[data-host]");
  if(host){selectedHost=host.dataset.host;render();if(!recorded)fetchState().catch(()=>{disconnected=true;connection();});return;}
  const selection=event.target.closest("[data-scope]");
  if(selection){scope={kind:selection.dataset.scope,id:selection.dataset.id};render();return;}
  const view=event.target.closest("[data-view]");if(view){selectView(view.dataset.view);return;}
  const button=event.target.closest("[data-command]");if(button && !button.disabled)send(button.dataset.command);
});
function selectView(name){
  if(!["world","host","releases","rollout","faults","monitoring","history"].includes(name))name="world";
  activeView=name;
  $("shared-topology").hidden=!["world","rollout"].includes(name);
  if(typeof rememberView==="function")rememberView(name);
  for(const view of ["world","host","releases","rollout","faults","monitoring","history"]){$("view-"+view).hidden=view!==name;$("nav-"+view).className=view===name?"active":"";}
  if(name!=="faults")$("fault-truth").textContent="Open this developer view to load injected truth.";
  if(["releases","rollout"].includes(name)&&!recorded)fetchCatalog().catch(e=>{$("release-info").textContent=e.message;});
  if(name==="faults"&&!recorded)fetchFaultTruth().catch(e=>{$("fault-truth").textContent=e.message;});
  if(name==="monitoring"){if(recorded)$("public-window-status").textContent="Public minute telemetry is not included in this recorded fixture.";else fetchPublicTelemetry().catch(e=>{$("public-window-status").textContent=e.message;});}
  renderConsole();
  if(name==="history"&&typeof fetchRunHistory==="function")fetchRunHistory();
  if(typeof renderDashboard==="function")renderDashboard();
}
function renderConsole(){
  if(!packet)return;
  const world=packet.snapshot.world;
  const serviceSelection=$("manifest-service").value,services=[...new Set(world.replicas.map(r=>r.service_id))];
  $("manifest-service").innerHTML=services.map(id=>`<option value="${esc(id)}">${esc(id)}</option>`).join("");
  if(services.includes(serviceSelection))$("manifest-service").value=serviceSelection;
  $("monitor-host").innerHTML=world.hosts.map(h=>`<option value="${esc(h.host_id)}">${esc(h.host_id)} · ${esc(h.rack_id)}</option>`).join("");
  $("monitor-host").value=selectedHost;
  const history=historyForHost();
  drawChart("monitor-cpu",history.map(r=>({...r,cpu_percent:r.cpu_utilization*100})),"cpu_percent",{max:100});
  drawChart("monitor-memory",history,"memory_mb",{peak:"memory_peak_mb"});drawChart("monitor-latency",history,"latency_proxy_ms");
  const deployment=packet.snapshot.deployment;
  $("deployment").innerHTML=deployment?`<strong>${esc(deployment.status.toUpperCase())}</strong><br>${esc(deployment.release_id??"No candidate")}<br>${deployment.canaries.length} canaries · ${deployment.controls.length} controls<br>${esc(deployment.canaries.join(", "))}`:"Console unavailable for this static clock config.";
  const rows=packet.outcomes??[];
  $("outcomes").innerHTML=rows.length?`<table><thead><tr><th>Tick</th><th>Command</th><th>Outcome</th><th>Receipt / detail</th></tr></thead><tbody>${[...rows].reverse().map(r=>`<tr><td>${esc(r.tick)}</td><td>${esc(r.command)}</td><td>${esc(r.status)}</td><td>${esc(r.error??String(r.command_id))}</td></tr>`).join("")}</tbody></table>`:"No commands yet.";
  renderReleasePolicy();
  renderResourceHealth();
  renderRollout();
  refreshTargets();
}
async function fetchCatalog(){
  const response=await fetch("/api/releases",{cache:"no-store",signal:AbortSignal.timeout(3000)});
  if(!response.ok)throw new Error("Release registry unavailable");
  releaseCatalog=(await response.json()).releases;catalogLoaded=true;
  const previous=$("release-select").value;
  $("release-select").innerHTML=releaseCatalog.map(r=>`<option value="${esc(r.release_id)}">${esc(r.release_id)} · ${esc(r.source)}</option>`).join("");
  $("release-select").value=releaseCatalog.some(r=>r.release_id===previous)?previous:(releaseCatalog.find(r=>r.profile==="slow")?.release_id??releaseCatalog[0]?.release_id??"");
  releaseInfo();
  if(typeof renderDashboard==="function")renderDashboard();
}
function releaseInfo(){
  const r=releaseCatalog.find(r=>r.release_id===$("release-select").value);
  $("release-info").innerHTML=r?`<strong>${r.source==="upload"?"UNEXECUTED UPLOAD":r.source==="manifest"?"REGISTERED MANIFEST · SIMULATION":"SIMULATED SAMPLE"}</strong><br>Version ${esc(r.version)} · ${esc(r.service_id)}<br>Immutable content SHA-256 ${esc(r.content_hash)}<br>${r.behavior.work_multiplier}× CPU work · ${r.behavior.memory_model==='process-memory-v1'?`${r.behavior.retained_mb_per_request} MB retained/processed request + ${r.behavior.background_mb_per_second} MB/s background · cache cap ${r.behavior.retained_limit_mb??'none'} MB · process-memory-v1 (OOM enabled)`:`${r.behavior.retained_mb_per_completion} MB retained/processed request · legacy bounded (no OOM)`} · ${r.behavior.error_probability} error probability · ${r.behavior.response_delay_ms} ms response wait<br>Declared behavior only; source is never executed${r.artifact?`<br>${esc(r.artifact.filename)} · ${r.artifact.size_bytes} bytes<br>SHA-256 ${esc(r.artifact.sha256)}`:""}`:"No release selected.";
}
function refreshTargets(){
  if(!packet)return;
  const previous=$("fault-target").value, scope=$("fault-scope").value||"host", world=packet.snapshot.world;
  const ids=scope==="rack"?world.racks.map(r=>r.rack_id):scope==="world"?["world"]:world.hosts.map(h=>h.host_id);
  $("fault-target").innerHTML=ids.map(id=>`<option value="${esc(id)}">${esc(id)}</option>`).join("");
  $("fault-target").value=ids.includes(previous)?previous:(scope==="host"&&ids.includes(selectedHost)?selectedHost:ids[0]);
}
async function fetchFaultTruth(){
  if(activeView!=="faults")return;
  const response=await fetch("/api/fault-lab?developer=1",{cache:"no-store",signal:AbortSignal.timeout(3000)});
  if(!response.ok)throw new Error("Developer fault data unavailable");
  const data=await response.json(), rows=data.injected_truth;
  if(activeView!=="faults")return;
  const b=data.background;
  if(b){
    $("background-summary").innerHTML=`<strong>${b.enabled?"BACKGROUND ENABLED":"BACKGROUND DISABLED"}</strong> · ${esc(b.config.mode)} · seed ${b.config.seed}<br>${b.summary.accepted_events} scheduled · ${b.active_events} active · ${b.future_events} future<br>Horizon tick ${b.config.horizon_ticks}${b.horizon_exhausted?" · no new starts remain":""} · max ${b.config.max_concurrent} concurrent background events<br>`+b.sampling.map(r=>`${esc(r.rule_id)}: ${r.rate_per_second_per_target}/simulated second per ${esc(r.scope)} × ${r.targets} targets; p/tick ${r.candidate_probability_per_tick.toFixed(5)}; duration ${r.duration_ticks_inclusive.join("–")} ticks; cooldown ${r.cooldown_ticks} ticks`).join("<br>");
    $("background-schedule").innerHTML=b.events.length?`<table><thead><tr><th>Background event</th><th>Scope / target</th><th>Ticks</th><th>Severity</th></tr></thead><tbody>${b.events.slice(0,30).map(f=>`<tr><td>${esc(f.kind)}</td><td>${esc(f.scope)} / ${esc(f.target)}</td><td>${f.start_tick}–${f.end_tick-1}</td><td>${f.severity.toFixed(3)}</td></tr>`).join("")}</tbody></table><p class="subtle">First 30 planned events; complete schedule in Save run.</p>`:"No planned background events.";
  }
  $("fault-truth").innerHTML=rows.length?`<table><thead><tr><th>Injected mechanism</th><th>Target</th><th>Ticks</th><th>Known truth</th></tr></thead><tbody>${rows.map(f=>`<tr><td>${esc(f.kind)}</td><td>${esc(f.scope)}: ${esc(f.target??"world")}</td><td>${f.start_tick}–${f.end_tick-1}</td><td>${f.active?"ACTIVE INJECTION":"scheduled / ended"}${f.seed!==undefined?" · seed "+f.seed+" · "+esc(f.recovery):""}</td></tr>`).join("")}</tbody></table>`:"No injected faults in this run.";
}
$("release-select").addEventListener("change",()=>{allocation=null;releaseInfo();connection();});
$("preview-release").addEventListener("click",async()=>{
  allocation=await send("preview",null,{release_id:$("release-select").value,per_rack:Number($("canary-count").value)});
  $("allocation").innerHTML=allocation?`<strong>VALID ALLOCATION</strong><br>${allocation.canaries.length} canaries · ${allocation.controls.length} controls<br>`+allocation.racks.map(r=>`${esc(r.rack_id)}: ${r.canaries.length} candidate / ${r.controls.length} controls`).join("<br>"):"Allocation rejected. Check the backend command outcome.";
  connection();
});
$("deploy-release").addEventListener("click",async()=>{if(allocation)await send("deploy",null,{plan_id:allocation.plan_id});});
$("rollback-release").addEventListener("click",()=>send("rollback",null,{}));
$("register-release").addEventListener("click",async()=>{
  const file=$("artifact-upload").files?.[0];if(!file || file.size>131072){$("command-status").textContent="Choose an artifact of 1–131072 bytes.";return;}
  $("command-status").textContent="Reading unexecuted artifact…";
  try{let binary="";for(const b of new Uint8Array(await file.arrayBuffer()))binary+=String.fromCharCode(b);
    const result=await send("register_release",null,{filename:file.name,content_base64:btoa(binary),profile:$("upload-profile").value});
    if(result){await fetchCatalog();$("release-select").value=result.release_id;releaseInfo();allocation=null;}
  }catch(e){$("command-status").textContent="Upload failed: "+e.message;}
});
$("fault-kind").addEventListener("change",()=>{if($("fault-kind").value==="demand_surge")$("fault-scope").value="world";else if($("fault-kind").value==="network_degradation")$("fault-scope").value="rack";else if($("fault-scope").value==="world")$("fault-scope").value="host";refreshTargets();});
$("fault-scope").addEventListener("change",refreshTargets);
$("schedule-fault").addEventListener("click",async()=>{await send("fault",null,{kind:$("fault-kind").value,scope:$("fault-scope").value,target:$("fault-target").value,duration:Number($("fault-duration").value),severity:Number($("fault-severity").value),seed:Number($("manual-fault-seed").value)});await fetchFaultTruth();});
$("random-faults").addEventListener("click",async()=>{await send("random_faults",null,{seed:Number($("fault-seed").value),count:Number($("fault-count").value)});await fetchFaultTruth();});
$("background-preview").addEventListener("click",()=>fetchFaultTruth().catch(e=>{$("background-summary").textContent=e.message;}));
for(const [id,enabled] of [["background-enable",true],["background-disable",false]])$(id).addEventListener("click",async()=>{await send("background_set_enabled",null,{enabled});await fetchFaultTruth();});
$("monitor-host").addEventListener("change",event=>{selectedHost=event.target.value;render();if(!recorded)fetchState().catch(()=>{disconnected=true;connection();});});
$("save-run").addEventListener("click",async()=>{try{const response=await fetch("/api/run",{cache:"no-store"});if(!response.ok)throw new Error("Save failed");const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement("a");link.href=url;link.download=`world-${packet.run_id}.json`;link.click();URL.revokeObjectURL(url);}catch(e){$("command-status").textContent=e.message;}});
$("load-run").addEventListener("change",async event=>{const file=event.target.files?.[0];if(!file)return;if(file.size>32*1024*1024){$("command-status").textContent="Saved run exceeds 32 MiB.";return;}if(packet?.snapshot.state==="running"){$("command-status").textContent="Pause before replaying a saved run.";return;}try{await send("load_run",null,{run:await file.text()});if(!recorded)await fetchCatalog();}catch(e){$("command-status").textContent="Replay failed: "+e.message;}event.target.value="";});
$("speed").addEventListener("change",event=>send("speed",event.target.value));
setInterval(connection,250);
poll();

async function fetchPublicTelemetry(){
  const response=await fetch("/api/telemetry",{cache:"no-store",signal:AbortSignal.timeout(3000)});
  if(!response.ok)throw new Error("Public minute telemetry unavailable");
  const data=await response.json();if(activeView!=="monitoring")return;
  if(!data.enabled){$("public-window-status").textContent="Public minute telemetry is disabled in this config.";$("public-windows").textContent="";return;}
  const rows=data.windows.filter(r=>r.host_id===selectedHost).slice(-10);
  $("public-window-status").textContent=`${data.summary.closed_minutes} committed minutes · ${data.summary.receiver_counters.late} late records excluded · ${data.summary.receiver_counters.duplicates} duplicate receipts ignored`;
  $("public-windows").innerHTML=rows.length?`<table><thead><tr><th>Minute end</th><th>Service / replica</th><th>Release</th><th>Requests</th><th>Latency mean</th><th>Fresh coverage</th><th>Observed mask</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${r.window_end}s</td><td>${esc(r.service_id)} / ${esc(r.replica_id)}</td><td>${esc(r.release_id??"mixed / missing")}</td><td>${r.request_count}</td><td>${esc(fmt(r.latency_ms," ms"))}</td><td>${esc(fmt(100*r.coverage,"%"))}</td><td>${r.observed?"FRESH":"MASKED"}</td></tr>`).join("")}</tbody></table>`:"Waiting for the first minute deadline.";
}

function buildReleaseManifest(){
  const profiles=[],fields=[["manifest-cpu","extra_cpu_work","work_multiplier",1],["manifest-memory","retained_memory_leak","retained_mb_per_completion",0],["manifest-error","increased_error_probability","error_probability",0],["manifest-delay","slower_response","response_delay_ms",0]];
  for(const [id,kind,key,neutral] of fields){const value=Number($(id).value);if(!Number.isFinite(value))throw Error("Parameters must be finite numbers");if(value!==neutral)profiles.push({kind,[key]:value});}
  if($("manifest-memory-model").value==='process'){
    const index=profiles.findIndex(p=>p.kind==='retained_memory_leak');if(index>=0)profiles.splice(index,1);
    if(profiles.length===1&&profiles[0].kind==='healthy')profiles.length=0;
    profiles.push({kind:'process_memory',retained_mb_per_request:Number($("manifest-process-rate").value),background_mb_per_second:Number($("manifest-background").value),retained_limit_mb:$("manifest-retained-limit").value.trim()===''?null:Number($("manifest-retained-limit").value)});
  }
  return {schema_version:1,release_id:$("manifest-release-id").value.trim(),service_id:$("manifest-service").value,version:$("manifest-version").value.trim(),creation_metadata:{author:$("manifest-author").value.trim(),created_at:new Date().toISOString()},behavior_manifest:{schema_version:1,profiles:profiles.length?profiles:[{kind:"healthy"}]}};
}
$("build-release-manifest").addEventListener("click",()=>{try{$("release-manifest-json").value=JSON.stringify(buildReleaseManifest(),null,2);}catch(e){$("command-status").textContent=e.message;}});
$("release-manifest-upload").addEventListener("change",async event=>{const file=event.target.files?.[0];if(!file)return;try{if(file.size>262144)throw Error("Registration JSON is limited to 256 KiB");$("release-manifest-json").value=JSON.stringify(JSON.parse(await file.text()),null,2);$("command-status").textContent="Manifest loaded for review; not registered or executed.";}catch(e){$("command-status").textContent=e.message;}event.target.value="";});
$("register-manifest").addEventListener("click",async()=>{
  $("manifest-registration-status").textContent="Validating immutable registration…";
  try{
    const release=$("release-manifest-json").value.trim()?JSON.parse($("release-manifest-json").value):buildReleaseManifest(),source=$("manifest-source").files?.[0];
    if(source){if(source.size<1||source.size>131072)throw Error("Source attachment must contain 1–131072 bytes");let binary="";for(const b of new Uint8Array(await source.arrayBuffer()))binary+=String.fromCharCode(b);release.source_attachment={filename:source.name,content_base64:btoa(binary)};}
    const result=await send("register_release",null,{release});
    if(result){await fetchCatalog();$("release-select").value=result.release_id;releaseInfo();allocation=null;$("command-status").textContent="Immutable version registered. Declared behavior is simulated; source was not executed.";$("manifest-registration-status").textContent=`Registered ${result.release_id} / ${result.version} · content SHA-256 ${result.content_hash} · source not executed`;}
    else $("manifest-registration-status").textContent="Registration rejected. "+$("command-status").textContent;
  }catch(e){$("command-status").textContent="Manifest registration failed: "+e.message;$("manifest-registration-status").textContent=$("command-status").textContent;}
});

function currentRollout(){const rs=packet?.snapshot.rollout?.rollouts??[];return rs[rs.length-1];}
function renderRollout(){
  const r=currentRollout();
  const allowed={baseline:['CREATED'],expose:['BASELINING'],pause:['CANARY'],resume:['PAUSED'],promote:['CANARY','PAUSED'],rollback:['CREATED','BASELINING','CANARY','PAUSED','PROMOTED','FAILED']};
  for(const [action,states] of Object.entries(allowed))$("rollout-"+action).disabled=!r||!states.includes(r.state)||!!r.pending_action||packet.read_only||recorded||pending||!!unconfirmed||disconnected||(action==='resume'&&!r.evaluation_active);
  $("rollout-create").disabled=recorded||pending||!!unconfirmed||disconnected||!!packet.read_only||!!r&&!['PROMOTED','ROLLED_BACK'].includes(r.state);
  if(!r){$("rollout-current").textContent="No fixed-cohort rollout.";$("rollout-versions").innerHTML="";$("rollout-log").innerHTML="";return;}
  $("rollout-current").textContent=`${r.state} · ${r.rollout_id} · epoch ${r.monitoring_epoch} · ${r.calibration_status} · ${r.canaries.length} canaries / ${r.controls.length} controls · fixed traffic ${100*r.canary_fraction}% · evaluation ${r.evaluation_active?'active':'inactive'} · exposure tick ${r.exposure_tick??'not exposed'} · first full-window decision ${r.first_decision_time??'—'}s${r.pending_action?' · PENDING '+r.pending_action:''}`;
  $("rollout-versions").innerHTML=`<table><thead><tr><th>Baseline version(s)</th><th>Candidate version</th><th>Canary hosts</th></tr></thead><tbody><tr><td>${r.baseline_releases.map(v=>esc(v.release_id+' · '+v.version)).join('<br>')}</td><td>${esc(r.candidate.release_id+' · '+r.candidate.version)}</td><td>${esc(r.canaries.join(', '))}</td></tr></tbody></table>`;
  $("rollout-log").innerHTML=`<table><thead><tr><th>Sequence</th><th>Tick</th><th>Transition</th><th>Reason</th></tr></thead><tbody>${(packet.snapshot.rollout.transitions??[]).map(t=>`<tr><td>${t.sequence}</td><td>${t.tick}</td><td>${esc((t.from_state??'new')+' → '+t.to_state)}</td><td>${esc(t.reason)}</td></tr>`).join('')}</tbody></table>`;
}
$("rollout-create").onclick=async()=>{try{await send('rollout_create',null,{release_id:$("release-select").value,per_rack:Number($("canary-count").value),canary_fraction:Number($("rollout-fraction").value),baseline_seconds:Number($("rollout-baseline-seconds").value),monitoring_seconds:Number($("rollout-horizon-seconds").value)});}catch(e){$("rollout-current").textContent=e.message;}};
for(const action of ['baseline','expose','pause','resume','promote','rollback'])$("rollout-"+action).onclick=async()=>{try{const r=currentRollout();if(r)await send('rollout_'+action,null,{rollout_id:r.rollout_id});}catch(e){$("rollout-current").textContent=e.message;}};

function renderResourceHealth(){
  const history=historyForHost(),o=history[history.length-1],a=packet.snapshot.resource_health?.advisories.find(x=>x.host_id===selectedHost);
  $("resource-health").textContent=a?`${a.label} · ${a.status} · ${a.policy_id} · headroom ${fmt(a.memory_headroom_mb,' MB')} · retained growth ${fmt(a.growth_mb_per_request,' MB/processed request')} · ${fmt(a.growth_mb_per_second,' MB/s')} · restarts ${a.process_restart_count} · OOMs ${a.oom_count} · ${a.flags.join(', ')}. ${a.interpretation}`:'Insufficient observed resource history. This advisory is separate from the latency detector.';
  drawChart('memory-headroom-chart',history,'memory_mb',{peak:'memory_headroom_mb'});
  drawChart('memory-growth-chart',history,'retained_added_mb_per_request');drawChart('memory-latency-chart',history,'sampled_latency_mean_ms');
  const replicas=(packet.snapshot.resources?.replicas??[]).filter(r=>r.host_id===selectedHost),previous=$("memory-process").value;
  $("memory-process").innerHTML=replicas.map(r=>`<option value="${esc(r.replica_id)}">${esc(r.replica_id)} · ${esc(r.process_state??'RUNNING')} · generation ${r.process_generation??0} · retained ${fmt(r.retained_memory_mb,' MB')}</option>`).join('');
  if(replicas.some(r=>r.replica_id===previous))$("memory-process").value=previous;
  $("restart-process").disabled=!!packet.read_only||recorded||!replicas.length;
  const events=(packet.snapshot.resources?.process_events??[]).filter(e=>e.host_id===selectedHost).slice(-12);
  $("process-events").innerHTML=events.length?`<table><thead><tr><th>Tick</th><th>Process</th><th>Event / reason</th><th>Reclaimed retained MB</th><th>Dropped requests</th></tr></thead><tbody>${events.map(e=>`<tr><td>${e.tick}</td><td>${esc(e.replica_id)}</td><td>${esc(e.kind+' / '+e.reason)}</td><td>${fmt(e.reclaimed_retained_mb,' MB')}</td><td>${e.dropped_requests}</td></tr>`).join('')}</tbody></table>`:'No process exit/restart events recorded.';
}
$("restart-process").onclick=()=>send('restart_process',null,{replica_id:$("memory-process").value});

function renderReleasePolicy(){
  const r=currentRollout(),p=packet.snapshot.release_policy,b=p?.bindings.find(x=>x.rollout_id===r?.rollout_id);
  $("policy-attach").disabled=pending||!!unconfirmed||disconnected||!!packet.read_only||recorded||!r||r.state!=='CREATED'||packet.snapshot.tick!==0||!!r.pending_action||!!b;
  if(!b){$("policy-status").textContent='No compatible calibrated policy attached. Automatic decisions disabled; absence of data never proves health.';$("policy-decisions").innerHTML='';return;}
  $("policy-status").textContent=`${b.active?b.decision.state:'EVALUATION CLOSED (recorded decision: '+b.decision.state+')'} · eligible ${b.decision.eligible_windows??0}/${b.decision.required_eligible_windows??'—'} · auto rollback ${b.auto_rollback?'OPTED IN':'OFF (manual rollback)'} · policy ${b.policy_hash} · hashes ${Object.entries(b.hashes).map(([k,v])=>k+"="+v).join("; ")} · reasons ${b.blocked_reasons.join(', ')||'none'} · validation release false-alert rate ${b.validation_false_alerts.release_alarm.rate} [95% interval ${b.validation_false_alerts.release_alarm.exact_binomial_95_interval.join(", ")}] · combined-action rate ${b.validation_false_alerts.combined_action.rate} [95% interval ${b.validation_false_alerts.combined_action.exact_binomial_95_interval.join(", ")}]`;
  $("policy-decisions").innerHTML=`<table><thead><tr><th>Tick</th><th>Reason</th><th>Action / decision</th></tr></thead><tbody>${(p.decisions??[]).filter(x=>x.rollout_id===r.rollout_id).slice(-15).map(x=>`<tr><td>${x.tick}</td><td>${esc(x.reason)}</td><td>${esc(x.action??x.decision?.state??'recorded')}</td></tr>`).join('')}</tbody></table>`;
}
$("policy-attach").onclick=async()=>{try{const a=$("policy-artifact").files?.[0],v=$("policy-validation").files?.[0],r=currentRollout();if(!a||!v||!r)throw Error('Select a policy, independent validation receipt and current rollout.');if(a.size>16000000||v.size>16000000)throw Error('Each policy file must be <=16 MB');await send('policy_attach',null,{rollout_id:r.rollout_id,policy:JSON.parse(await a.text()),validation:JSON.parse(await v.text()),auto_rollback:!!$("policy-auto-rollback").checked});}catch(e){$("policy-status").textContent=e.message;}};
