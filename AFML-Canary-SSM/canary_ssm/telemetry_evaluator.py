"""Evaluator-only injection labels. Never imported by telemetry or inference modules."""
from pathlib import Path
import json


class TelemetryEvaluator:
    def __init__(self):self.rows=[]

    def capture(self,records,tick,demo,model):
        faults=[] if demo is None else [f for f in demo.faults if f.active(tick)]+demo.background.active_events(tick)
        for record in records:
            active=[f for f in faults if record.host_id in f.host_ids]
            rid=record.replica_id
            base=model.services[record.service_id]
            work=model.profiles[rid].work_core_seconds/base.work_core_seconds
            retention=model.retention_rates[rid]
            release_induced=work!=1 or retention!=0 or model.background_rates[rid]!=0 or model.error_probabilities[rid]!=0 or model.response_delays_ms[rid]!=0
            self.rows.append({'record_id':record.record_id,'run_id':record.run_id,'epoch':record.epoch,
                'host_id':record.host_id,'replica_id':rid,'event_time':record.event_time,
                'fault_type':sorted({f.kind.value for f in active}),'fault_ids':[f.fault_id for f in active],
                'true_affected':bool(active) or release_induced,'release_induced':release_induced,
                'injected_latent_effect':None,
                'injected_mechanisms':{'cpu_factor':model.cpu_factors[record.host_id],
                    'network_factor':model.network_factors[record.host_id],
                    'platform_memory_mb':model.platform_memory[record.host_id],
                    'demand_multiplier':model.demand_multiplier,'work_multiplier':work,
                    'retained_mb_per_completion':retention if model.memory_models[rid]=='legacy-bounded-v1' else None,
                    'retained_mb_per_request':retention if model.memory_models[rid]=='process-memory-v1' else None,
                    'background_mb_per_second':model.background_rates[rid],'retained_limit_mb':model.retained_limits[rid],'memory_model':model.memory_models[rid],'error_probability':model.error_probabilities[rid],
                    'response_delay_ms':model.response_delays_ms[rid]}})

    def artifact(self):
        import copy
        return {'evaluator_only':True,'label_definition':'targeted platform injection or nonneutral release resource behavior; not proof of code leak or observed latency harm',
                'latent_effect_definition':'No counterfactual additive log-latency effect is defined by this resource simulator; null is intentional',
                'records':copy.deepcopy(self.rows)}

    def export(self,directory):
        directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
        data=self.artifact()
        (directory/'truth.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in data.pop('records')))
        (directory/'metadata.json').write_text(json.dumps(data,indent=2)+'\n')
