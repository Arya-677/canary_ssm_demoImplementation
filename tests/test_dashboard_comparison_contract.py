"""Regression checks for the browser/API method-comparison contract."""
from pathlib import Path


def test_dashboard_uses_the_compare_endpoint_response_schema():
    """The UI must render the actual named methods and host arrays returned by the API."""
    source = Path("canary_ssm/dashboard/app.js").read_text(encoding="utf-8")

    assert "comp.methods.hierarchical" in source
    assert "comp.methods.independent" in source
    assert "Array.isArray(hier.hosts)" in source
    assert "host.server_id" in source
    assert "Number.isFinite(hier.release_score)" in source


def test_dashboard_does_not_present_a_hard_coded_calibration_verdict():
    """Live policy messaging must be driven by the service, not stale audit numbers."""
    source = Path("canary_ssm/dashboard/index.html").read_text(encoding="utf-8")

    assert "FAR=0.05, N=2000" not in source
    assert "does not load a calibration artifact by hash" in source
