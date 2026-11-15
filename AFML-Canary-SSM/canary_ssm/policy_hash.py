"""Semantic JSON SHA-256 for policy files crossing Python/browser boundaries."""
import hashlib,json,math


def canonical(value):
    # JSON.parse/stringify changes 1.0 to 1 and -0.0 to 0. Bind their numerical
    # meaning, while keeping booleans distinct. Never alter existing research hashes.
    if type(value) is float:
        if not math.isfinite(value):raise ValueError('Encode nonfinite thresholds explicitly')
        return int(value) if value.is_integer() else value
    if isinstance(value,dict):return {k:canonical(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [canonical(v) for v in value]
    return value


def digest(value):
    return hashlib.sha256(json.dumps(canonical(value),sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
