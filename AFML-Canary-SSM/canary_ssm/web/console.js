/* Console composition only. All world state, allocation, evidence and history are backend data. */
let rolloutPlan=null,historyRows=[],recoveringCommand=false;
const pendingKey='world-lab-pending-v1';
function rememberCommand(payload){
  try{const raw=JSON.stringify(payload);sessionStorage.setItem(pendingKey,raw.length<200000?raw:JSON.stringify({command_id:payload.command_id,run_id:payload.run_id,epoch:payload.epoch,command:payload.command,payload_unavailable:true}));}catch{}
}
function forgetCommand(){try{sessionStorage.removeItem(pendingKey);}catch{}$("retry-command").hidden=true;}
function rememberView(name){try{sessionStorage.setItem('world-lab-view',name);if(location.hash!=='#'+name)location.hash=name;}catch{}}
async function recoverUnconfirmed(){
  if(pending||recoveringCommand||recorded||!packet)return;
  if(!unconfirmed){try{unconfirmed=JSON.parse(sessionStorage.getItem(pendingKey)||'null');}catch{}}
  if(!unconfirmed)return;
  recoveringCommand=true;
  const command=unconfirmed;
  try{
    if(command.run_id!==packet.run_id||command.epoch!==packet.epoch){$("command-status").textContent=`UNCONFIRMED prior run/epoch · ${command.command_id}. It will not be resubmitted to this run.`;return;}
    const response=await fetch('/api/commands?command_id='+encodeURIComponent(command.command_id),{cache:'no-store',signal:AbortSignal.timeout(5000)});
    if(!response.ok)throw Error('Receipt lookup unavailable');
    const result=await response.json();
    if(result.known){$("command-status").textContent=`${result.receipt?'SUCCESS':'ERROR'} recovered ${command.command} · ${command.command_id}${result.outcome?.error?' · '+result.outcome.error:''}`;unconfirmed=null;forgetCommand();}
    else $("command-status").textContent=`UNCONFIRMED ${command.command} · ${command.command_id}. ${command.payload_unavailable?'Choose the original large upload again after acknowledging this unknown outcome.':'Retry the same command ID to avoid duplicate execution.'}`;
  }catch{$("command-status").textContent=`UNCONFIRMED · ${command.command_id} · waiting for backend receipt`;
  }finally{recoveringCommand=false;connection();renderDashboard();}
}
$("retry-command").onclick=()=>{if(unconfirmed&&!unconfirmed.payload_unavailable)return send(unconfirmed.command,null,null,unconfirmed);};
$("dismiss-command").onclick=()=>{if(unconfirmed){$("command-status").textContent=`UNKNOWN OUTCOME acknowledged · ${unconfirmed.command_id}. Inspect backend history before issuing another command.`;unconfirmed=null;forgetCommand();connection();renderDashboard();}};

