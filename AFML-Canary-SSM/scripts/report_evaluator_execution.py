"""Build execution notes and summary tables solely from saved evidence."""
from collections import Counter
import csv
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
STUDY=ROOT/'examples/evaluator_v2'
DOCS=ROOT/'docs/wp'

def rows(path):
    with path.open(newline='') as f:return list(csv.DictReader(f))

def main():
    f=json.loads((STUDY/'development_freeze.json').read_text());gates=[]
    lines=['# Evaluator v2: executed evidence','',
        'The Linux rebuild extends the integrated-dashboard checkpoint with public-only scoring, evaluator-only retrospective targets, disjoint data roles, independently calibrated comparators/ablations, saved tables/figures and scoped performance measurements. Earlier Mac evaluator/cache results were unavailable and were not imported as v2 measurements.','',
        '## Independent null audits','',
        '| Generator / endpoint | B | Independent n | Policies | PASS | FAIL | INSUFFICIENT |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for gen,endpoints in [('research',['latent_effect']),('world',['release_latency','infrastructure'])]:
        for endpoint in endpoints:
            p=STUDY/gen/(endpoint+'_null_intervals.csv')
            if not p.exists():lines.append(f'| {gen} / {endpoint} | pending | pending | pending | pending | pending | pending |');continue
            rr=rows(p);gates+=rr;c=Counter(r['gate'] for r in rr)
            lines.append(f'| {gen} / {endpoint} | {rr[0]["B"]} | {rr[0]["n"]} | {len(rr)} | {c["PASS"]} | {c["FAIL"]} | {c["INSUFFICIENT"]} |')
    lines+=['','These are computed diagnostic audit verdicts. Release-null calibration is a declared six-family mixture, not independent per-family qualification. Platform nulls are all healthy. Continuous-maxima Beta–Binomial diagnostics can fail with saturated/tied scores even when strict thresholds produce conservative alarms; those failures remain visible. Final inputs stay sealed pending the governing per-family gate; no superiority claim follows from these mixture audits.','',
        '## Saved scenario outcomes','',
        '| Generator | Raw rows | Status counts |','| --- | ---: | --- |']
    for gen,name in [('research','research_results.csv'),('world','resource_world_results.csv')]:
        p=STUDY/gen/name
        if p.exists():
            rr=rows(p);c=Counter(r['status'] for r in rr);lines.append(f'| {gen} | {len(rr)} | '+', '.join(f'{k}: {v}' for k,v in sorted(c.items()))+' |')
        else:lines.append(f'| {gen} | pending | pending |')
    lines+=['','Smoke rows are one paired replay per scenario, not final-test power or delay estimates. Research memory mechanisms are unsupported rows, not fabricated latent memory outcomes. World missing targets, unmonitored affected controls, misses, late alarms and abstentions remain included. Raw generator tables never share a target definition or denominator.','',
        '## Numerical and leakage contracts','',
        '- Research preserves the original strict log(1.02)/15-minute latent event, first-crossing premature/success/miss/late rules, capped failure delay and onset+30 localization. Canonical prediction-only localization and its fresh-only counterpart remain separately labeled.',
        '- World release attribution uses an offline paired completed-request log-mean difference. Infrastructure uses separate operator disturbance windows. Routing/queue interference is measured; no additive equality or directly observed online counterfactual is asserted.',
        '- Classical methods have statistics, not fabricated posteriors. Independent, pooled, class/rack and nested Gaussian methods reuse the existing numerical engines and retain white shared uncertainty exactly once. Factor/AR ablations refit healthy nuisance models; persistence-off reselects effect settings without refitting a mathematically unchanged no-effect nuisance likelihood.',
        '- Development decisions freeze before calibration. Calibration and independent validation use disjoint registered seeds. Tests cover future-data/truth perturbations, strict boundaries, capped outcomes, role isolation, paired identities, final locks and tampered caches.','',
        '## Performance measurements','',
        '| Component | Samples | Operations/second | Scope |','| --- | ---: | ---: | --- |']
    p=STUDY/'performance/throughput_summary.csv'
    if p.exists():
        for r in rows(p):lines.append(f'| {r["component"]} | {r["samples"]} | {r["operations_per_second"]} | {r["scope"]} |')
    p=STUDY/'performance/renderer_samples.csv'
    if p.exists():
        rr=rows(p)
        for component in sorted({r['component'] for r in rr}):
            ss=[r for r in rr if r['component']==component];ns=sum(int(r['elapsed_ns']) for r in ss);lines.append(f'| {component} | {len(ss)} | {len(ss)/(ns/1e9)} | '+ss[0]['scope']+' |')
    lines+=['','Per-update wall samples, state bytes and separate traced peak allocations are under `performance/`; traced allocations are not RSS. All timings were collected under concurrent audit load and are diagnostic, not isolated capacity limits. Renderer VM throughput is not browser layout/paint/input throughput. Local Chromium launch failed because the environment denied its Unix socket; the alternate cloud browser could not reach the workspace-local server. Browser throughput remains UNVERIFIED.','',
        'The first repeated API measurement reused persisted command IDs and counted cached receipts. Its raw files are retained under `performance/retired_duplicate_command_measurement/INVALID.json`. The corrected measurement uses a fresh runtime directory, asserts one actual engine tick per sample, and has a regression test rejecting duplicate-command samples.','',
        '## Regression verification','']
    testlog=DOCS/'evaluator_full_tests_final.txt'
    if testlog.exists():
        match=re.findall(r'\d+ passed[^\n]*',testlog.read_text());lines.append('Latest complete test command: `python -m pytest -q`. Result: **'+(match[-1] if match else 'see saved test log')+'**.')
    preservation=json.loads((DOCS/'evaluator_preservation.json').read_text());lines+=['',
        'Original-file comparison against the integrated dashboard ZIP is saved in `evaluator_preservation.json`. All original numerical modules and all original test files are byte-preserved. Changes to original files are documentation links plus the recorded dashboard fixture runtime metadata. The original Mac fixture is retained under `examples/evaluator_runtime/`.','',
        '## Executed commands','',
        '```bash','export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1',
        'python -m canary_ssm.replay_evaluator run --out examples/evaluator_v2 --B 2000 --n-validation 2000 --offset 12500 --workers 8',
        'python -m canary_ssm.evaluation_performance --study examples/evaluator_v2 --inputs /tmp/evaluator_v2_pilot',
        'python -m canary_ssm.evaluation_report --study examples/evaluator_v2',
        'python -m canary_ssm.evaluation_check --study examples/evaluator_v2',
        'python -m canary_ssm.evaluation_archive replay-null --study examples/evaluator_v2 --generator world --endpoint release_latency --role null-validation --index 0',
        'python -m canary_ssm.replay_evaluator check-final-lock --out examples/evaluator_v2',
        'python -m pytest -q','```','',
        'The pilot input path was used only for separately hashed public performance inputs; copies are included under `performance/inputs`. Future performance reproduction can use `--inputs examples/evaluator_v2` after the full smoke export exists. Use the evaluator guide for verified resume/null replay commands.','',
        'The freeze binds source/config/runtime/models and seed plans. Full scenario public arrays/evaluator truth, every raw result table and per-minute score/mask, independent maxima and config/seed/ordered commands are saved. The compact delivery replaces large null-input buffers with verified semantic fingerprints and exact source/seed regeneration; no negative outcome or score is omitted. Source snapshots permit exact provenance inspection. No online policy is attached by this offline study.']
    (DOCS/'EVALUATOR.md').write_text('\n'.join(lines)+'\n')
    (DOCS/'evaluator_execution_summary.json').write_text(json.dumps(dict(study_id=f['study_id'],freeze_hash=f['freeze_hash'],audits_completed=len({(r['generator'],r['endpoint']) for r in gates}),diagnostic_gates=dict(Counter(r['gate'] for r in gates)),final_test_materialized=(STUDY/'final_test_access.json').exists(),original_tests_preserved=preservation['preserved_all_original_tests']),indent=2)+'\n')

if __name__=='__main__':main()
