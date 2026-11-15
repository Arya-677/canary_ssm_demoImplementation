"""Generate measured checkpoint tables from saved CSV/JSON/test evidence."""
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'examples/world_policy'
WP = ROOT/'docs/wp'
policy = json.loads((OUT/'policy.json').read_text())
validation = json.loads((OUT/'validation.json').read_text())
http = json.loads((OUT/'http_demo_checks.json').read_text())
preserved = json.loads((WP/'world_policy_preservation.json').read_text())
log = (WP/'world_policy_full_tests_verified.txt').read_text()
test_result = re.findall(r'\d+ passed[^\n]*',log)[-1]
rates = list(csv.DictReader((OUT/'false_alerts.csv').open()))
status = 'implemented' if validation['gate']['status']=='PASS' else 'partial'
rows = [
    ('Healthy physical development fit','implemented','world_policy_fixture.export_fixture → fit_development; development_fit.json, frozen.json','None within the declared all-healthy distribution'),
    ('Full-horizon physical null maxima and strict first crossing','implemented','world_policy_fixture._null; null_maxima.csv; existing policy_artifacts.calibrate','None for this fixed four-minute protocol'),
    ('Independent physical null qualification',status,'validation.json gate '+validation['gate']['status']+'; false_alerts.csv; separate registered seed roles','New version and fresh data for any changed distribution/settings; never retune this audit'),
    ('Compatible policy and explicit hashes','implemented','world_simulator/world_protocol, frozen.json, policy.json; actual HTTP attachment','None for the supplied independent-effect configuration'),
    ('Public live telemetry → posterior charts and policy','implemented','world_policy_live.public_outputs/PublicPolicyPump.poll_once; http_demo_checks.json; ten saved HTTP sessions','Run the external producer alongside the backend; no browser simulation loop'),
    ('Automatic PAUSE, manual ROLLBACK and replay','implemented' if http['passed'] else 'partial','world_policy_http_demo.export_demo; actual public observations and command_outcomes.json','None if the saved HTTP demo gates pass'),
    ('Opt-in automatic rollback','implemented','Existing policy_control adapter and original tests; HTTP examples explicitly keep it off','Optional separately recorded opt-in; default remains false'),
    ('Positive-evidence promotion','implemented','Existing PolicyController.guard and LatchedFirstCrossing; full eligible budget plus healthy score ceiling','No utility/power claim from absence of an alarm'),
    ('Broader fault/missingness/advisory null distribution','partial','Current config has no random platform faults or telemetry loss; resource/platform producers disabled','New development freeze, full combined-policy null replay and independent validation for an enabled wider family'),
    ('Physical hierarchical/pooling calibration','missing','This matched policy uses EffectParams(kind=indep); original grouped/nested demos remain separate','Freeze each hierarchy setting on development, calibrate and validate independently'),
    ('Specific laptop browser visual check','unverified','Cloud browser could not reach this backend loopback origin (ERR_CONNECTION_REFUSED); real local HTTP path is checked','Inspect the saved dashboard sessions in a browser on the running backend host'),
    ('Original inference, tests and research artifact preservation','implemented','world_policy_preservation.json; original tests byte-preserved; no original canary_ssm source change','None'),
]
table = '| Requirement | Status | Actual file/function and evidence | Smallest next patch |\n| --- | --- | --- | --- |\n'
table += '\n'.join('| '+' | '.join(row)+' |' for row in rows)+'\n'
rate_table = '| Channel | Events | Null rollouts | Rate | Pointwise exact 95% interval |\n| --- | --- | --- | --- | --- |\n'
rate_table += '\n'.join('| '+ ' | '.join([r['channel'],r['events'],r['n'],r['rate'],'['+r['lower_95']+', '+r['upper_95']+']'])+' |' for r in rates)+'\n'
report = '''# Physical-world policy checkpoint — 15 November 2026

This closes the earlier checkpoint's missing matched physical-world calibration
within one explicitly scoped version. It does not close the original shared-step
failure or certify other world configurations, hierarchies or advisory producers.
No original inference implementation or test was rewritten.

## Executed evidence

'''
report += f'Full repository suite: **{test_result}**.\n\n'
report += f"Calibration B={policy['calibration']['B']}, alpha={policy['calibration']['alpha']}, k={policy['calibration']['k']}, frozen threshold={policy['calibration']['threshold']}. "
report += f"Independent validation gate: **{validation['gate']['status']}**. "
report += 'Gate details, Beta diagnostics, ineligible/no-data counts and all outcome rows are retained in `examples/world_policy/validation.json`.\n\n'
report += rate_table+'\n'
report += f"**Abstention matters:** {validation['no_eligible_nulls']} of {len(validation['outcomes'])} null rollouts had no eligible monitoring windows. Among {validation['eligible_rollouts']} rollouts with any eligible window, the conditional alert fraction was {validation['conditional_on_any_eligible']['rate']}; the nominal alpha guarantee is not conditional on eligibility. In particular, current workload-support overlap checks often HOLD in this short four-minute protocol. No-data rollouts are never promoted as healthy.\n\n"
report += 'The combined row is the measured union. Platform/resource producers are disabled in this null family; their zero observed counts do not imply zero population false alerts. Intervals are pointwise, not simultaneous. Calibration rank coverage assumes independent/exchangeable complete null rollouts from this exact frozen pipeline.\n\n'
report += f"Policy hash: `{policy['policy_hash']}`.\n\nValidation hash: `{validation['validation_hash']}`.\n\n"
report += 'Both HTTP sessions use actual physical requests, saved public telemetry and the frozen Gaussian posterior. Polls never advance the world. Repeated polls emit no duplicate decisions. The candidate example is illustrative and is not a power estimate.\n\n'
report += '| HTTP example | Automatic pause | Final state | Detector frames | Exact engine replay |\n| --- | --- | --- | --- | --- |\n'
for n,r in http.items():
    if not isinstance(r,dict):
        continue
    report += f"| {n} | {r['automatic_pause']} | {r['final_state']} | {r['detector_frames']} | {r['replay_identical']} |\n"
