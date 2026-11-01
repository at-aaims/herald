from typing import TypeVar
import itertools
import pandas as pd
import numpy as np

T = TypeVar("T")

def normalize_np(val: T) -> T:
    """ Converts any numpy fields into standard python objects. By default converts NaN to None """
    if isinstance(val, dict):
        return {k: normalize_np(v) for k, v in val.items()} #type: ignore
    elif isinstance(val, (list, tuple, set)):
        return type(val)([normalize_np(v) for v in val]) #type: ignore
    elif isinstance(val, np.generic):
        return normalize_np(val.item())
    elif pd.isna(val):
        return None
    else:
        return val


def omit(d: dict, keys: list):
    return {k: v for k, v in d.items() if k not in keys}


def pick(d: dict, keys: list):
    return {k: v for k, v in d.items() if k in keys}


def find_dups(items: list[T]) -> list[T]:
    return [
        k for k, v in itertools.groupby(sorted(items))
        if len(list(v)) > 1
    ]
