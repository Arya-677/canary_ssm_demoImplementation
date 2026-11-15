"""Deterministic simulated transport and public-only source adapter."""
from dataclasses import asdict, dataclass, replace
import heapq
import json
import math
from pathlib import Path
from .telemetry import PublicRecord, CausalWindowStore, finite, integer, digest


@dataclass(frozen=True)
class TelemetryConfig:
    enabled: bool = False
    delay_min_ticks: int = 0
    delay_max_ticks: int = 0
    duplicate_probability: float = 0
    missing_probability: float = 0
    missing_window_probability: float = 0
    drop_windows: tuple[int,...] = ()
    late_windows: tuple[int,...] = ()
    late_delay_ticks: int = 120
    decision_delay_seconds: int = 0
    minimum_coverage: float = .8
    max_records: int = 50000
    max_windows: int = 1000

    def __post_init__(self):
        if type(self.enabled) is not bool: raise ValueError('telemetry enabled must be boolean')
        integer(self.delay_min_ticks,'delay_min_ticks',0,1000)
        integer(self.delay_max_ticks,'delay_max_ticks',self.delay_min_ticks,1000)
        integer(self.late_delay_ticks,'late_delay_ticks',0,1000)
        integer(self.decision_delay_seconds,'decision_delay_seconds',0,600)
        integer(self.max_records,'max_records',1,200000);integer(self.max_windows,'max_windows',1,1000)
        for k in ('duplicate_probability','missing_probability','missing_window_probability'):
            finite(getattr(self,k),k)
            if getattr(self,k)>1: raise ValueError(f'{k} must be <= 1')
        finite(self.minimum_coverage,'minimum_coverage')
        if not 0<self.minimum_coverage<=1: raise ValueError('minimum_coverage must be in (0,1]')
        for k in ('drop_windows','late_windows'):
            items=getattr(self,k)
            if not isinstance(items,(list,tuple)): raise ValueError(f'{k} must be a sequence')
            for item in items: integer(item,k,0,self.max_windows-1)
            if len(set(items))!=len(items): raise ValueError(f'Duplicate {k}')
            object.__setattr__(self,k,tuple(sorted(items)))

    def to_dict(self):
        d=asdict(self)
        for k in ('drop_windows','late_windows'): d[k]=list(d[k])
        return d

    @classmethod
    def from_dict(cls,row):
        if not isinstance(row,dict): raise ValueError('telemetry config must be an object')
        try:return cls(**row)
        except TypeError as exc:raise ValueError(f'Invalid telemetry config: {exc}') from exc


