"""Evaluator-only operator-interval skeleton; no detector or calibrated metric claim."""
from dataclasses import dataclass
import argparse
import csv
import json
from pathlib import Path


def tick(value,name,optional=False):
    if optional and value is None:return
    if type(value) is not int or value<0:raise ValueError(f'{name} must be nonnegative integer simulated seconds')


@dataclass(frozen=True)
class OperatorLabel:
    onset:int|None
    recovery:int|None
    horizon:int
    label_id:str='operator-intervention-v1'

    def __post_init__(self):
        if self.label_id!='operator-intervention-v1':raise ValueError('Wrong evaluator label definition')
        tick(self.onset,'onset',True);tick(self.recovery,'recovery',True);tick(self.horizon,'horizon')
        if self.horizon<=0:raise ValueError('horizon must be positive')
        if self.onset is None and self.recovery is not None:raise ValueError('Recovery needs an onset')
        if self.onset is not None and self.onset>=self.horizon:raise ValueError('Onset must precede horizon')
        if self.recovery is not None and self.recovery<=self.onset:raise ValueError('Recovery must follow onset')


def classify(label,alarm_time,eligible_decisions=1,minimum_followup=30):
    if not isinstance(label,OperatorLabel):raise ValueError('Use an explicit OperatorLabel')
    tick(alarm_time,'alarm_time',True);tick(eligible_decisions,'eligible_decisions');tick(minimum_followup,'minimum_followup')
    if alarm_time is not None and alarm_time>label.horizon:raise ValueError('Alarm outside observed horizon')
    if eligible_decisions==0 and alarm_time is not None:raise ValueError('No eligible decision can produce an alarm')
    event=label.onset is not None
    followup=label.horizon-label.onset if event else None
    delay=None
    if eligible_decisions==0:status='abstain'
    elif not event:status='false_alarm' if alarm_time is not None else 'quiet'
    elif followup<minimum_followup:status='insufficient_followup'
    elif alarm_time is None:status='miss'
    elif alarm_time<label.onset:status='premature'
    elif label.recovery is None or alarm_time<label.recovery:
        status='success';delay=alarm_time-label.onset
    else:status='after_recovery'
    return {'status':status,'event':event,'delay_seconds':delay,'followup_seconds':followup,
        'capped_delay_seconds':delay if status=='success' else followup if event and status not in ('abstain','insufficient_followup') else None,
        'right_censored':event and (label.recovery is None or label.recovery>label.horizon),
        'evaluator_id':'operator-outcome-skeleton-v1'}


def run_handlabels(output):
    path=Path(__file__).resolve().parents[1]/'configs/world_evaluator_handlabels.json'
    cases=json.loads(path.read_text())['cases'];rows=[]
    for case in cases:
        actual=classify(OperatorLabel(**case['label']),case['alarm_time'],case.get('eligible_decisions',1),case.get('minimum_followup',30))
        passed=all(actual.get(k)==value for k,value in case['expected'].items())
        rows.append({'case_id':case['case_id'],**actual,'expected_status':case['expected']['status'],'passed':passed})
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    with (output/'outcomes.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    result={'fixture_only':True,'cases':len(rows),'passed':all(r['passed'] for r in rows),
        'note':'Hand-authored alarm/label cases, not detector predictions or benchmark results'}
    (output/'checks.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',default='examples/world_evaluator')
    result=run_handlabels(parser.parse_args().out);print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['passed'] else 1)
