"""Append-only declared-behavior release registry. Attachments are inert bytes."""
import base64
import copy
import hashlib
import json
import math
import re
from dataclasses import asdict,dataclass
from datetime import datetime

from .telemetry import identifier


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class Behavior:
    work_multiplier: float=1.
    retained_mb_per_completion: float=0.
    error_probability: float=0.
    response_delay_ms: float=0.
    memory_model: str='legacy-bounded-v1'
    retained_mb_per_request: float=0.
    background_mb_per_second: float=0.
    retained_limit_mb: float|None=None


PARAMETERS={'extra_cpu_work':('work_multiplier',1.,16.),
    'retained_memory_leak':('retained_mb_per_completion',0.,64.),
    'increased_error_probability':('error_probability',0.,1.),
    'slower_response':('response_delay_ms',0.,300000.)}


def behavior_manifest(value):
    if not isinstance(value,dict) or set(value)!={'schema_version','profiles'} or type(value['schema_version']) is not int or value['schema_version']!=1:
        raise ValueError('Behavior manifest requires schema_version 1 and profiles')
    profiles=value['profiles']
    if not isinstance(profiles,list) or not 1<=len(profiles)<=4:raise ValueError('Use 1–4 unique behavior profiles')
    seen=set();normalized=[];parameters={}
    for profile in profiles:
        if not isinstance(profile,dict):raise ValueError('Each profile is an object')
        kind=profile.get('kind')
        if not isinstance(kind,str) or kind in seen:raise ValueError('Duplicate or invalid behavior kind')
        seen.add(kind)
        if kind=='healthy':
            if len(profiles)!=1 or set(profile)!={'kind'}:raise ValueError('Healthy must be the sole profile')
            normalized.append({'kind':'healthy'});continue
        if kind=='process_memory':
            if not {'kind','retained_mb_per_request'}<=profile.keys() or profile.keys()-{'kind','retained_mb_per_request','background_mb_per_second','retained_limit_mb'}:
                raise ValueError('process_memory requires retained_mb_per_request and optional background_mb_per_second/retained_limit_mb')
            values={'retained_mb_per_request':profile['retained_mb_per_request'],'background_mb_per_second':profile.get('background_mb_per_second',0.),'retained_limit_mb':profile.get('retained_limit_mb')}
            for key,v in values.items():
                if key=='retained_limit_mb' and v is None:continue
                high=1e9 if key=='retained_limit_mb' else 64.
                if type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=high:raise ValueError(f'{key} must be finite in [0,{high}]')
                values[key]=float(v)
            parameters.update(values,memory_model='process-memory-v1')
            normalized.append({'kind':kind,**values});continue
        if kind not in PARAMETERS:raise ValueError('Unknown behavior kind')
        key,low,high=PARAMETERS[kind]
        if set(profile)!={'kind',key}:raise ValueError('Unexpected or missing behavior parameter')
        v=profile[key]
        if type(v) not in (int,float) or not math.isfinite(v) or not low<=v<=high:raise ValueError(f'{key} must be finite in [{low}, {high}]')
        parameters[key]=float(v);normalized.append({'kind':kind,key:float(v)})
    if {'process_memory','retained_memory_leak'}<=seen:raise ValueError('Use one memory model per release')
    return {'schema_version':1,'profiles':sorted(normalized,key=lambda p:p['kind'])},Behavior(**parameters)


@dataclass(frozen=True)
class Creation:
    author: str
    created_tick: int
    created_at: str|None=None
    description: str=''


@dataclass(frozen=True)
class Attachment:
    filename: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class Release:
    release_id: str
    service_id: str
    version: str
    content_hash: str
    creation: Creation
    manifest_json: str
    behavior: Behavior
    attachment: Attachment|None=None
    schema_version: int=1

    def to_dict(self):
        return {'schema_version':1,'release_id':self.release_id,'service_id':self.service_id,'version':self.version,
            'content_hash':self.content_hash,'creation_metadata':asdict(self.creation),
            'behavior_manifest':json.loads(self.manifest_json),'source_attachment':asdict(self.attachment) if self.attachment else None,
            'executed':False,'mode':'declared-behavior-simulation'}

    def public_metadata(self):
        return {k:getattr(self,k) for k in ('release_id','service_id','version','content_hash')}


