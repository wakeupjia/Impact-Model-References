# L3 Take–Wait Model — Training Guide (sourced)

Companion to [[Market Impact - Three Layers]] · data prep [[Data Preparation]] · sim [[L3 Take-Wait Simulator Guide]].  
## 0. Model you are training

$$
C_{\text{take}} = W(q) + S_t + I_0(q)
$$
$$
q'(\tau)=\min\big(q_{\max},\, q + v^\star\tau + \kappa_L L_t\big)
$$
$$
C_{\text{wait}}(\tau)=\lambda\sigma^2 Q^2\tau + W(q') + S_t G(\tau) + I_0(q')
$$

**Take** if $C_{\text{take}} \le C_{\text{wait}}(\tau)$.

| Piece                  | What it means                                                     | Train from data?          | Source of method                                                   |
| ---------------------- | ----------------------------------------------------------------- | ------------------------- | ------------------------------------------------------------------ |
| $W(q)$                 | Mechanical take cost                                              | No — live book            | Cont–Kukanov take/cross cost                                       |
| $I_0(q)$               | Immediate mid impact of this take of size $q$ (power law $a q^b$) | **Yes**                   | Almgren et al. (2005) style markouts; propagator literature        |
| $G(\tau)$              | Remaining **own** dent fraction after wait $\tau$ (bare $G_0$)   | **Yes**                   | Taranto et al. (2016) TIM1; Bouchaud et al. (2004); Gatheral (2010) |
| $S_t$                  | Leftover mid dent from earlier **own** takes in this parent       | Live state using $I_0,G_0$ | TIM age-resolved residual; OW exponential as special case only    |
| $q'(\tau)$             | Larger size you may need after waiting $\tau$ (catch-up / lag)    | No — schedule math        | Cont–Kukanov catch-up / execution risk                             |
| $\lambda$ (or $\beta$) | Urgency: how much you hate waiting with parent $Q$ left           | Knob (optional light fit) | Almgren–Chriss (2001) risk aversion                                |

### 2.1 Dataset (minimum)

Schema of the markout table after [[Data Preparation]].

| Field           | Example                                          | Notes               |
| --------------- | ------------------------------------------------ | ------------------- |
| `q`             | shares                                           |                     |
| `mid_before`    | mid just before take                             |                     |
| `mid_at_lag[h]` | mid at lags $h\in\{0.2,1,5,30,120\}$ s           | same lag set always |
| optional        | spread, $\sigma$ bucket, TOD, ADV, participation | for stratification  |

