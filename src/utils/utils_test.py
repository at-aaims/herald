from src.utils.utils import normalize_np
import numpy as np
import pandas as pd

def test_normalize_np():
    assert normalize_np(1) == 1
    assert normalize_np(np.int64(4)) == 4
    assert type(normalize_np(np.float64(1.0))) == float

    data = {
        'a': [np.float64(1.2), np.int64(3), None, np.nan, pd.NA]
    }
    assert normalize_np(data) == {
        'a': [1.2, 3, None, None, None]
    }
    assert [type(d) for d in normalize_np(data)['a']] == [float, int, type(None), type(None), type(None)]
