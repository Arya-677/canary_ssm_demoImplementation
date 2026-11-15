"""Explicit evaluator/demo recipe reader; never imported by detector code."""
import json
from pathlib import Path


def recipe_for(artifact_id):
    path=Path(__file__).resolve().parents[1]/'examples/detector_dashboard/evaluator/recipes.json'
    if not path.exists():return None
    data=json.loads(path.read_text())
    recipe=next((r for r in data['recipes'] if r['artifact_id']==artifact_id),None)
    return {'evaluator_only':True,'not_detector_output':True,'recipe':recipe} if recipe else None
