"""Represent runtime numeric values in strict JSON."""
import math


def json_values(value, *, exact_integers=False):
    if isinstance(value, float) and not math.isfinite(value):
        if math.isnan(value):
            return 'NaN'
        return 'Infinity' if value > 0 else '-Infinity'
    if exact_integers and isinstance(value, int) and abs(value) > 9007199254740991:
        return str(value)
    if isinstance(value, dict):
        return {key: json_values(item, exact_integers=exact_integers) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_values(item, exact_integers=exact_integers) for item in value]
    return value