class ReleaseRegistry:
    def __init__(self,service_ids):
        self.service_ids=frozenset(service_ids);self._records={};self._sources={}

    def get(self,release_id):
        if release_id not in self._records:raise ValueError('Unknown release_id')
        return self._records[release_id]

    def records(self):return tuple(self._records.values())

    def source_attachments(self):return dict(self._sources)

    def register(self,payload,created_tick):
        required={'schema_version','release_id','service_id','version','creation_metadata','behavior_manifest'}
        if not isinstance(payload,dict) or not required<=payload.keys() or payload.keys()-(required|{'content_hash','source_attachment'}):raise ValueError('Invalid release registration fields')
        if type(payload['schema_version']) is not int or payload['schema_version']!=1:raise ValueError('Release schema_version must be 1')
        rid,sid,version=payload['release_id'],payload['service_id'],payload['version']
        identifier(rid,'release_id');identifier(sid,'service_id')
        if sid not in self.service_ids:raise ValueError('Unknown service_id')
        if not isinstance(version,str) or len(version)>100 or not re.fullmatch(r'\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?',version):raise ValueError('Use a numeric semantic version, optionally with prerelease suffix')
        meta=payload['creation_metadata']
        if not isinstance(meta,dict) or not {'author'}<=meta.keys() or meta.keys()-{'author','created_at','description'}:raise ValueError('Creation metadata requires author; created_tick is backend owned')
        if not isinstance(meta['author'],str) or not meta['author'].strip() or len(meta['author'])>100:raise ValueError('Author must contain 1–100 characters')
        description=meta.get('description','');stamp=meta.get('created_at')
        if not isinstance(description,str) or len(description)>500:raise ValueError('Description must be <=500 characters')
        if stamp is not None:
            if not isinstance(stamp,str) or len(stamp)>40:raise ValueError('created_at must be ISO-8601 with timezone')
            try:dt=datetime.fromisoformat(stamp.replace('Z','+00:00'))
            except ValueError as exc:raise ValueError('Invalid created_at timestamp') from exc
            if dt.tzinfo is None:raise ValueError('created_at must include timezone')
        if type(created_tick) is not int or created_tick<0:raise ValueError('Invalid creation tick')
        manifest,behavior=behavior_manifest(payload['behavior_manifest'])
        attachment=None;encoded=None
        if payload.get('source_attachment') is not None:
            source=payload['source_attachment']
            if not isinstance(source,dict) or set(source)!={'filename','content_base64'}:raise ValueError('Source attachment needs filename and content_base64')
            filename=source['filename'];encoded=source['content_base64']
            if not isinstance(filename,str) or not 1<=len(filename)<=200 or any(c in filename for c in ('/','\\','\x00')):raise ValueError('Attachment filename must be a plain name')
            if not isinstance(encoded,str) or len(encoded)>180000:raise ValueError('Source attachment is limited to 128 KiB')
            try:content=base64.b64decode(encoded,validate=True)
            except (ValueError,TypeError) as exc:raise ValueError('Invalid attachment base64') from exc
            if not 1<=len(content)<=131072:raise ValueError('Source attachment must contain 1–131072 bytes')
            attachment=Attachment(filename,len(content),hashlib.sha256(content).hexdigest())
        content_hash=digest({'behavior_manifest':manifest,'source_sha256':attachment.sha256 if attachment else None})
        if 'content_hash' in payload and payload['content_hash']!=content_hash:raise ValueError('Release content hash mismatch')
        record=Release(rid,sid,version,content_hash,Creation(meta['author'],created_tick,stamp,description),
            json.dumps(manifest,sort_keys=True,separators=(',',':')),behavior,attachment)
        if rid in self._records:
            existing=self._records[rid]
            # An exact retry preserves first-registration time. Every other field
            # including metadata and attachment name must match the frozen record.
            from dataclasses import replace
            if replace(record,creation=replace(record.creation,created_tick=existing.creation.created_tick))!=existing:
                raise ValueError('Immutable release_id already exists with different content or metadata')
            return existing
        if any(r.service_id==sid and r.version==version for r in self._records.values()):raise ValueError('Service version is already registered')
        if len(self._records)>=64:raise ValueError('Registry limit is 64 immutable releases')
        if attachment and attachment.sha256 not in self._sources and len(self._sources)>=10:raise ValueError('Registry limit is 10 attached source blobs')
        self._records[rid]=record
        if attachment:self._sources[attachment.sha256]=encoded
        return record


def example_payloads(service_id='demo-service'):
    common={'schema_version':1,'service_id':service_id,'creation_metadata':{'author':'example-fixture','created_at':'2026-11-14T00:00:00Z','description':'Declared simulation only; no source execution'}}
    return [{**copy.deepcopy(common),'release_id':'release-001','version':'1.0.0',
        'behavior_manifest':{'schema_version':1,'profiles':[{'kind':'healthy'}]}},
        {**copy.deepcopy(common),'release_id':'release-002','version':'1.1.0',
         'behavior_manifest':{'schema_version':1,'profiles':[{'kind':'extra_cpu_work','work_multiplier':2},
            {'kind':'retained_memory_leak','retained_mb_per_completion':.25},
            {'kind':'increased_error_probability','error_probability':.1},
            {'kind':'slower_response','response_delay_ms':1500}]}}]


def memory_example_payloads(service_id='demo-service'):
    common={'schema_version':1,'service_id':service_id,'creation_metadata':{'author':'memory-example','description':'Declared process-memory-v1 behavior; source never executes'}}
    return [{**copy.deepcopy(common),'release_id':rid,'version':version,'behavior_manifest':{'schema_version':1,'profiles':[{'kind':'process_memory','retained_mb_per_request':rate,'background_mb_per_second':0.,'retained_limit_mb':limit}]}}
        for rid,version,rate,limit in [('sample-cache-v1','2.0.0-cache',.25,128.),('sample-leak-v3','2.0.0-retention',.5,None)]]
