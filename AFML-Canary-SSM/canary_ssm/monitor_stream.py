"""Example external producer: stream saved posterior frames to the local dashboard."""
import argparse
import json
import time
import uuid
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlsplit


def stream(artifact,url,start=0,stop=None,interval=.2):
    parsed=urlsplit(url)
    if parsed.scheme!='http' or parsed.hostname not in ('localhost','127.0.0.1') or parsed.path not in ('','/'):
        raise ValueError('Use the local dashboard origin')
    frames=artifact['frames'];stop=len(frames) if stop is None else stop
    if not 0<=start<stop<=len(frames) or not 0<=interval<=5:raise ValueError('Invalid bounded frame range or interval')
    def command(name,args):
        with urlopen(url+'/api/state',timeout=10) as r:state=json.load(r)
        payload={'command_id':str(uuid.uuid4()),'run_id':state['run_id'],'epoch':state['epoch'],'command':name,'args':args}
        request=Request(url+'/api/commands',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','X-World-Token':state['command_token']},method='POST')
        with urlopen(request,timeout=30) as r:return json.load(r)
    metadata={k:v for k,v in artifact.items() if k not in ('frames','artifact_sha256')}
    metadata['source_kind']='external-detector-stream'
    command('monitor_begin',{'metadata':metadata})
    for index in range(start,stop):
        command('monitor_append',{'frame':frames[index]})
        if interval and index+1<stop:time.sleep(interval)
    return {'frames_sent':stop-start,'source':'saved detector outputs streamed by external producer','run_id':metadata['run_id']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--artifact',required=True)
    p.add_argument('--url',default='http://127.0.0.1:8765');p.add_argument('--start',type=int,default=80)
    p.add_argument('--stop',type=int);p.add_argument('--interval',type=float,default=.2);a=p.parse_args()
    print(json.dumps(stream(json.loads(Path(a.artifact).read_text()),a.url,a.start,a.stop,a.interval)))