class TelemetryPipeline:
    def __init__(self,config,world,dt,run_id,epoch):
        if dt>60 or 60%dt or config.decision_delay_seconds%dt:
            raise ValueError('Enabled telemetry needs ticks dividing 60 and tick-aligned decision grace')
        hosts={h.host_id:h for h in world.hosts}
        roster=[dict(host_id=r.host_id,rack_id=hosts[r.host_id].rack_id,class_id=hosts[r.host_id].class_id,
                     service_id=r.service_id,replica_id=r.replica_id) for r in world.replicas]
        self.config,self.dt,self.run_id,self.epoch=config,dt,run_id,epoch
        self.store=CausalWindowStore(run_id,roster,dt,config.decision_delay_seconds,config.minimum_coverage,
                                    config.max_records,config.max_windows,epoch)
        self.pending=[];self.order=0;self.source_count=0;self.last_source_records=[];self.window_loss={}
        self.counters=dict(source_drops=0,window_drops=0,transport_capacity_drops=0,duplicates_sent=0)

    def emit(self,world,tick,batches,routed,host_rows,exposed_replicas,rng):
        now=tick*self.dt;win=math.ceil(now/60)-1
        stats={r.replica_id:[0,0.,0.,0.,0.] for r in world.replicas}
        for batch in batches:
            n,lat=batch['request_count'],batch['latency_ms'];v=stats[batch['replica_id']]
            v[0]+=n;v[1]+=n*lat;v[2]+=n*lat*lat;v[3]+=n*math.log(lat);v[4]+=n*math.log(lat)**2
        hosts={h.host_id:h for h in world.hosts};usage={r['host_id']:r for r in host_rows}
        self.last_source_records=[]
        for r in sorted(world.replicas,key=lambda r:r.replica_id):
            if self.source_count>=self.config.max_records or win>=self.config.max_windows:
                self.counters['transport_capacity_drops']+=1;continue
            n,total,sq,logs,logsq=stats[r.replica_id];h=hosts[r.host_id];u=usage[r.host_id]
            row=PublicRecord(digest([self.run_id,self.epoch,tick,r.replica_id]),self.run_id,r.host_id,h.rack_id,h.class_id,
                r.service_id,r.replica_id,r.release_id,r.replica_id in exposed_replicas,now,now,self.dt,n,
                total/n if n else None,routed.get(r.replica_id,0)/self.dt,total,sq,logs,logsq,
                latency_observed=n>0,cpu_cores=u['cpu_cores'],memory_mb=u['memory_mb'],network_mbps=u['network_mbps'],epoch=self.epoch)
            self.source_count+=1;self.last_source_records.append(row)
            key=(win,r.replica_id)
            if key not in self.window_loss:
                self.window_loss[key]=win in self.config.drop_windows or float(rng.random())<self.config.missing_window_probability
            # Unconditional draws keep payload values from influencing transport randomness.
            missing,duplicate,delay_u=rng.random(3)
            delay=self.config.delay_min_ticks+min(self.config.delay_max_ticks-self.config.delay_min_ticks,
                int(delay_u*(self.config.delay_max_ticks-self.config.delay_min_ticks+1)))
            if win in self.config.late_windows:delay+=self.config.late_delay_ticks
            if self.window_loss[key]:self.counters['window_drops']+=1;continue
            if missing<self.config.missing_probability:self.counters['source_drops']+=1;continue
            self._enqueue(replace(row,arrival_time=now+delay*self.dt))
            if duplicate<self.config.duplicate_probability:
                self._enqueue(replace(row,arrival_time=now+(delay+1)*self.dt));self.counters['duplicates_sent']+=1
        self.deliver_through(now)

    def _enqueue(self,row):
        if len(self.pending)>=self.config.max_records:
            self.counters['transport_capacity_drops']+=1;return
        heapq.heappush(self.pending,(row.arrival_time,self.order,row));self.order+=1

    def deliver_through(self,now):
        finite(now,'delivery_time',self.store.clock)
        # Merge arrivals and decision deadlines so a large clock jump cannot backdate data.
        while True:
            deadline=(self.store.closed_count+1)*60+self.config.decision_delay_seconds
            can_close=self.store.closed_count<self.config.max_windows and deadline<=now
            next_arrival=self.pending[0][0] if self.pending else float('inf')
            if next_arrival<=now and (not can_close or next_arrival<=deadline):
                arrival,_,row=heapq.heappop(self.pending);self.store.ingest(row,arrival)
            elif can_close:self.store.decide(deadline)
            else:break
        self.store.clock=max(self.store.clock,now)

    def summary(self):
        return {'enabled':True,'run_id':self.run_id,'epoch':self.epoch,'received_records':len(self.store.received),
                'closed_minutes':self.store.closed_count,'pending_records':len(self.pending),
                'transport_counters':dict(self.counters),'receiver_counters':dict(self.store.counters),
                'latency_metric':'completed_request_tick_latency_ms','window_seconds':60}

    def public_artifact(self):return self.store.public_artifact()

    def transport_state(self):
        return {'pending':[{'order':order,'record':row.to_dict()} for _,order,row in sorted(self.pending)],
                'source_count':self.source_count,'order':self.order,'counters':dict(self.counters),
                'window_loss':[{'window':w,'replica_id':r,'missing':v} for (w,r),v in sorted(self.window_loss.items())]}

    def export_public(self,directory):
        directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
        data=self.public_artifact()
        for key in ('records','windows','decisions','scores'):
            (directory/f'{key}.jsonl').write_text(''.join(json.dumps(row,allow_nan=False)+'\n' for row in data.pop(key)))
        data.update(config=self.config.to_dict(),summary=self.summary(),units='simulated seconds since run start; latency in ms')
        (directory/'metadata.json').write_text(json.dumps(data,indent=2)+'\n')
