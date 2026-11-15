"""Separate update/allocation/simulation/API/real-browser measurements; public data only."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import threading
import time
import tracemalloc
import uuid
from unittest.mock import patch
from urllib.request import Request,urlopen
import numpy as np
from .evaluation_inputs import load_public, world_config
from .evaluation_scoring import adjusted_input, one_method
from .replay_evaluator import table,write,checked_freeze,file_hash
from .kalman import KalmanFilter
from .dashboard import WorldController,make_server
from .seeds import seed_for


def one_http_step(controller,origin,command_id):
    with urlopen(origin+'/api/state',timeout=30) as response:state=json.load(response)
    payload=dict(command_id=command_id,run_id=state['run_id'],epoch=state['epoch'],command='step')
    req=Request(origin+'/api/commands',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','X-World-Token':state['command_token']},method='POST')
    before=controller.engine.tick;start=time.perf_counter_ns()
    with urlopen(req,timeout=30) as response:receipt=json.load(response)
    elapsed=time.perf_counter_ns()-start
    if controller.engine.tick!=before+1:raise AssertionError('No simulation tick: duplicate/held command cannot be a step throughput sample')
    return elapsed


def measure(directory,input_study):
    root=Path(directory);freeze=checked_freeze(root);target=root/'performance';target.mkdir(exist_ok=True)
    updates=[];methods=[]
    for gen in ('research','world'):
        src=Path(input_study)/gen/'inputs/smoke/healthy/harm/public';dst=target/'inputs'/gen;dst.mkdir(parents=True,exist_ok=True);shutil.copyfile(src/'input.npz',dst/'input.npz');p=load_public(gen,dst)
        models=freeze['models'][gen];cache={}
        for name,sd in freeze['settings'][gen].items():
            key=name if name in ('factor_off','ar_off') else 'base'
            if key not in cache:
                t=time.perf_counter_ns();cache[key]=adjusted_input(gen,p,models[key],tuple(str(c) for c in p.class_id) if gen=='research' else None)
                methods.append(dict(generator=gen,method=key,component='public adjustment',elapsed_ns=time.perf_counter_ns()-t))
            data,eligible,classes,racks,adj=cache[key];samples=[];state_bytes=[];original=KalmanFilter.step
            def timed(self,*args,**kwargs):
                t=time.perf_counter_ns();r=original(self,*args,**kwargs);samples.append((time.perf_counter_ns()-t,len(self.m)));state_bytes.append(self.m.nbytes+self.P.nbytes);return r
            def run():return one_method(name,data,eligible,classes,racks,adj,sd,'rack_id' if gen=='world' else 'class_id')
            t=time.perf_counter_ns()
            with patch.object(KalmanFilter,'step',timed):run()
            elapsed=time.perf_counter_ns()-t
            updates.extend(dict(generator=gen,method=name,sample=i,elapsed_ns=ns,state_dimension=d) for i,(ns,d) in enumerate(samples))
            tracemalloc.start();run();_,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
            methods.append(dict(generator=gen,method=name,component='method replay',elapsed_ns=elapsed,input_minutes=len(data.times),amortized_ns_per_input_minute=elapsed/len(data.times),actual_update_samples=len(samples),step_p50_ns=float(np.median([x[0] for x in samples])) if samples else None,step_p95_ns=float(np.quantile([x[0] for x in samples],.95)) if samples else None,tracked_allocation_peak_bytes=peak,max_state_bytes=max(state_bytes) if state_bytes else None,public_input_sha256=file_hash(dst/'input.npz'),scope='whole replay and actual Kalman step samples; separate traced Python/NumPy allocations, not RSS'))
    table(target/'update_samples.csv',updates);table(target/'method_runtime_memory.csv',methods)
    c=WorldController(world_config(seed_for('world_smoke',0,46),'healthy'),state_dir=target/'backend_runtime'/uuid.uuid4().hex);server=make_server(c,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();origin='http://127.0.0.1:'+str(server.server_port);rows=[];browser={}
    def get(path):
        with urlopen(origin+path,timeout=30) as r:return json.load(r)
    try:
        for i in range(100):
            t=time.perf_counter_ns();c.engine.step();rows.append(dict(component='simulation_tick',sample=i,elapsed_ns=time.perf_counter_ns()-t,scope='full engine including telemetry and snapshot; no HTTP or UI'))
        tick=c.engine.tick
        for i in range(50):
            t=time.perf_counter_ns();get('/api/state');rows.append(dict(component='api_snapshot_get',sample=i,elapsed_ns=time.perf_counter_ns()-t,scope='HTTP and JSON snapshot; no simulation step'))
        assert c.engine.tick==tick
        for i in range(20):
            elapsed=one_http_step(c,origin,'performance-'+str(i))
            rows.append(dict(component='simulation_api_step',sample=i,elapsed_ns=elapsed,scope='verified one engine tick plus HTTP validation/journal/checkpoint; no browser'))
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                chrome=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage']);page=chrome.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(origin,wait_until='networkidle');page.wait_for_function('typeof packet !== "undefined" && packet !== null');initial=page.evaluate('packet.run_id')
                # Actual browser events, layout, network and paint scheduling.
                for i in range(20):
                    name=('world','rollout','host','monitoring')[i%4];t=time.perf_counter_ns()
                    page.evaluate('(v)=>selectView(v)',name);page.evaluate('()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
                    rows.append(dict(component='browser_view_with_layout_paint',sample=i,elapsed_ns=time.perf_counter_ns()-t,scope='real Chromium view switch and two animation frames; includes driver overhead'))
                for i in range(10):
                    t=time.perf_counter_ns();page.evaluate('()=>send("step")');page.evaluate('()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
                    rows.append(dict(component='simulation_api_browser_step',sample=i,elapsed_ns=time.perf_counter_ns()-t,scope='real app command, HTTP engine/checkpoint, DOM and paint opportunity; driver overhead included'))
                page.reload(wait_until='networkidle');page.wait_for_function('typeof packet !== "undefined" && packet !== null');same=page.evaluate('packet.run_id')==initial
                overflow=page.evaluate('document.documentElement.scrollWidth>innerWidth');browser=dict(status='MEASURED',engine='Chromium',same_run_after_refresh=same,page_errors=errors,horizontal_overflow=overflow,scope='1440x1000 headless local browser, diagnostic concurrent-load measurement')
                page.screenshot(path='/tmp/evaluator_dashboard_qa.png',full_page=True);chrome.close()
                if errors or not same:raise AssertionError('Browser integration regression')
        except Exception as e:
            browser=dict(status='UNVERIFIED',error=repr(e),scope='Browser launch/run failed; API throughput is not browser throughput')
        write(target/'browser_checks.json',browser)
        result=subprocess.run(['node',str(Path(__file__).resolve().parents[1]/'scripts/benchmark_console.mjs'),origin,str(target/'renderer_samples.csv')],capture_output=True,text=True,timeout=120)
        write(target/'renderer_harness.json',dict(returncode=result.returncode,stdout=result.stdout,stderr=result.stderr,browser_layout_paint_measured=False))
        if result.returncode:raise RuntimeError('Renderer harness failed: '+result.stderr)
    finally:server.shutdown();server.server_close();c.close();thread.join()
    table(target/'throughput_samples.csv',rows);summary=[]
    for component in sorted({r['component'] for r in rows}):
        rr=[r for r in rows if r['component']==component];total=sum(r['elapsed_ns'] for r in rr)
        summary.append(dict(component=component,samples=len(rr),wall_seconds=total/1e9,operations_per_second=len(rr)/(total/1e9),scope=rr[0]['scope']))
    table(target/'throughput_summary.csv',summary)
    write(target/'environment.json',dict(python=platform.python_version(),numpy=np.__version__,platform=platform.platform(),freeze_hash=freeze['freeze_hash'],OPENBLAS_NUM_THREADS=os.getenv('OPENBLAS_NUM_THREADS'),OMP_NUM_THREADS=os.getenv('OMP_NUM_THREADS'),concurrent_audit=True,limitations='diagnostic wall timings under concurrent audit; traced allocations not process RSS; browser round trips include driver overhead'))
    return dict(update_samples=len(updates),method_rows=len(methods),throughput_samples=len(rows),browser=browser)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',default='examples/evaluator_v2');p.add_argument('--inputs',required=True);a=p.parse_args();print(json.dumps(measure(a.study,a.inputs),indent=2))