function replicaTable(rows){
  return rows?.length?`<table><thead><tr><th>Host / replica</th><th>Service</th><th>Active release / version</th><th>Routing</th><th>Nominal share</th><th>Requests last tick</th><th>Process</th></tr></thead><tbody>${rows.map(r=>`<tr><td><button data-host="${esc(r.host_id)}">${esc(r.host_id)}</button><br><small>${esc(r.replica_id)}</small></td><td>${esc(r.service_id)}</td><td>${esc(r.release_id)}<br>${esc(r.version??'—')}</td><td>${esc(r.role)}</td><td>${finite(r.nominal_traffic_fraction)?fmt(100*r.nominal_traffic_fraction,'%'):'—'}</td><td>${esc(r.routed_requests_last_tick??'—')}</td><td>${esc(r.process_state??'—')}</td></tr>`).join('')}</tbody></table>`:'<p class="empty">No backend replica allocation is available in this snapshot.</p>';
}
function renderDashboard(){
  if(!packet)return;
  const evidence=packet.console,context=evidence?.context;
  $("context-mode").textContent=packet.read_only?'READ-ONLY SAVED SIMULATION':recorded?'RECORDED SNAPSHOT':context?.simulation_mode??'SIMULATION';
  $("context-seed").textContent=context?.seed??'Not included';
  for(const [id,value] of [['context-model',context?.model_id??'DETECTOR NOT CONNECTED'],['context-policy',context?.policy_id??'None attached']]){$(id).textContent=value;$(id).title=value;}
  $("context-calibration").textContent=context?.calibration_status??'UNVERIFIED RECORDING';
  if($("latest-command-id").textContent==='—'&&packet.outcomes?.length)$("latest-command-id").textContent=packet.outcomes.at(-1).command_id;
  $("decision-reason").textContent='Decision reason · '+(context?.decision_reason??'No connected inference evidence');
  $("world-replicas").innerHTML=replicaTable(evidence?.replicas);
  $("host-replica-allocation").innerHTML=replicaTable(evidence?.replicas.filter(r=>r.host_id===selectedHost));
  $("detail-host-select").innerHTML=packet.snapshot.world.hosts.map(h=>`<option value="${esc(h.host_id)}">${esc(h.host_id)} · ${esc(h.rack_id)}</option>`).join('');
  $("detail-host-select").value=selectedHost;
  const timeline=evidence?.timeline??[];
  const table=timeline.length?`<table><thead><tr><th>Tick</th><th>Source / sequence</th><th>Event / decision reason</th><th>Command ID / epoch</th></tr></thead><tbody>${[...timeline].reverse().map(e=>`<tr><td>${e.tick}</td><td>${esc(e.kind)} / ${e.sequence}</td><td>${esc(e.command??e.state??e.action??'Policy observation')}<br>${esc(e.reason)}</td><td><code>${esc(e.command_id??e.rollout_id??'—')}</code></td></tr>`).join('')}</tbody></table>`:'No backend events yet.';
  $("event-timeline").innerHTML=table;$("rollout-timeline").innerHTML=table;
  $("rollout-release-select").innerHTML=releaseCatalog.map(r=>`<option value="${esc(r.release_id)}">${esc(r.release_id)} · ${esc(r.version)}</option>`).join('');
  $("rollout-release-select").value=$("release-select").value;
  $("rollout-selection-info").textContent='Selected candidate: '+($("release-select").value||'Register or select a release first')+' · manifest behavior is simulated; uploaded source is not executed.';
  $("registry-list").innerHTML=releaseCatalog.length?`<table><thead><tr><th>Release / service</th><th>Version</th><th>Immutable content hash</th><th>Mode</th></tr></thead><tbody>${releaseCatalog.map(r=>`<tr><td>${esc(r.release_id)}<br>${esc(r.service_id)}</td><td>${esc(r.version)}</td><td><code>${esc(r.content_hash)}</code></td><td>Declared simulation · source unexecuted</td></tr>`).join('')}</tbody></table>`:'Loading backend release registry…';
  const r=currentRollout(),planned=rolloutPlan;
  if(planned&&planned.release_id!==$("release-select").value)rolloutPlan=null;
  $("retry-command").hidden=!unconfirmed||!!unconfirmed.payload_unavailable||unconfirmed.run_id!==packet.run_id||unconfirmed.epoch!==packet.epoch;
  $("dismiss-command").hidden=!unconfirmed;
  const blocked=pending||!!unconfirmed||disconnected||recorded||!packet.console_available||!!packet.read_only;
  $("rollout-preview").disabled=blocked||!!r&&!['ROLLED_BACK','PROMOTED'].includes(r.state);
  $("history-save").disabled=pending||!!unconfirmed||disconnected||recorded;
  $("history-refresh").disabled=disconnected||recorded;
  for(const id of ['world','host','faults','releases','rollout','monitoring','history'])$("nav-"+id).setAttribute?.('aria-current',activeView===id?'page':'false');
  // Resource colors remain observed CPU/memory/availability; labels are cohort membership only.
  const roles=new Map((evidence?.replicas??[]).map(x=>[x.host_id,x.role]));
  if(typeof document.querySelectorAll==='function')for(const tile of document.querySelectorAll('.host-tile')){
    const role=roles.get(tile.dataset.host)??'balanced';tile.dataset.cohort=role;
    if(!tile.querySelector('.cohort-badge')){const tag=document.createElement('span');tag.className='cohort-badge';tile.appendChild(tag);}
    tile.querySelector('.cohort-badge').textContent=role;
  }
}
$("rollout-release-select").onchange=event=>{$("release-select").value=event.target.value;rolloutPlan=null;releaseInfo();renderDashboard();};
$("detail-host-select").onchange=async event=>{selectedHost=event.target.value;try{if(!recorded)await fetchState();else render();}catch{disconnected=true;connection();}};
function rolloutArguments(){return {release_id:$("release-select").value,per_rack:Number($("canary-count").value),canary_fraction:Number($("rollout-fraction").value),baseline_seconds:Number($("rollout-baseline-seconds").value),monitoring_seconds:Number($("rollout-horizon-seconds").value)};}
$("rollout-preview").onclick=async()=>{
  rolloutPlan=await send('rollout_preview',null,rolloutArguments());
  $("rollout-allocation").innerHTML=rolloutPlan?`<strong>BACKEND-VALIDATED COHORT</strong><br>Canaries: ${esc(rolloutPlan.canaries.join(', '))}<br>Controls: ${esc(rolloutPlan.controls.join(', '))}<br>Traffic: ${fmt(100*rolloutPlan.canary_fraction,'%')} candidate · cohort ${esc(rolloutPlan.cohort_sha256)}<br>Creation revalidates current availability; inspect the frozen cohort after creating it.`:'Allocation rejected. See the full command ID and error above.';
};
for(const id of ['canary-count','rollout-fraction','rollout-baseline-seconds','rollout-horizon-seconds'])$(id).addEventListener('change',()=>{rolloutPlan=null;$("rollout-allocation").textContent='Selection changed. Preview the new backend allocation.';});

