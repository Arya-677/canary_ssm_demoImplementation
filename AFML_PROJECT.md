# Added AFML canary project

The additional simulator, dashboard and evaluator project is in
[AFML-Canary-SSM/](AFML-Canary-SSM/README.md).

Run its commands from that directory:

```sh
cd AFML-Canary-SSM
python -m pip install -r requirements-world-policy.lock
python -m pip install -e . --no-deps
python -m canary_ssm world-dashboard --config configs/world_console.yaml --port 8765 --state-dir runtime/integrated-console
```

This is the lightweight project snapshot: source, configurations, fitted models,
policies and required fixtures are included; bulk historical run exports are not.
See its distribution guide for validation limits and reproducibility details.

The original research package and frozen artifacts remain unchanged on this
branch. This addition does not merge the two inference implementations or run
any new research phase or final-test evaluation.
