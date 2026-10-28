# g0-tim1 — Bare \(G_0\) (TIM1) first drop

Implements [G0 TIM1 Step-by-Step](../G0%20TIM1%20Step-by-Step.md) (Researchy, 2026-10-28).

## Scope (locked)

| Item | Choice |
| --- | --- |
| \(G\) | TIM1 bare \(G_0 = A^{-1} R\) (not \(R/R(1)\)) |
| Delivered | mock tape → events → \(I_0(q)\) + \(C,R,G_0,g\) + age-buffer \(S\) |
| Stubbed | \(W(q)\), \(q'(\tau)\), full \(C_{\mathrm{take}}\) vs \(C_{\mathrm{wait}}\) |
| Data | one symbol / one day mock `1347.HK` (noisy fits OK) |
| Signs | Lee–Ready vs last quote \(t_q < t_{\mathrm{tr}}\); ignore `tradetype`/`salescond`/`realtrade`; drop inside-spread |

## Conventions

- Mid = mid **just before** trade.
- Units for \(C,R,G_0\): **bps of mid** (same as \(I_0\)).
- Live multiplier \(g(\ell)=G_0(\ell)/G_0(1)\).
- Age buffer: on take append `(age=1, I0(q))`; each public trade increments ages; \(S=\sum I_0\,g(\mathrm{age})\).

## Layout

```
g0-tim1/
  g0_tim1/          # package
  data/             # mock trades/quotes
  artifacts/        # events, fits, plots
  tests/
  run.py
```

## Run

```bash
cd g0-tim1
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python run.py
.venv/bin/pytest -q
```

## Artifacts

- `artifacts/events.parquet` — merged take events + markouts
- `artifacts/i0_fit.json` — \(a,b\) + buckets + `stat_used` + caveat
- `artifacts/C.csv`, `R.csv`, `G0.csv`, `g.csv`, `R_hat.csv`
- `artifacts/G0_matrix.csv`, `artifacts/G0_differential.csv` — both inversion paths always recorded; primary = matrix if \(G_0^{mat}(1)>0\), else differential if \(G_0^{diff}(1)>0\), else matrix + warning
- `artifacts/reconstruct.png`, `artifacts/R_vs_Rhat.png`
- `artifacts/run_meta.json` — \(N,L\), units, corr(\(R,\tilde R\)), holdout metrics, planted kernel
- `artifacts/TEST_REPORT.md` + `artifacts/test_metrics.json` — metrics report (researchy checklist): synthetic recovery of known \(G_0\), corr(\(R,A\hat G_0\)), \(g(1)\)/age-buffer check, 70/30 train/holdout, one-day-mock caveat, matrix vs differential comparison

`run.py` runs the pipeline then regenerates the report. The mock tape injects a
planted power-law kernel \(G_0(\ell)=g_1\ell^{-\gamma}\) (documented in
`run_meta.json → planted_kernel`) so \(\hat G_0\) has ground truth to be judged
against.

## Non-goals

Do not treat one-day mock \(b\) as production. Do not use \(R/R(1)\) as production \(G\).
