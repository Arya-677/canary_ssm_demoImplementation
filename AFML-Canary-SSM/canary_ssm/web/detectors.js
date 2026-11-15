/* Read-only chart polling. World simulation, playback cursors and posteriors stay in Python. */
(() => {
  'use strict';
  const el=id=>document.getElementById(id),good=x=>typeof x==='number'&&Number.isFinite(x);
  const escape=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const number=x=>good(x)?x.toLocaleString(undefined,{maximumFractionDigits:4}):'—';
  let feed=null,host=null,lastContact=0,busy=false,request=0,applied=0,error=null,commandError=null;
  const colors={independent:'#5f6d80',weak:'#b57c32',strong:'#087f83'};
  function status(){
    if(!feed?.connected){el('detector-status').textContent='DETECTOR NOT CONNECTED';el('detector-status').className='detector-banner';return;}
    const disconnected=error||Date.now()-lastContact>4500;
    const labels={observations_available:'OBSERVATIONS AVAILABLE',insufficient_data:'INSUFFICIENT DATA',stale_stream:'STALE STREAM',pre_exposure:'PRE-EXPOSURE',waiting_for_frames:'WAITING FOR FRAMES'};
    el('detector-status').textContent=(disconnected?'DISCONNECTED · LAST RECEIVED OUTPUT':labels[feed.status]??feed.status)+' · UNCALIBRATED';
    el('detector-status').className='detector-banner '+(disconnected?'detector-status-disconnected':feed.status==='stale_stream'?'detector-status-stale':feed.status==='insufficient_data'?'detector-status-insufficient':'');
    el('detector-message').textContent=commandError??(error?error+' · retrying connection':feed.mode==='recorded'?'Saved recording · backend owns playback · simulated metrics':'External detector output stream · last receipt '+number(feed.receipt_age_seconds)+'s ago');
  }
  function chart(id,rows,series,band=false,riskAxis=false){
    const node=el(id),values=rows.flatMap(r=>series.flatMap(s=>[s.value(r),band?r.methods?.[el('detector-setting').value]?.lower:null,band?r.methods?.[el('detector-setting').value]?.upper:null])).filter(good);
    if(!values.length){node.innerHTML='<p class="empty">No posterior / fresh observations in this prefix</p>';return;}
    let lo=riskAxis?0:Math.min(0,...values),hi=riskAxis?1:Math.max(0,...values);if(hi===lo)hi=lo+1;
    const margin=(hi-lo)*.08;if(!riskAxis){lo-=margin;hi+=margin;}
    const first=rows[0].event_time,last=rows.at(-1).event_time;
    const x=t=>48+322*(t-first)/Math.max(60,last-first),y=v=>138-112*(v-lo)/(hi-lo);
    function path(fn){let live=false;return rows.map(r=>{const v=fn(r);if(!good(v)){live=false;return '';}const p=(live?'L':'M')+x(r.event_time).toFixed(2)+','+y(v).toFixed(2);live=true;return p;}).join(' ');}
    let area='';
    if(band){const key=el('detector-setting').value;let segment=[];
      function flush(){if(segment.length){const upper=segment.map(r=>`${x(r.event_time)},${y(r.methods[key].upper)}`),lower=segment.slice().reverse().map(r=>`${x(r.event_time)},${y(r.methods[key].lower)}`);area+=`<polygon points="${upper.concat(lower).join(' ')}" fill="#087f83" opacity=".13"/>`;segment=[];}}
      for(const r of rows){if(good(r.methods?.[key]?.upper)&&good(r.methods?.[key]?.lower))segment.push(r);else flush();}flush();}
    node.innerHTML=`<svg viewBox="0 0 390 170" role="img" aria-label="${escape(id)} over simulated event time"><title>${escape(id)} · backend posterior/telemetry</title><line x1="48" x2="370" y1="${y(0)}" y2="${y(0)}" stroke="#cad7db"/><text x="1" y="27" class="axis-label">${escape(number(hi))}</text><text x="1" y="140" class="axis-label">${escape(number(lo))}</text>${area}${series.map(s=>`<path d="${path(s.value)}" fill="none" stroke="${s.color}" stroke-width="1.8"/>`).join('')}<text x="48" y="163" class="axis-label">${first}s</text><text x="370" y="163" text-anchor="end" class="axis-label">${last}s</text></svg>`;
  }
  function render(){
    if(!feed)return;status();
    const prior=el('detector-sample').value;
    el('detector-sample').innerHTML=feed.catalog.map(s=>`<option value="${escape(s.sample_id)}">${escape(s.label)}</option>`).join('');
    if(feed.catalog.some(s=>s.sample_id===prior))el('detector-sample').value=prior;
    for(const id of ['detector-play','detector-pause','detector-seek','detector-speed'])el(id).disabled=busy||!feed.connected||feed.mode!=='recorded';
    el('detector-export').disabled=!feed.connected;
    if(!feed.connected){for(const id of ['detector-raw','detector-residual','detector-effect','detector-risk','detector-group','detector-deviation'])el(id).innerHTML='<p class="empty">No detector feed</p>';el('detector-meta').textContent='No detector feed. Current-world inference is not connected.';el('detector-risk-summary').textContent='No posterior yet.';el('detector-host').innerHTML='';return;}
    const m=feed.metadata,rows=feed.rows;
    const choices=m.methods.filter(v=>v.kind==='hierarchical'),available=choices.length?choices:m.methods,previousSetting=el('detector-setting').value;
    el('detector-setting').innerHTML=available.map(v=>`<option value="${escape(v.method_id)}">${escape(v.method_id==='strong'?'Stronger pooling':v.method_id==='weak'?'Weaker pooling':v.method_id)} · ${escape(v.version)}</option>`).join('');
    el('detector-setting').value=available.some(v=>v.method_id===previousSetting)?previousSetting:available[0].method_id;
    const key=el('detector-setting').value;
    m.methods.forEach((v,i)=>{if(!colors[v.method_id])colors[v.method_id]=['#5f6d80','#b57c32','#087f83','#8066a5'][i%4];});
    el('detector-legend').innerHTML=m.methods.map(v=>`<span>${escape(v.method_id)} · ${escape(v.version)}</span>`).join('')+'<span>Band: selected setting marginal 95% interval</span>';
    el('detector-host').innerHTML=m.host_roster.map(h=>`<option value="${escape(h.host_id)}">${escape(h.host_id)} · ${escape(h.rack_id)}</option>`).join('');el('detector-host').value=feed.host_id;
    el('detector-seek').max=Math.max(0,feed.frame_count-1);el('detector-seek').value=Math.max(0,feed.cursor);el('detector-speed').value=String(feed.speed);
    el('detector-meta').innerHTML=`<strong>${escape(m.source_kind)} · simulated</strong><br>Detector run <code>${escape(m.run_id)}</code> · replay <code>${escape(m.replay_id)}</code><br>Artifact ${escape(m.artifact_id)} / ${escape(m.version)} · frame ${feed.cursor+1}/${feed.frame_count}<br>Event time ${number(rows.at(-1)?.event_time)}s · received by decision ${number(rows.at(-1)?.decision_time)}s<br>World controls and detector replay are separate clocks. Same observation prefix for every method · SHA-256 <code>${escape(m.artifact_sha256)}</code><br>`+m.methods.map(v=>`${escape(v.method_id)}: ${escape(v.version)} · ${escape(JSON.stringify(v.settings))}`).join('<br>');
    const lines=field=>m.methods.map(v=>v.method_id).map(id=>({value:r=>r.methods[id]?.[field],color:colors[id]}));
    chart('detector-raw',rows,[{value:r=>r.observed?r.latency_ms:null,color:'#087f83'}]);
    chart('detector-residual',rows,[{value:r=>r.observed?r.residual:null,color:'#087f83'}]);
    chart('detector-effect',rows,lines('mean'),true);chart('detector-risk',rows,lines('risk'),false,true);
    chart('detector-group',rows,[{value:r=>r.methods[key]?.group,color:colors[key]}]);
    chart('detector-deviation',rows,[{value:r=>r.methods[key]?.deviation,color:colors[key]}]);
    const current=rows.at(-1),p=current?.methods[key];
    el('detector-risk-summary').innerHTML=`<strong>UNCALIBRATED · ${escape(key)} · conditional posterior</strong><br>Host risk P(effect &gt; log(1.02)): ${number(p?.risk)}<br>Marginal 95% interval: [${number(p?.lower)}, ${number(p?.upper)}]<br>Release score (maximum host risk): ${number(p?.release_score)} · not a joint release probability<br>Observed mask: ${current?.observed?'fresh observed':'masked / missing'} · decision input ${current?.eligible?'eligible':'insufficient or pre-exposure'}<br>${escape((current?.quality_flags??[]).join(' · '))}`;
  }
  async function refresh(){
    const sequence=++request;
    try{const response=await fetch('/api/detectors'+(host?'?host_id='+encodeURIComponent(host):''),{cache:'no-store',signal:AbortSignal.timeout(3000)});
      if(!response.ok){if(response.status===404&&host){host=null;return refresh();}throw Error('Detector output unavailable ('+response.status+')');}const next=await response.json();
      if(sequence<applied)return;applied=sequence;feed=next;host=next.host_id??null;lastContact=Date.now();error=null;render();
    }catch(e){error=e.message;status();}
  }
  async function command(command,args={}){
    if(busy)return;busy=true;commandError=null;el('detector-message').textContent='Applying '+command+'…';
    try{const state=await (await fetch('/api/state',{cache:'no-store'})).json();
      const response=await fetch('/api/commands',{method:'POST',headers:{'Content-Type':'application/json','X-World-Token':state.command_token},body:JSON.stringify({command_id:crypto.randomUUID(),run_id:state.run_id,epoch:state.epoch,command,args}),signal:AbortSignal.timeout(15000)});
      const result=await response.json();if(!response.ok)throw Error(result.error??'Detector command rejected');if(command==='monitor_load'||command==='monitor_begin')host=null;await refresh();
    }catch(e){commandError='Command failed: '+e.message;el('detector-message').textContent=commandError;}finally{busy=false;render();}
  }
  el('detector-load').addEventListener('click',()=>command('monitor_load',{sample_id:el('detector-sample').value}));
  el('detector-play').addEventListener('click',()=>command('monitor_play'));
  el('detector-pause').addEventListener('click',()=>command('monitor_pause'));
  el('detector-speed').addEventListener('change',()=>command('monitor_speed',{speed:Number(el('detector-speed').value)}));
  el('detector-seek').addEventListener('change',()=>command('monitor_seek',{index:Number(el('detector-seek').value)}));
  el('detector-host').addEventListener('change',()=>{host=el('detector-host').value;return refresh();});
  el('detector-setting').addEventListener('change',render);
  el('detector-upload').addEventListener('change',async event=>{const f=event.target.files?.[0];if(!f)return;if(f.size>8*1024*1024){el('detector-message').textContent='Detector artifact exceeds 8 MiB';return;}try{await command('monitor_load',{artifact:JSON.parse(await f.text())});}catch(e){el('detector-message').textContent=e.message;}event.target.value='';});
  el('detector-export').addEventListener('click',async()=>{try{const response=await fetch('/api/detectors/export');if(!response.ok)throw Error('No detector artifact');const blob=await response.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='detector-'+feed.metadata.artifact_id+'.json';a.click();URL.revokeObjectURL(url);}catch(e){el('detector-message').textContent=e.message;}});
  el('detector-recipe-load').addEventListener('click',async()=>{try{const r=await fetch('/api/detectors/evaluator?developer=1');if(!r.ok)throw Error('No selected authored demo recipe');el('detector-recipe').textContent='EVALUATOR / DEMO TRUTH ONLY\n'+JSON.stringify(await r.json(),null,2);}catch(e){el('detector-recipe').textContent=e.message;}});
  async function poll(){if(!el('view-monitoring').hidden||!feed)await refresh();setTimeout(poll,750);}setInterval(status,500);poll();
})();
