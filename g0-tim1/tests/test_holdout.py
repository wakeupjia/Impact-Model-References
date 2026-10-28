"""Train/holdout split + out-of-sample TIM1 metrics."""

from __future__ import annotations

import numpy as np
import pytest

from g0_tim1.holdout import holdout_metrics, split_holdout
from g0_tim1.synth import make_events


def test_split_is_70_30_by_event_index():
    n = 100
    import pandas as pd

    ev = pd.DataFrame({"n": np.arange(n)})
    train, hold = split_holdout(ev)
    assert len(train) == 70
    assert len(hold) == 30
    assert train["n"].iloc[-1] < hold["n"].iloc[0]


def test_holdout_metrics_on_clean_synth():
    ev, _ = make_events(N=3000, L_true=40, noise=5e-4, seed=11)
    m = holdout_metrics(ev, L=40, units="price")
    assert m["G0_train_1"] > 0
    # in-sample fit is near-exact; out-of-sample should stay strong on clean synth
    assert m["corr_train_R_vs_Rhat"] > 0.9
    assert m["corr_holdout_R_vs_Rhat"] > 0.8
    assert m["n_train"] + m["n_holdout"] == len(ev)


def test_holdout_rejects_too_small_split():
    ev, _ = make_events(N=100, L_true=10, seed=2)
    with pytest.raises(ValueError):
        holdout_metrics(ev, L=40, units="price")
