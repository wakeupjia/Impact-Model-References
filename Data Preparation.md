# L3 Take–Wait — Data Preparation

Companion to [[L3 Take-Wait Training Guide]] · [[Market Impact - Three Layers]].

## 1. Goal

From trades + quotes → event table → short-horizon $I_0(q)=a q^b$ and response $R(\ell)$ (then $\hat G$).

## 2. Inputs

- Trades: $(t,\ \mathrm{price},\ \mathrm{size})$
- Quotes: $(t,\ \mathrm{bid},\ \mathrm{ask})$ or mid — same clock, same symbol
- Optional: ADV, spread bucket, TOD, $\sigma$ for $q/\mathrm{ADV}$ and stratification

---

## 3. Sample size

- Use **all** continuous-session takes after filters (sweep-merged). No per-day random cap.
- **MVP:** **1 symbol**; **10–20** trading days; land about **2k–5k** events; first $R(\ell)$ only — no $\rho$ claim.
- **Size groups:** see pipeline step 7 (5 quintiles of $q$; $\gtrsim 50$ events/bin when possible).
- **Full:** stretch toward **1–3 months**; $\gtrsim 10^4$ events for solid $I_0$; $10^5+$ for nonparametric $G$ / TIM invert.
- Pass bar: $I_0$ exponent $b$ about 0.3–0.8 and stable on a half-sample split.

---

## 4. Pipeline (in order)

1. **Session clean** — drop auction + first/last ~10 minutes; drop crossed / locked books and bad clocks.
2. **Quote match + sign** — last quote with $t_{\mathrm{quote}} < t_{\mathrm{trade}}$ (strict). Price at/above ask → $\varepsilon=+1$; at/below bid → $\varepsilon=-1$. Mid $m^-$. *[MVP: no “quote age $<1\,\mathrm{s}$” keep-filter.]*
3. **Sweep merge** — same-side same-ms (or contiguous same-side walk) → one event $(t_n,\varepsilon_n,q_n,m_n^-)$ with $q=\sum$ sizes.
4. **As-of mid** — mid at time $u$ = last quote/mid with timestamp $\le u$. Piecewise constant; no 1 ms poll loop.
5. **Keep later prints** in every markout path. *[MVP and full: do not drop when another trade arrives before the horizon.]*
6. **$I_0$ labels** — primary $h=1\,\mathrm{s}$ (also **record** $y$ at $100\,\mathrm{ms}$ for a check):
   $$y=\varepsilon\cdot\frac{m(t_n+h)-m_n^-}{m_n^-}\cdot 10^4\ \text{(bps)}$$
7. **$I_0$ fit** — sort by $q$ (or $q/\mathrm{ADV}$), split into **5 quintiles** (smallest 20% … largest 20%); mean $y(1\,\mathrm{s})$ in each; regress the 5 points: $\log y \approx \log a + b\log q$. Aim $\gtrsim 50$ events per quintile when possible.
8. **Response $R$** — **trade time** preferred:
   $$R(\ell)=\mathrm{mean}_n\bigl[\varepsilon_n\cdot(m_{n+\ell}^- - m_n^-)\bigr]$$
   Lags $\ell\in\{1,2,5,10,20,50,100,200,\ldots\}$. MVP: stop around 200. Full: through the rise $\ell^\star\sim 100$–$1000$ and a bit beyond.
9. **Normalize** — means only: $\hat G(\ell)=R(\ell)/R(1)$ (or small $\ell_0$). *[MVP: skip $e^{-\rho\tau}$ fit. Full: empirical / power-law $G$; optional sign-ACF + TIM invert (Taranto) for bare $G$; exponential only as a local diagnostic.]*
10. **Optional** — calendar grid $\{1,5,30,120\}\,\mathrm{s}$ for plots; index residual at $\ge 30\,\mathrm{s}$ only.

---

## 5. Outputs

- `events.parquet` — one row per take event + $y(h)$
- `i0_buckets.csv` / `i0_fit.json` — bucket means + $(a,b)$
- `R_trade_time.csv` — $R(\ell)$, $\hat G(\ell)$
- Short note: $n$ events, date range, symbols

---

## 6. Do not

- Quote-age $<1\,\mathrm{s}$ keep-filter
- Stop the path at the next trade
- Normalize with medians when medians are 0
- Claim $\rho$ from $n\sim 10^2$ or rising raw $R$

---

## 7. Why $R$ often rises

Dressed response keeps later same-sign flow, so mean signed mid move can climb for many trades before a slow fall. That is expected (Bouchaud et al. 2004). Bare $G$ still decays; recover it via deconvolution when you leave MVP.

---

## 8. Refs

- Bouchaud et al. (2004) — [[papers/bouchaud-2004.pdf]] · [arXiv](https://arxiv.org/abs/cond-mat/0307332)
- Taranto et al. (2016) — [arXiv:1602.02735](https://arxiv.org/abs/1602.02735)
- Tóth–Eisler–Bouchaud (2017) — [arXiv:1702.08029](https://arxiv.org/abs/1702.08029)
- Fit steps after this prep: [[L3 Take-Wait Training Guide]]
