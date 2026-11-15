"""Public records and frozen causal monitoring windows. No simulator truth imports."""
from dataclasses import asdict, dataclass, replace
import copy
import hashlib
import json
import math


def finite(value, name, low=0):
    if type(value) not in (int, float) or not math.isfinite(value) or value < low:
        raise ValueError(f"{name} must be finite and >= {low}")


def integer(value, name, low=0, high=1_000_000_000):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be integer in [{low}, {high}]")


def identifier(value, name):
    if not isinstance(value, str) or not value.strip() or value.strip() != value or len(value) > 256:
        raise ValueError(f"Invalid {name}")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class PublicRecord:
    record_id: str
    run_id: str
    host_id: str
    rack_id: str
    class_id: int
    service_id: str
    replica_id: str
    release_id: str
    exposed: bool
    event_time: float
    arrival_time: float
    interval_seconds: int
    request_count: int
    latency_ms: float | None
    workload: float | None
    latency_sum_ms: float = 0
    latency_sum_sq_ms2: float = 0
    log_latency_sum: float = 0
    log_latency_sum_sq: float = 0
    observed: bool = True
    latency_observed: bool = False
    workload_observed: bool = True
    exposure_observed: bool = True
    carried_forward: bool = False
    cpu_cores: float | None = None
    memory_mb: float | None = None
    network_mbps: float | None = None
    epoch: int = 0

    def __post_init__(self):
        for k in ('record_id','run_id','host_id','rack_id','service_id','replica_id','release_id'):
            identifier(getattr(self,k),k)
        for k in ('exposed','observed','latency_observed','workload_observed','exposure_observed','carried_forward'):
            if type(getattr(self,k)) is not bool: raise ValueError(f'{k} must be boolean')
        for k in ('class_id','epoch','request_count'): integer(getattr(self,k),k)
        integer(self.interval_seconds,'interval_seconds',1,60)
        if 60 % self.interval_seconds: raise ValueError('Telemetry interval must divide 60 seconds')
        finite(self.event_time,'event_time',self.interval_seconds)
        finite(self.arrival_time,'arrival_time',self.event_time)
        if not math.isclose(self.event_time/self.interval_seconds,round(self.event_time/self.interval_seconds),abs_tol=1e-9):
            raise ValueError('event_time must be on the tick grid')
        for k in ('latency_sum_ms','latency_sum_sq_ms2','log_latency_sum_sq'): finite(getattr(self,k),k)
        if type(self.log_latency_sum) not in (int,float) or not math.isfinite(self.log_latency_sum):
            raise ValueError('log_latency_sum must be finite')
        for k in ('workload','cpu_cores','memory_mb','network_mbps'):
            if getattr(self,k) is not None: finite(getattr(self,k),k)
        if self.latency_ms is not None: finite(self.latency_ms,'latency_ms',1e-12)
        if (not self.observed or self.carried_forward) and any((self.latency_observed,self.workload_observed,self.exposure_observed)):
            raise ValueError('Unobserved or carried values cannot have fresh masks')
        if self.workload_observed and self.workload is None: raise ValueError('Fresh workload needs a value')
        if self.latency_observed:
            n=self.request_count
            if n<1 or self.latency_ms is None or not math.isclose(self.latency_ms*n,self.latency_sum_ms,rel_tol=1e-9,abs_tol=1e-9):
                raise ValueError('Fresh latency needs consistent count, mean and sum')
            for total,squares in ((self.latency_sum_ms,self.latency_sum_sq_ms2),(self.log_latency_sum,self.log_latency_sum_sq)):
                if squares*n+1e-8*max(1,total*total)<total*total: raise ValueError('Invalid second moment')
        elif any((self.latency_sum_ms,self.latency_sum_sq_ms2,self.log_latency_sum,self.log_latency_sum_sq)):
            raise ValueError('Masked latency must have zero sufficient statistics')

    def to_dict(self): return asdict(self)

    @classmethod
    def from_dict(cls,row):
        if not isinstance(row,dict): raise ValueError('Public record must be an object')
        try: return cls(**row)
        except TypeError as exc: raise ValueError(f'Invalid public fields: {exc}') from exc

    @property
    def window(self): return math.ceil(self.event_time/60)-1


