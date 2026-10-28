# Bare \(G_0\) (TIM1) — Junior step-by-step

Companion to [[L3 Take-Wait Training Guide]] · [[Data Preparation]] · papers [[papers/bouchaud-2004.pdf]] · [Taranto et al. arXiv:1602.02735](https://arxiv.org/abs/1602.02735).

**What this file is:** exact data → \(C\) → \(R\) → bare \(G_0\) → live own-dent \(S\) so a junior with no market-impact background can implement.  
**What this file is not:** full take/wait decision engine (that is the Training Guide). First code drop = this pipeline + age-buffer \(S\).

---

## 0. Plain-English picture (read once)

1. Every aggressive trade pushes mid a little. That push **does not vanish instantly**; a fraction remains after later trades. Call the leftover shape the **bare propagator** \(G_0\).
2. What you **measure** on tape is the **dressed response** \(R(\ell)\): “after a buy, how much has mid moved \(\ell\) trades later on average?” \(R\) mixes (a) bare impact, (b) later same-sign public flow, (c) leftover of earlier correlated flow. \(R\) often **rises** then falls. That rise is **not** “impact growing.”
3. To get bare \(G_0\), also measure sign autocorrelation \(C(\ell)=\mathbb{E}[\varepsilon_{n+\ell}\varepsilon_n]\), then **invert** the TIM1 linear map \(R = A G_0\) (Taranto). Never set \(G = R/R(1)\) for production own-dent.
4. In take/wait, \(S_t G(\tau)\) is **only the decay of your past takes’ mid dent**. Future public trades during a simulated wait are **not** part of that term. Mid-path / micro-alpha is a separate object \(\mathbb{E}[\varepsilon^{\mathrm{pub}}\mid X]\) if you want it later.

**Verdict for our model (research, 2026-10-28):**

| Question | Answer |
| --- | --- |
| OK to use bare \(G_0\) for wait cost while ignoring future public \(\varepsilon\)? | **Yes** — that is what deconvolution is for (Bouchaud 2004; Gatheral 2010 own-execution kernel = bare \(G\)). |
| OK to ignore own-trade-induced same-side follow-on? | **Qualified yes** for a small anonymous child: induced copy-cat lives in \(C_{\mathrm{you,mkt}}\), not in \(G_0\), and typically reverts ~10 trades (Tóth–Eisler–Bouchaud arXiv:1702.08029). Do **not** claim it is zero for a large/visible child or a 1–10-trade P&L budget. |

---

## 1. Scope lock for first implementation (@SWE)

| # | Decision |
| --- | --- |
| 1 | **TIM1 bare \(G_0\)** (Training Guide §2.3). Do **not** ship MVP \(R/R(1)\) as \(G\). Optional: also plot \(R/R(1)\) as a diagnostic only. |
| 2 | **Scope:** mock tape → events → \(I_0(q)\) + \(C,R,G_0,g\) artifacts + **age-buffer live \(S\)**. Stub \(q'(\tau)\) and full \(C_{\mathrm{take}}\) vs \(C_{\mathrm{wait}}\) (or omit). |
| 3 | **One symbol / one day mock OK** for a runnable pipeline; fits will be noisy. Document \(N\) and \(L\). |
| 4 | **\(W(q)\):** stub from BBO walk (`bsize`/`asize`) or skip; do not block on depth. |
| 5 | **HK fields:** ignore `tradetype` / `salescond` / `realtrade` for v1. Sign = Lee–Ready vs last quote with \(t_{\mathrm{quote}} < t_{\mathrm{trade}}\). |

Repo folder suggestion: `Impact-Model-References/g0-tim1/` (code + `data/` mock + `artifacts/`).

---

## 2. Inputs (exact columns)

**Trades**

| Column | Type | Notes |
| --- | --- | --- |
| `date` | date | session date |
| `sym` | str | e.g. `1347.HK` |
| `exchtime` | timestamp / ns | exchange time |
| `price` | float | trade price |
| `size` | int | shares |
| `realtrade`, `tradetype`, `salescond` | any | **ignore in v1** |

**Quotes (BBO)**

| Column | Type | Notes |
| --- | --- | --- |
| `date`, `sym`, `exchtime` | | same clock as trades |
| `bid`, `ask` | float | |
| `bsize`, `asize` | int | top size only |

---

## 3. Data preparation (ordered steps)

Do these **in order**. Match [[Data Preparation]] except: after \(R\), you **invert** for \(G_0\) (not normalize \(R/R(1)\) as \(G\)).

### Step A — Session clean

1. Keep continuous session only (HK cash: typically drop auction + first/last ~10 minutes of the continuous session you use).
2. Drop crossed/locked quotes (`bid >= ask`) and rows with missing bid/ask/price/size.
3. Sort trades and quotes by `exchtime` ascending. One symbol.

### Step B — Mid and Lee–Ready sign

For each trade \(i\) at time \(t_i\):

1. Find last quote with `exchtime` **strictly before** \(t_i\).
2. Mid just before trade:
   \[
   m_i^- = \frac{\mathrm{bid}+\mathrm{ask}}{2}.
   \]
3. Sign \(\varepsilon_i \in \{+1,-1\}\):
   - `price >= ask` → \(\varepsilon = +1\) (buy aggressor)
   - `price <= bid` → \(\varepsilon = -1\) (sell aggressor)
   - else (inside): \(\varepsilon = +1\) if `price > m^-`, else \(-1\) (tie: carry previous \(\varepsilon\), or drop — **pick one and document**; recommended: drop inside-spread prints for v1 if rare).

**Paper default:** mid is **just before** the trade (Taranto). Freeze this forever.

### Step C — Sweep merge

Merge same-side prints that are the same millisecond (or contiguous same-side walk with no opposing print):

- Keep one event: \(t_n =\) first time, \(\varepsilon_n =\) shared sign, \(q_n = \sum\) sizes, \(m_n^- =\) mid before first print of the sweep.

Output event table columns: `n` (0-based trade index), `t`, `eps`, `q`, `mid_before`.

### Step D — As-of mid at later trade indices

For trade-time lag \(\ell\), mid at event \(n+\ell\) means \(m_{n+\ell}^-\) (mid **before** trade \(n+\ell\)), from the event table. Do **not** stop the path when another trade arrives.

### Step E — Calendar markouts for \(I_0\) (separate from \(G_0\))

Primary horizon \(h = 1\,\mathrm{s}\) (also record \(100\,\mathrm{ms}\) as a check):

\[
y_i = \varepsilon_i \cdot \frac{m(t_i+h) - m_i^-}{m_i^-} \cdot 10^4 \quad \text{(bps)}
\]

where \(m(t_i+h)\) = last mid with quote time \(\le t_i+h\).

---

## 4. Train \(I_0(q) = a q^b\)

1. Keep events with finite \(y(1\,\mathrm{s})\).
2. Sort by \(q\) (or \(q/\mathrm{ADV}\) if ADV known). Split into **5 quintiles**.
3. In each quintile: median or mean \(y\) (Training Guide uses log-regression on bucket means; prefer **median** inside bin if noisy).
4. Regress the 5 points: \(\log y \approx \log a + b \log q\).
5. Save `i0_fit.json`: `{a, b, n, buckets...}`.

One day of mock data → expect noisy \(b\). Pipeline must still run.

---

## 5. Estimate \(C(\ell)\) and \(R(\ell)\) in **trade time**

Let \(N\) = number of merged events. Choose max lag \(L\) with \(N \gg L\) (e.g. \(L=50\)–\(200\) on one day if \(N\) allows; else shrink \(L\)).

For \(\ell = 0,\ldots,L\):

\[
C(0) = 1, \qquad
C(\ell) = \frac{1}{N-\ell}\sum_{n=0}^{N-\ell-1} \varepsilon_{n+\ell}\varepsilon_n \quad (\ell\ge 1)
\]

\[
R(\ell) = \frac{1}{N-\ell}\sum_{n=0}^{N-\ell-1} (m_{n+\ell}^- - m_n^-)\,\varepsilon_n \quad (\ell\ge 1)
\]

**Units:** pick **one** and freeze: price currency, ticks, or bps of \(m_n^-\). Same units must be used for \(G_0\) and for matching \(I_0\) into \(S\).

**Do not** force \(R\) to be decreasing. Rising \(R\) at short lags is expected.

Save `C.csv`, `R.csv`.

---

## 6. Invert TIM1 for bare \(G_0\) (core)

Taranto TIM1 (signs-only):

\[
R(\ell)=\sum_{0<n\le\ell} G_0(n)\,C(\ell-n)+\sum_{n>0}\bigl[G_0(n+\ell)-G_0(n)\bigr]C(n)
\]

with \(G_0(k)=0\) for \(k>L\).

### 6.1 Matrix form (1-based \(\ell,j = 1..L\))

\[
A_{\ell j}
=
\mathbf{1}_{j\le\ell}\,C(\ell-j)
+
\mathbf{1}_{j>\ell}\,C(j-\ell)
-
C(j)
\]

\[
R = A G_0
\qquad\Rightarrow\qquad
G_0 = A^{-1} R
\]

(or least squares if you over-determine). Implement `A` explicitly; do **not** invent a lag-by-lag “peel.”

**Reference code (calibration, not a black box to copy blindly):** [felixpatzelt/priceprop](https://github.com/felixpatzelt/priceprop) `calibrate_tim1` (+ [scorr](https://github.com/felixpatzelt/scorr)). Prefer reimplementing the matrix above so unit tests are transparent.

### 6.2 Preferred numerical path when \(A\) is ill-conditioned (Taranto)

Differential form:

\[
\Sigma(\ell)=\mathbb{E}[r_{n+\ell}\varepsilon_n],\quad
r_n = m_{n+1}^- - m_n^-,
\quad
\Gamma(\ell)=G_0(\ell+1)-G_0(\ell)
\]

Invert \(\Sigma = \Gamma * C\) (convolution), then

\[
G_0(\ell)=\sum_{i<\ell}\Gamma(i)
\]

(with \(G_0(0)=0\) or convention \(G_0(1)\) = first positive level — **document**: we take \(G_0(1)\) as impact after one trade step as in integrated kernel).

Tiny ridge on \(A\) **only if** reconstructed \(\tilde R = A G_0\) still tracks holdout \(R\). Do **not** force \(G_0\) monotone.

### 6.3 Live multiplier

\[
g(\ell)=\frac{G_0(\ell)}{G_0(1)}
\]

**Not** \(\sum_{k\ge\ell} G_0(k)/\sum G_0\).

Optional: fit \(G_0(\ell)\propto \ell^{-\beta}\) on the stable tail (\(\beta\sim 0.2\)–\(0.5\)) for plots only; production table stays nonparametric.

### 6.4 Calendar wait → trade lag

\[
\hat\ell(\tau)=\mathrm{round}(\hat\lambda_t\,\tau)
\]

\(\hat\lambda_t\) = recent trades per second (e.g. trailing 1–5 min). Clamp to \([1,L_{\mathrm{keep}}]\).

### 6.5 Worked toy (5 trades, \(L=2\))

Tiny tape so every average is hand-checkable. Units = mid price points. Signs \(\varepsilon\in\{+1,-1\}\).

| \(n\) | \(\varepsilon_n\) | \(m_n^-\) |
| --- | --- | --- |
| 0 | \(+1\) | 100.00 |
| 1 | \(+1\) | 100.05 |
| 2 | \(+1\) | 100.03 |
| 3 | \(-1\) | 100.11 |
| 4 | \(+1\) | 100.03 |

**Sign autocorrelation** \(C(\ell)=\frac1{N-\ell}\sum_n\varepsilon_n\varepsilon_{n+\ell}\), \(C(0)=1\):

- \(\ell=1\): products \(+1,+1,-1,-1\) → \(C(1)=0\)
- \(\ell=2\): products \(+1,-1,+1\) → \(C(2)=\tfrac13\)

**Response** \(R(\ell)=\frac1{N-\ell}\sum_n (m_{n+\ell}^--m_n^-)\varepsilon_n\):

| \(\ell\) | pairs \((m_{n+\ell}^--m_n^-)\varepsilon_n\) | \(R(\ell)\) |
| --- | --- | --- |
| 1 | \(0.05,\;-0.02,\;0.08,\;0.08\) | \(0.0475\) |
| 2 | \(0.03,\;0.06,\;0\) | \(0.03\) |

**Design \(A\)** from §6.1 with this \(C\):

\[
A=\begin{pmatrix}1 & -\tfrac13\\ 0 & \tfrac23\end{pmatrix}
\qquad
R=\begin{pmatrix}0.0475\\ 0.03\end{pmatrix}
\qquad
\hat G_0=A^{-1}R=\begin{pmatrix}0.0625\\ 0.045\end{pmatrix}
\]

Live multiplier: \(g(1)=1\), \(g(2)=\hat G_0(2)/\hat G_0(1)=0.72\).

Check: \(A\hat G_0=R\) exactly on this toy (square \(L\times L\)). On real tape use holdout \(R^2\) (§8), not in-sample alone.

**Cost note (fit vs live):** calibration is one \(L\times L\) solve (\(L\sim 50\)–\(200\)), independent of how many trades the day has. Live \(S\) (§7) is a sum over **your open takes in the age buffer**, each one multiply by table \(g(\mathrm{age})\) — not an \(N_{\mathrm{day}}\times N_{\mathrm{day}}\) matrix per decision.

---

## 7. Live own-dent \(S\) (age buffer)

No separate regression.

- Parent start: empty buffer; \(S=0\).
- On own take of size \(q\): append `(age=1, impact=I_0(q))` using the **same units** as \(G_0\).
- After each public trade (or after mapping \(\Delta t\to\hat\ell\)): `age += 1` for every buffer entry; drop ages \(> L_{\mathrm{keep}}\).
- Residual dent (buffer length = number of **your** children still younger than \(L\), typically ≪ day trade count):
  \[
  S = \sum_i I_0(q_i)\,\frac{G_0(\mathrm{age}_i)}{G_0(1)}.
  \]
- For a candidate wait \(\tau\):
  \[
  S(\tau)=\sum_i I_0(q_i)\,\frac{G_0(\mathrm{age}_i+\hat\ell(\tau))}{G_0(1)}.
  \]

**OW exponential** \(e^{-\rho\tau}\) scalar multiply is **special case only** (age-independent). Do not scalar-multiply a power-law / table \(G_0\).

---

## 8. Evaluation (OLS-style — this is how we score TIM1)

TIM1 is **not** ML-trained. Same family as OLS: outcome \(R\), design \(A(C)\), coefficients \(G_0\). Score **how well \(A\hat G_0\) matches empirical \(R\)**, not mid-move hit rate.

### 8.1 Empirical \(R\) (data, not model)

\[
R(\ell)=\frac{\mathbb{E}\!\big[\varepsilon_n\,\Delta x_{n+\ell}\big]}{\mathbb{E}\!\big[\varepsilon_n\,\varepsilon_n\big]}
\approx \frac{\sum_n \varepsilon_n\,\Delta x_{n+\ell}}{\sum_n \varepsilon_n^2},\qquad \ell=1..L
\]

\(\varepsilon_n=\pm1\) trade sign; \(\Delta x_{n+\ell}\) mid change over the next \(\ell\) trades (same units as the fit). Vector \(R\in\mathbb{R}^L\).

### 8.2 Design \(A\) and prediction

Build \(A\) from measured \(C\) exactly as in the TIM1 solve (same matrix used for \(G_0=A^{-1}R\) / differential form). Then:

\[
\tilde R := A\,\hat G_0,\qquad e := R-\tilde R
\]

### 8.3 Metrics (write into `run_meta.json`)

| key | formula |
| --- | --- |
| `sse` | \(e^\top e\) |
| `r2` | \(1-\dfrac{e^\top e}{(R-\bar R)^\top(R-\bar R)}\) |
| `rmse` | \(\sqrt{e^\top e\,/\,L}\) |
| `R_vs_Rhat_corr` | \(\mathrm{corr}(R,\tilde R)\) |

Also keep: `G0_1`, primary solver name, \(N\), \(L\), units.

### 8.4 In-sample vs holdout

1. **In-sample:** fit \(C,R,G_0\) on full (or train) tape; score \(\tilde R=A\hat G_0\) vs that same \(R\).
2. **Holdout:** split days (or morning/afternoon / first `train_frac` events). Fit \(\hat G_0\) on train. On test, rebuild \(A_{\mathrm{test}},R_{\mathrm{test}}\) from test tape only; score \(A_{\mathrm{test}}\hat G_0^{\mathrm{train}}\) vs \(R_{\mathrm{test}}\) with the same four metrics. Optional: \(\|\hat G_0^{\mathrm{train}}-\hat G_0^{\mathrm{test}}\|_2\).

### 8.5 Pass bars + unit tests + artifacts

1. Pass bars (soft on one-day mock): \(G_0(1)>0\); `R_vs_Rhat_corr` high (mock target \(\gtrsim 0.9\) in-sample); `r2` reported (do not hard-fail on tiny \(N\)); \(g(\ell)\) eventually decays; \(I_0\) exponent plausible if \(N\) large.
2. Unit tests (required):
   - synthetic: known \(G_0\), AR signs → recover \(G_0\); report recovery RMSE on \(G_0\) + reconstruct `r2`/`rmse`/`corr`
   - \(g(1)=1\)
   - age buffer: one take, advance \(\ell\), \(S\) matches \(I_0\cdot g(\ell)\)
   - eval helper: given known \(A,G_0,R=AG_0\), metrics give `r2≈1`, `rmse≈0`
3. Artifacts: `events.parquet`, `i0_fit.json`, `C.csv`, `R.csv`, `R_hat.csv`, `G0.csv`, `g.csv`, `reconstruct.png`, `run_meta.json` with §8.3 keys + holdout block if run, `README` with \(N,L\), units, mid-before convention.

---

## 9. Existing code / resources (verified 2026-10-28)

| Resource | What it gives | Caveat |
| --- | --- | --- |
| [felixpatzelt/priceprop](https://github.com/felixpatzelt/priceprop) | `calibrate_tim1`, `propagate`, `G_pow`, TIM2/HDIM2 | Research-era Py2 lineage; reimplement matrix for clarity |
| [felixpatzelt/scorr](https://github.com/felixpatzelt/scorr) | Correlation helpers for priceprop | Same |
| [screamer Propagator](https://screamer.readthedocs.io/en/stable/functions_micro/Propagator.html) | Power-law convolution only | **No** \(R\)–\(C\) deconvolution |
| [stochastic-rs impact](https://docs.rs/stochastic-rs-quant/latest/src/stochastic_rs_quant/microstructure/impact.rs.html) | Power-law / exp path convolution | Simulate only |
| Bouchaud et al. 2004 | [arXiv:cond-mat/0307332](https://arxiv.org/abs/cond-mat/0307332) · local [[papers/bouchaud-2004.pdf]] | Dressed \(R\) vs bare \(G_0\) |
| Taranto et al. 2016 | [arXiv:1602.02735](https://arxiv.org/abs/1602.02735) | TIM1 identity + differential form |
| Tóth–Eisler–Bouchaud | [arXiv:1702.08029](https://arxiv.org/abs/1702.08029) | Copy-cat \(C_{\mathrm{you,mkt}}\) vs universal \(G\) |
| Gatheral 2010 | no-dynamic-arbitrage; own kernel = bare \(G\) | Legal \((I_0,G)\) pairs |
| Lillo Imperial lecture PDF | [slides](https://www.imperial.ac.uk/media/imperial-college/research-centres-and-groups/cfm-imperial-institute-of-quantitative-finance/events/Lillo-Imperial-Lecture3.pdf) | Pedagogy |

---

## 10. Explicit non-goals / do-nots

- Do not set production \(G = R(\ell)/R(1)\).
- Do not use tail-sum \(\sum_{k\ge\ell}G_0/\sum G_0\) as remaining dent.
- Do not require future public trades inside the wait simulator for \(S(\tau)\).
- Do not force \(G_0\) monotone.
- Do not treat one-day mock \(b\) or \(\beta\) as production truth.

---

## 11. Handoff

@SWE: implement §1–§8 in `g0-tim1/` from this file; generate `1347.HK`-like one-day mock trades+quotes with the schema in §2; ping @Researchy for review against this guide + Bouchaud/Taranto.