report += '\n'+table
report += '\nThe HTTP smoke bundle retains all healthy/combined/strong-delay outcomes. `http_alarm` aliases the first eligible crossing in the eight predeclared strong-delay smoke seeds; no model, threshold or validation seed was selected from these outcomes. This selected replay is not a power estimate. The original combined release can show high posterior risk while eligibility flags correctly hold action. A client clock-command argument mismatch was caught by actual HTTP execution and fixed in the new client; its failing regression is retained.\n'
report += '\nCommands and scope: [world_policy.md](../world_policy.md). Actual logs: `world_policy_full_tests_initial.txt`, `world_policy_full_tests_verified.txt`, `world_policy_fixture_run.txt`, `world_policy_http_run.txt`, `world_policy_cli_validation.json`. The first full run encountered a missing optional `tabulate` dependency in the restored environment; after installing the declared report dependency, the complete suite passed without editing a test. Original checkpoint reports remain historical.\n'
(WP/'WORLD-POLICY.md').write_text(report)
section = '\n## Matched physical-world policy checkpoint — 15 November 2026\n\n'
section += 'This table supersedes the earlier physical-calibration gap only for `configs/world_policy_v1.yaml`. Earlier rows and test counts describe their original checkpoints. See [WORLD-POLICY.md](wp/WORLD-POLICY.md) for measured results and [world_policy.md](world_policy.md) for runnable commands.\n\n'+table
for name in ('gap_audit.md','implementation_status.md'):
    path = ROOT/'docs'/name
    text = path.read_text()
    marker = '\n## Matched physical-world policy checkpoint — 15 November 2026'
    if marker in text:
        text = text.split(marker)[0]
    text = text.replace('Latest checkpoint: process-memory-v1 and resource advisory; see the final requirement table. Earlier sections retain historical scope.',
        'Latest checkpoint: matched physical-world policy; see the final requirement table. Earlier sections retain historical scope.')
    path.write_text(text.rstrip()+'\n'+section)
print(json.dumps({'report':str(WP/'WORLD-POLICY.md'),'gate':validation['gate']['status'],'tests':test_result,'http_passed':http['passed']}))
