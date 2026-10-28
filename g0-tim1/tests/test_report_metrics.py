"""End-to-end: pipeline → report artifacts exist and carry the checklist metrics."""

from __future__ import annotations

import json

import pytest

from g0_tim1.pipeline import run
from g0_tim1.report import generate_report

MOCK_KWARGS = {"n_quotes": 6000, "n_trades": 1200, "seed": 7}


@pytest.fixture(scope="module")
def ran(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("g0tim1")
    meta = run(data_dir=tmp / "data", art_dir=tmp / "art", preferred_L=40, mock_kwargs=MOCK_KWARGS)
    metrics = generate_report(tmp / "art")
    return tmp / "art", meta, metrics


def test_report_files_exist(ran):
    art, _, _ = ran
    assert (art / "TEST_REPORT.md").exists()
    assert (art / "test_metrics.json").exists()
    assert (art / "R_vs_Rhat.png").exists()
    assert (art / "G0_matrix.csv").exists()
    assert (art / "G0_differential.csv").exists()
    md = (art / "TEST_REPORT.md").read_text()
    for section in ("Synthetic TIM1 recovery", "Train/holdout", "Caveats", "Matrix vs differential"):
        assert section in md


def test_metrics_cover_checklist(ran):
    _, meta, metrics = ran
    cl = metrics["checklist"]
    for key in (
        "1_synthetic_recovery",
        "2_mock_R_vs_Rhat",
        "3_g1_and_age_buffer",
        "4_holdout",
        "5_caveats",
        "6_matrix_vs_differential",
    ):
        assert key in cl
    # 1: synthetic recovery passes researchy bars
    assert cl["1_synthetic_recovery"]["pass"] is True
    assert cl["1_synthetic_recovery"]["corr_true_G0_vs_G0hat"] > 0.7
    # 2: mock reconstruction strong
    assert cl["2_mock_R_vs_Rhat"]["corr_R_vs_Rhat"] > 0.9
    # 3: g(1)=1 and age buffer exact
    assert cl["3_g1_and_age_buffer"]["pass"] is True
    # 4: holdout recorded and non-degenerate
    assert cl["4_holdout"]["n_train"] + cl["4_holdout"]["n_holdout"] == meta["N_events"]
    assert cl["4_holdout"]["corr_holdout_R_vs_Rhat"] == cl["4_holdout"]["corr_holdout_R_vs_Rhat"]
    # 5: caveat explicit
    assert cl["5_caveats"]["one_day_mock_I0_b_not_trusted"] is True
    # 6: both paths recorded
    assert "G0_matrix_1" in cl["6_matrix_vs_differential"]
    assert meta["G0_solver"] in ("matrix", "differential")


def test_metrics_json_roundtrip(ran):
    art, _, _ = ran
    loaded = json.loads((art / "test_metrics.json").read_text())
    assert loaded["checklist"]["1_synthetic_recovery"]["pass"] is True


def test_meta_documents_planted_kernel(ran):
    _, meta, _ = ran
    pk = meta["planted_kernel"]
    assert pk["kernel"].startswith("g1 * lag^-gamma")
    assert pk["L_planted"] > 0
