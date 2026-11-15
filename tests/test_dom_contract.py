"""Regression test verifying DOM contract between dashboard index.html and app.js."""
from __future__ import annotations

import re
from pathlib import Path


def test_dom_element_ids_exist_in_html():
    """Verify that every getElementById('...') in app.js exists in index.html."""
    dashboard_dir = Path("canary_ssm/dashboard")
    js_path = dashboard_dir / "app.js"
    html_path = dashboard_dir / "index.html"

    assert js_path.exists(), "app.js must exist"
    assert html_path.exists(), "index.html must exist"

    js_content = js_path.read_text(encoding="utf-8")
    html_content = html_path.read_text(encoding="utf-8")

    # Extract all getElementById targets
    pattern = re.compile(r'getElementById\([\'"]([\w\-]+)[\'"]\)')
    referenced_ids = set(pattern.findall(js_content))

    # Some IDs may be dynamically generated inside app.js (e.g. tabs or pages)
    # Filter out dynamically created IDs if any
    missing_ids = []
    for elem_id in sorted(referenced_ids):
        # Look for id="elem_id" or id='elem_id'
        if f'id="{elem_id}"' not in html_content and f"id='{elem_id}'" not in html_content:
            missing_ids.append(elem_id)

    assert not missing_ids, f"The following IDs in app.js are missing from index.html: {missing_ids}"