class CausalWindowStore:
    """First receipt wins; each completed minute is frozen at its deadline once."""
    def __init__(self,run_id,roster,interval_seconds=1,decision_delay_seconds=0,
                 minimum_coverage=.8,max_records=50000,max_windows=1000,epoch=0):
        identifier(run_id,'run_id');integer(epoch,'epoch')
        integer(interval_seconds,'interval_seconds',1,60)
        if 60%interval_seconds: raise ValueError('Telemetry interval must divide 60')
        integer(decision_delay_seconds,'decision_delay_seconds',0,600)
        finite(minimum_coverage,'minimum_coverage')
        if not 0<minimum_coverage<=1: raise ValueError('minimum_coverage must be in (0,1]')
        integer(max_records,'max_records',1,200000);integer(max_windows,'max_windows',1,1000)
        self.run_id,self.epoch,self.dt=run_id,epoch,interval_seconds
        self.grace,self.minimum_coverage=decision_delay_seconds,minimum_coverage
        self.max_records,self.max_windows=max_records,max_windows
        self.roster={}
        for original in roster:
            r=dict(original)
            if set(r)!={'host_id','rack_id','class_id','service_id','replica_id'}: raise ValueError('Invalid roster fields')
            for k in ('host_id','rack_id','service_id','replica_id'): identifier(r[k],k)
            integer(r['class_id'],'class_id')
            if r['replica_id'] in self.roster: raise ValueError('Duplicate replica')
            self.roster[r['replica_id']]=r
        if not self.roster or len(self.roster)>1000: raise ValueError('Roster size must be 1–1000')
        self.clock=0;self.closed_count=0
        self.seen_ids={};self.seen_slots={};self.buckets={}
        self.received=[];self.windows=[];self.decisions={};self.scores={}
        self.counters=dict(duplicates=0,conflicts=0,late=0,capacity_drops=0)

    def ingest(self,record,received_at):
        if not isinstance(record,PublicRecord): record=PublicRecord.from_dict(record)
        finite(received_at,'received_at',self.clock)
        if record.arrival_time>received_at: raise ValueError('Cannot ingest before arrival')
        if record.run_id!=self.run_id or record.epoch!=self.epoch: raise ValueError('Wrong run or epoch')
        parent=self.roster.get(record.replica_id)
        if parent is None or any(getattr(record,k)!=v for k,v in parent.items()): raise ValueError('Conflicting placement')
        if record.interval_seconds!=self.dt: raise ValueError('Wrong telemetry interval')
        self.clock=received_at
        record=replace(record,arrival_time=received_at)  # receiver prevents backdating
        payload=record.to_dict();payload.pop('arrival_time');payload.pop('record_id')
        fingerprint=digest(payload);slot=(record.replica_id,record.event_time)
        old=self.seen_ids.get(record.record_id) or self.seen_slots.get(slot)
        if old is not None:
            result='duplicates' if old==fingerprint else 'conflicts'
            self.counters[result]+=1;return result
        if len(self.received)>=self.max_records or record.window>=self.max_windows:
            self.counters['capacity_drops']+=1;return 'capacity_drops'
        self.seen_ids[record.record_id]=fingerprint;self.seen_slots[slot]=fingerprint
        self.received.append(record.to_dict())
        if record.arrival_time>(record.window+1)*60+self.grace or record.window<self.closed_count:
            self.counters['late']+=1;return 'late'
        self.buckets.setdefault((record.window,record.replica_id),[]).append(record)
        return 'accepted'

    def _aggregate(self,index,rid):
        rows=self.buckets.pop((index,rid),[])
        fresh=[r for r in rows if r.observed and not r.carried_forward]
        latency=[r for r in fresh if r.latency_observed]
        workload=[r for r in fresh if r.workload_observed]
        exposure=[r for r in fresh if r.exposure_observed]
        n=sum(r.request_count for r in latency);coverage=len(fresh)*self.dt/60
        versions=sorted({r.release_id for r in exposure});cohorts=sorted({r.exposed for r in exposure})
        mixed=len(versions)>1 or len(cohorts)>1
        exposure_ok=len(exposure)*self.dt/60>=self.minimum_coverage and len(versions)==len(cohorts)==1
        observed=coverage>=self.minimum_coverage and n>0 and exposure_ok and not mixed
        total=sum(r.latency_sum_ms for r in latency);logs=sum(r.log_latency_sum for r in latency)
        return {'run_id':self.run_id,'epoch':self.epoch,**self.roster[rid],'window_index':index,
            'event_time':(index+1)*60,'window_start':index*60,'window_end':(index+1)*60,
            'decision_time':(index+1)*60+self.grace,'request_count':n,'latency_ms':total/n if n else None,
            'latency_sum_ms':total,'latency_sum_sq_ms2':sum(r.latency_sum_sq_ms2 for r in latency),
            'log_latency_mean':logs/n if n else None,'log_latency_sum':logs,
            'log_latency_sum_sq':sum(r.log_latency_sum_sq for r in latency),
            'workload':sum(r.workload*r.interval_seconds for r in workload)/sum(r.interval_seconds for r in workload) if workload else None,
            'workload_integral':sum(r.workload*r.interval_seconds for r in workload),
            'workload_seconds':sum(r.interval_seconds for r in workload),'coverage':coverage,
            'received_ticks':len(rows),'fresh_ticks':len(fresh),'observed':observed,'latency_observed':observed,
            'workload_observed':len(workload)*self.dt/60>=self.minimum_coverage,
            'exposure_observed':exposure_ok,'release_id':versions[0] if len(versions)==1 else None,
            'release_ids':versions,'exposed':cohorts[0] if len(cohorts)==1 else None,
            'mixed_exposure':mixed,'carried_forward':False}

    def decide(self,decision_time):
        finite(decision_time,'decision_time')
        if decision_time in self.decisions: return copy.deepcopy(self.decisions[decision_time])
        if decision_time<self.clock: raise ValueError('New decisions must be monotonic')
        self.clock=decision_time
        through=min(self.max_windows,max(0,math.floor((decision_time-self.grace)/60)))
        while self.closed_count<through:
            for rid in sorted(self.roster): self.windows.append(self._aggregate(self.closed_count,rid))
            self.closed_count+=1
        result={'run_id':self.run_id,'epoch':self.epoch,'decision_time':decision_time,
                'window_count':len(self.windows),'input_sha256':digest(self.windows)}
        self.decisions[decision_time]=result
        return copy.deepcopy(result)

    def time_slice(self,decision_time):
        receipt=self.decide(decision_time)
        return {**receipt,'windows':copy.deepcopy(self.windows[:receipt['window_count']])}

    def score_once(self,decision_time,scorer):
        """Trusted external callback sees only frozen public data; no detector is supplied."""
        if decision_time in self.scores: return copy.deepcopy(self.scores[decision_time])
        sliced=self.time_slice(decision_time);result=scorer(copy.deepcopy(sliced))
        json.dumps(result,allow_nan=False)
        self.scores[decision_time]={'decision_time':decision_time,'input_sha256':sliced['input_sha256'],'result':copy.deepcopy(result)}
        return copy.deepcopy(self.scores[decision_time])

    def public_artifact(self):
        return copy.deepcopy({'run_id':self.run_id,'epoch':self.epoch,'roster':list(self.roster.values()),
            'records':self.received,'windows':self.windows,'decisions':list(self.decisions.values()),
            'scores':list(self.scores.values()),'counters':self.counters})


def causal_time_slice(records,run_id,roster,decision_time,**options):
    """Offline/as-of entry point: filter on receiver receipt before reading payload values."""
    finite(decision_time,'decision_time')
    store=CausalWindowStore(run_id,roster,**options)
    eligible=[]
    for order,row in enumerate(records):
        arrival=row.arrival_time if isinstance(row,PublicRecord) else row.get('arrival_time')
        finite(arrival,'arrival_time')
        if arrival<=decision_time:
            eligible.append((arrival,order,row))
    for arrival,_,row in sorted(eligible,key=lambda item:(item[0],item[1])):
        while store.closed_count<store.max_windows and (store.closed_count+1)*60+store.grace<arrival:
            store.decide((store.closed_count+1)*60+store.grace)
        store.ingest(row,arrival)
    return store.time_slice(decision_time)