async function fetchRunHistory(){
  if(recorded)return;
  try{
    const response=await fetch('/api/history',{cache:'no-store',signal:AbortSignal.timeout(10000)});
    if(!response.ok)throw Error('Backend history unavailable');
    const data=await response.json();historyRows=data.checkpoints;
    $("history-status").textContent=data.persistent?'Backend checkpoints persist across refresh and server restart.':'Backend checkpoints survive UI refresh; use --state-dir to persist across server restarts.';
    $("history-list").innerHTML=historyRows.length?`<table><thead><tr><th>Run / checkpoint</th><th>Seed / epoch</th><th>Simulated clock</th><th>Backend state</th><th>Replay / export</th></tr></thead><tbody>${historyRows.map(r=>`<tr><td>${esc(r.run_id)}<br><code>${r.checkpoint_id}</code></td><td>${r.seed} / ${r.epoch}</td><td>${simulatedTime(r.simulated_seconds)} · tick ${r.tick}</td><td>${esc(r.state)} · ${r.command_outcomes} command outcomes</td><td><button data-history-load="${r.checkpoint_id}" ${pending||unconfirmed||packet?.snapshot.state==='running'?'disabled':''}>Load read-only replay</button><a href="/api/history?checkpoint_id=${r.checkpoint_id}" download="world-${r.checkpoint_id.slice(0,12)}.json">Export backend JSON</a></td></tr>`).join('')}</tbody></table>`:'No checkpoints saved yet. Save the current backend run; reset also checkpoints it.';
  }catch(e){$("history-status").textContent=e.message+' · retry after reconnect';}
}
$("history-save").onclick=async()=>{await send('history_save',null,{});await fetchRunHistory();};
$("history-refresh").onclick=fetchRunHistory;
document.addEventListener('click',async event=>{const button=event.target.closest('[data-history-load]');if(button&&!button.disabled){await send('history_load',null,{checkpoint_id:button.dataset.historyLoad});await fetchRunHistory();}});
try{selectView(String(location.hash??'').replace(/^#/,'')||sessionStorage.getItem('world-lab-view')||'world');}catch{}
if(packet)renderDashboard();