Parent side (for $q'$, wait-risk): remaining $Q$, time left, target curve $X^\star(t)$ so you can compute $v^\star$ and lag $L_t$.
LOB snapshots (or reconstructable book) at decision time for $W(q)$.
Data preparation (tape → events, horizons, sample size): [[Data Preparation]].

### 2.2 Train $I_0(q)$

$I_0(q)$ is **immediate impact of taking size $q$** — how much mid is expected to move right after that take, in bps. Fit as $a q^b$ from short-horizon markouts.

**Method (Almgren et al. 2005 style + short-horizon propagator response):**
1. For each take $i$, pick short horizon $h$ (e.g. 0.2–1 s):
   $$y_i = \text{side}_i \cdot \frac{\text{mid}_{t_i+h}-\text{mid}_{t_i-}}{\text{mid}_{t_i-}}\cdot 10^4 \quad\text{(bps)}$$
2. Fit power-law $I_0(q)=a\,q^{b}$ (Almgren 2003/2005) 
	- Fit per stock when there are enough takes; pool similar names (ADV / spread bucket) when thin. Size often as $q/\text{ADV}$.
	- Regress $\log y$ on $\log q$: $\log y \approx \log a + b\log q$
		- That is linear regression in log space
	- Size buckets (optional denoise)
		- Put takes with similar $q$ (or $q/\text{ADV}$) in the same bin.
		- In each bin take median $y$ 
		- Median kills noise in single-take $y_i$. Your $q$ stays the real take size;
3. Optionally residualize market return over $[t,t+h]$ (Bouchaud-style).
Do not use metaorder square-root over full day as child $I_0$ (different horizon — Tóth et al. / parent metaorder literature).

### 2.3 Train bare $G_0$ (own-dent decay) — **not** $R/R$

Prep and trade-time lags: [[Data Preparation]]. **Do not** set $G=R(\cdot)/R(h)$. Raw mean response $R$ is **dressed** (impact + correlated future flow + liquidity); it often **rises** at short lags then falls. Bare $G_0$ is recovered by deconvolving $R$ with the sign autocorrelation $C$ (Taranto TIM1; Bouchaud 2004).

**What this $G$ is for in $C_{\mathrm{wait}}$:** remaining fraction of **your** past takes’ mechanical dent. It does **not** need future public trades at decision time. It is **not** the half-life of micro-alpha $S^{\mathrm{alpha}}$ and **not** the expected mid path while waiting (that needs $\mathbb{E}[\varepsilon^{\mathrm{pub}}\mid X]$ separately, if you want it).

**Method (Taranto et al. 2016 TIM1; Bouchaud et al. 2004):**

1. **Tape (one small-tick symbol first).** For each trade $n$: mid **just before** the trade $m_n$, aggressor sign $\varepsilon_n\in\{+1,-1\}$ (Lee–Ready). Index lags $\ell$ in **trade count**, not seconds. Cap $L$ (e.g. 200–300) with enough trades ($N\gg L$).

2. **Estimate** (means over $n$):
   $$C(0)=1,\quad C(\ell)=\mathbb{E}[\varepsilon_{n+\ell}\varepsilon_n]\quad(\ell=1,\ldots,L)$$
   $$R(\ell)=\mathbb{E}\big[(m_{n+\ell}-m_n)\varepsilon_n\big]\quad(\ell=1,\ldots,L)$$
   (freeze units: price ticks or bps of $m_n$). Rising $R$ is expected — keep it; do not force $G_0$ to rise with it.

3. **Invert TIM1 for bare $G_0$** (signs-only MVP). Taranto:
   $$R(\ell)=\sum_{0<n\le\ell} G_0(n)\,C(\ell-n)+\sum_{n>0}\big[G_0(n+\ell)-G_0(n)\big]C(n)$$
   with $G_0(k)=0$ for $k>L$. In matrix form ($1$-based $\ell,j=1..L$):
   $$A_{\ell j}=\mathbf{1}_{j\le\ell}\,C(\ell-j)+\mathbf{1}_{j>\ell}\,C(j-\ell)-C(j),\qquad R=AG_0.$$
   Solve $G_0=A^{-1}R$ (or least squares). Prefer Taranto’s **differential** form when boundary bias shows: $\Sigma(\ell)=\mathbb{E}[r_{n+\ell}\varepsilon_n]$, $\Gamma(\ell)=G_0(\ell+1)-G_0(\ell)$, invert $\Sigma=\Gamma*C$, then $G_0(\ell)=\sum_{i<\ell}\Gamma(i)$. Tiny ridge only if reconstructed $\tilde R=AG_0$ still tracks $R$ on a holdout. **Do not** force $G_0$ monotone (short lags can be flat / briefly up). Optional power-law fit on the stable part: $G_0(\ell)\propto\ell^{-\beta}$ with $\beta\sim0.2$–$0.5$.

4. **Live multiplier for one child of age $\ell$ trades:**
   $$g(\ell)=\frac{G_0(\ell)}{G_0(1)}$$
   (or $(G_0(\ell)-G_\infty)/(G_0(1)-G_\infty)$ if you keep a plateau). **Not** $\sum_{k\ge\ell}G_0/\sum G_0$. Map calendar wait $\Delta t\to\hat\ell=\mathrm{round}(\hat\lambda_t\Delta t)$ with local trade intensity.

5. **Gatheral (2010) check:** concave $I_0$ + ultra-fast pure exponential resilience can be inconsistent — prefer the nonparametric / power-law $G_0$ table; treat $e^{-\rho\tau}$ as a **local OW diagnostic** only.

6. **Artifacts:** save $G_0[1..L_{\mathrm{keep}}]$, $g(\ell)$, $C$, $R$, reconstruct plot, fit window, $n$ trades. Fit $I_0(q)$ on calendar $h=1\,\mathrm{s}$ **separately** (§2.2); match scales so $I_0$ and $G_0(1)$ live in the same units as $S$.

### 2.4 Live $S_t$ — **TIM own-dent residual** (OW exponential = special case only)

No separate regression. Keep an **age buffer** of own children (true TIM):

- order start: empty buffer; $S=0$
- on take $q$: append $(\mathrm{age}=1,\,I_0(q))$; $S\leftarrow\sum_i I_0(q_i)\,G_0(\mathrm{age}_i)/G_0(1)$
- each trade-time tick (or after mapping $\Delta t\to\hat\ell$): increment ages; recompute $S$ the same way
- in $C_{\mathrm{wait}}(\tau)$: use $S(\tau)=\sum_i I_0(q_i)\,G_0(\mathrm{age}_i+\hat\ell(\tau))/G_0(1)$ in place of the scalar $S_t G(\tau)$ when ages differ

**OW special case only:** if you force $G(\tau)=e^{-\rho\tau}$, then a single scalar $S\leftarrow S\cdot G(\Delta t)$ is exact (age-independent). Do not use that scalar multiply with a power-law / nonparametric $G_0$.

### 2.6 $q'(\tau)$ — **Cont–Kukanov catch-up (schedule)**

Not an impact model:
$$q' = q + v^\star\tau + \kappa_L L_t$$
- $v^\star$ from parent curve (TWAP/POV/AC path)
- $L_t=\max(0,X^\star(t)-X_{\text{done}})$
- Cont–Kukanov: unfilled limit quantity is caught up at worse expected cost → larger later marketable size

### 2.7 $\lambda\sigma^2 Q^2\tau$ — **Almgren–Chriss knob**

- $\sigma$: same vol you use in TCA  
- $Q$: **parent** shares left (not child $q$)  
- $\lambda$: risk aversion — **sweep**; AC do not “MLE-fit” $\lambda$ on one month of IS  

Optional $\beta\sigma\sqrt{\tau}$: light ratio of adverse mid move over wait gaps to $\sigma\sqrt{\tau}$, still treat as tunable.

---

## 3. Step-by-step training runbook

1. Prep tape → take events ([[Data Preparation]]); export take-markout dataset (fields in §2.1).  
2. Fit $I_0(q)$ (§2.2); save artifact + plots (bps vs size).  
3. Fit bare $G_0$ via $R$–$C$ TIM1 (§2.3); save $G_0$, $g(\ell)=G_0(\ell)/G_0(1)$; reconstruct-$R$ check; Gatheral sanity.  
4. Unit-test $W(q)$ on recorded books.  
5. Simulate $S_t$ path on historical parents.  
6. Wire parent $X^\star\to v^\star,L_t,q'$.  
7. Offline replay: at each child decision, compute $C_{\text{take}},C_{\text{wait}}$; log decisions.  
8. Sweep $\lambda,\kappa_L$ only; freeze $I_0,G$.  
9. Score **parent** IS, leftover, participation.  
10. Paper trade → A/B.  
11. Later upgrade: OW target $D^\star$ / take-the-refill ([[papers/obizhaeva-wang-2013.pdf]]).
12. Compose decision + simulator hooks: [[L3 Take-Wait Simulator Guide]].

---

## 5. Source

- AC risk on remaining $Q$  
- Cont–Kukanov catch-up $q'$  
- Propagator TIM $I_0,G_0,S_t$ (OW exponential optional)  

| Paper                                                                                                          | Why we use it                                                               | Link                                                                                                                              | Local PDF                                                  |
| -------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| Almgren & Chriss (2001), *Journal of Risk* 3(2), 5–39. “Optimal execution of portfolio transactions.”          | Timing / inventory risk $\sim\lambda\sigma^2$; parent urgency               | [DOI](https://doi.org/10.21314/jor.2001.041) · [working-paper PDF](https://www.smallake.kr/wp-content/uploads/2016/03/optliq.pdf) | [[papers/almgren-chriss-optliq.pdf]] (Dec 2000 WP)         |
| Almgren (2003), *Applied Mathematical Finance* 10(1), 1–18. Optimal execution with nonlinear temporary impact. | Waiting → larger/faster later clip costs more (convex temp impact)          | [DOI](https://doi.org/10.1080/135048602100056)                                                                                    | **Not downloaded** (paywall / no OA PDF from this machine) |
| Almgren, Thum, Hauptmann, Li (2005). “Direct Estimation of Equity Market Impact.”                              | How to **estimate** impact from trade data (size / participation)           | [Risk.net](https://www.risk.net/derivatives/structured-products/1500270/equity-market-impact)                                     | **Not downloaded** (publisher)                             |
| Obizhaeva & Wang (2013), *J. Financial Markets* 16(1), 1–32.                                                   | $D_t$ / resilience $\rho$; do not wait until dent $=0$; block–trickle–block | [DOI](https://doi.org/10.1016/j.finmar.2012.09.001) · [MIT PDF](https://web.mit.edu/wangj/www/pap/ObizhaevaWang13.pdf)            | [[papers/obizhaeva-wang-2013.pdf]]                         |
| Alfonsi, Fruth & Schied (2010), *Quantitative Finance* 10(2), 143–157.                                         | Closed-form resilient-book sibling of OW                                    | [DOI](https://doi.org/10.1080/14697680802595700) · [arXiv](https://arxiv.org/abs/0708.1756)                                       | [[papers/alfonsi-fruth-schied-2010.pdf]]                   |
| Bouchaud, Gefen, Potters, Wyart (2004), *Quantitative Finance* 4(2), 176–190.                                  | Dressed $R$ vs bare $G_0$; long-memory signs; **not** $G=R/R$               | [DOI](https://doi.org/10.1088/1469-7688/4/2/007) · [arXiv](https://arxiv.org/abs/cond-mat/0307332)                                | [[papers/bouchaud-2004.pdf]]                               |
| Taranto, Bormetti, Bouchaud, Lillo, Tóth (2016). Linear models for the impact of order flow I.                  | TIM1 $R$–$C$–$G_0$ identity + calibration (prefer differential form)       | [arXiv](https://arxiv.org/abs/1602.02735) · *Quant. Finance* 18:903–915 (2018)                                                   | Download to `papers/` if missing                           |
| Gatheral (2010), *Quantitative Finance* 10(7), 749–759. “No-dynamic-arbitrage and market impact.”              | Which $(I_0,G)$ pairs are legal                                             | [DOI](https://doi.org/10.1080/14697680903373692) · [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1292353)            | **Not downloaded** (SSRN/DOI blocked here)                 |
| Gatheral, Schied, Slynko (2012), *Mathematical Finance*                                                        | Transient impact optimal trajectories                                       | [DOI](https://doi.org/10.1111/j.1467-9965.2011.00478.x) · [arXiv](https://arxiv.org/abs/1008.1622)                                | [[papers/gatheral-schied-slynko-2012.pdf]]                 |
| Cont & Kukanov (2017), *Quantitative Finance* 17(1), 21–39. “Optimal order placement in limit order markets.”  | Catch-up cost of unfilled; take vs limit; schedule↔child split              | [DOI](https://doi.org/10.1080/14697688.2016.1190030) · [arXiv](https://arxiv.org/abs/1210.1625)                                   | [[papers/cont-kukanov-2017.pdf]]                           |
| Guéant, Lehalle, Fernandez-Tapia (2012), *SIAM J. Financial Math.*                                             | Reservation / intensity control (optional overlay)                          | [DOI](https://doi.org/10.1137/110850475) · [arXiv](https://arxiv.org/abs/1106.3279)                                               | [[papers/gueant-lehalle-2012.pdf]]                         |

Start: [[papers/obizhaeva-wang-2013.pdf]] for state + refill intuition, then Cont–Kukanov PDF for catch-up / child placement.