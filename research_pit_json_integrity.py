"""Strict JSON source intake: integrity checks do not certify provenance."""
import json
import math

def _unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("DUPLICATE_JSON_KEY:" + key)
        out[key] = value
    return out

def _constant(token):
    raise ValueError("NONFINITE_JSON_CONSTANT:" + token)

def _finite(token):
    number = float(token)
    if not math.isfinite(number):
        raise ValueError("NONFINITE_JSON_NUMBER")
    return number

def strict_json(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= 8 * 1024 * 1024:
        raise ValueError("INVALID_JSON_ENVELOPE")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                          parse_constant=_constant, parse_float=_finite)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("INVALID_JSON_ENCODING_OR_SYNTAX") from exc
