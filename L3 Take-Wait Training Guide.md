# L3 Take–Wait Model — Training Guide (sourced)

Companion to [[Market Impact - Three Layers]].  
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
| $G(\tau)$              | Decay curve: fraction of impact dent left after wait $\tau$       | **Yes**                   | Bouchaud et al. (2004); OW resilience; Gatheral (2010) constraints |
| $S_t$                  | Leftover mid dent from earlier takes in this parent               | Live state using $I_0,G$  | OW displacement / propagator residual                              |
| $q'(\tau)$             | Larger size you may need after waiting $\tau$ (catch-up / lag)    | No — schedule math        | Cont–Kukanov catch-up / execution risk                             |
| $\lambda$ (or $\beta$) | Urgency: how much you hate waiting with parent $Q$ left           | Knob (optional light fit) | Almgren–Chriss (2001) risk aversion                                |

### 2.1 Dataset (minimum)

| Field           | Example                                          | Notes               |
| --------------- | ------------------------------------------------ | ------------------- |
| `q`             | shares                                           |                     |
| `mid_before`    | mid just before take                             |                     |
| `mid_at_lag[h]` | mid at lags $h\in\{0.2,1,5,30,120\}$ s           | same lag set always |
| optional        | spread, $\sigma$ bucket, TOD, ADV, participation | for stratification  |

Parent side (for $q'$, wait-risk): remaining $Q$, time left, target curve $X^\star(t)$ so you can compute $v^\star$ and lag $L_t$.
LOB snapshots (or reconstructable book) at decision time for $W(q)$.

### 2.15 Data preparation (tape → take events)

Each print is an aggressive take hitting a resting quote. Build the $I_0$ / $G$ sample from market trades + quotes (own fills optional for venue/routing).

- **Side:** tag buy/sell vs bid/ask (quote rule / Lee–Ready): trade at or above ask → buy take; at or below bid → sell take.
- **Sweep grouping:** a multi-level walk prints as several same-side trades in one burst (same ms / same aggressor). Merge into one event; $q$ = sum of sizes. One markout from the start of the burst.
- **Arrival mid:** mid just before the event ($\text{mid}_{t-}$).
- **Markout path:** keep mid at fixed lags $h$ (same set always; see §2.1). $y$ uses short $h$ for $I_0$; longer lags for $G$.
- **Filters:** drop crossed/locked books and bad clocks.
- **Optional residual:** subtract market return over $[t,t+h]$ so $y$ is closer to pure impact.
- **Output rows:** $(q,\,\text{side},\,\text{mid}_{t-},\,\text{mid}_{t+h},\,y)$ — this is the §2.1 take-markout dataset.
- **Waits:** queue / limit fills are a separate slice for $q'$ and live $W$; do not mix into the $I_0$ fit.

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

### 2.3 Train $G(\tau)$ <- decay of short term impact 

**Method (Bouchaud et al. 2004 propagator; OW exponential resilience as special case):**
1. Same takes; compute $y_i(\tau)$ at each lag $\tau$.
2. Normalize:
   $$\hat G(\tau)=\frac{\mathrm{median}\,y(\tau)}{\mathrm{median}\,y(h)}$$
3. Fit $G(\tau)=e^{-\rho\tau}$ (OW) or keep empirical $G$ table.
4. **Gatheral (2010) check:** concave $I_0$ + very fast exponential $G$ can violate no-dynamic-arbitrage — if $I_0$ is strongly concave, use slower $G$ on longer lags or linearize $I_0$ on the child horizon.

### 2.4 Live $S_t$ — **OW / propagator residual**
No separate regression:
- order start: $S=0$
- on take $q$: $S \leftarrow S + I_0(q)$
- each $\Delta t$: $S \leftarrow S\cdot G(\Delta t)$
Matches OW dent $D_t$ decaying at $\rho$ when $G(\tau)=e^{-\rho\tau}$.

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

1. Prep tape → take events (§2.15); export take-markout dataset (fields in §2.1).  
2. Fit $I_0(q)$ (§2.2); save artifact + plots (bps vs size).  
3. Fit $G(\tau)$ (§2.3); save $\rho$ or table; run Gatheral sanity check.  
4. Unit-test $W(q)$ on recorded books.  
5. Simulate $S_t$ path on historical parents.  
6. Wire parent $X^\star\to v^\star,L_t,q'$.  
7. Offline replay: at each child decision, compute $C_{\text{take}},C_{\text{wait}}$; log decisions.  
8. Sweep $\lambda,\kappa_L$ only; freeze $I_0,G$.  
9. Score **parent** IS, leftover, participation.  
10. Paper trade → A/B.  
11. Later upgrade: OW target $D^\star$ / take-the-refill ([[papers/obizhaeva-wang-2013.pdf]]).

---

## 5. Source

- AC risk on remaining $Q$  
- Cont–Kukanov catch-up $q'$  
- Propagator/OW $I_0,G,S_t$  

| Paper                                                                                                          | Why we use it                                                               | Link                                                                                                                              | Local PDF                                                  |
| -------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| Almgren & Chriss (2001), *Journal of Risk* 3(2), 5–39. “Optimal execution of portfolio transactions.”          | Timing / inventory risk $\sim\lambda\sigma^2$; parent urgency               | [DOI](https://doi.org/10.21314/jor.2001.041) · [working-paper PDF](https://www.smallake.kr/wp-content/uploads/2016/03/optliq.pdf) | [[papers/almgren-chriss-optliq.pdf]] (Dec 2000 WP)         |
| Almgren (2003), *Applied Mathematical Finance* 10(1), 1–18. Optimal execution with nonlinear temporary impact. | Waiting → larger/faster later clip costs more (convex temp impact)          | [DOI](https://doi.org/10.1080/135048602100056)                                                                                    | **Not downloaded** (paywall / no OA PDF from this machine) |
| Almgren, Thum, Hauptmann, Li (2005). “Direct Estimation of Equity Market Impact.”                              | How to **estimate** impact from trade data (size / participation)           | [Risk.net](https://www.risk.net/derivatives/structured-products/1500270/equity-market-impact)                                     | **Not downloaded** (publisher)                             |
| Obizhaeva & Wang (2013), *J. Financial Markets* 16(1), 1–32.                                                   | $D_t$ / resilience $\rho$; do not wait until dent $=0$; block–trickle–block | [DOI](https://doi.org/10.1016/j.finmar.2012.09.001) · [MIT PDF](https://web.mit.edu/wangj/www/pap/ObizhaevaWang13.pdf)            | [[papers/obizhaeva-wang-2013.pdf]]                         |
| Alfonsi, Fruth & Schied (2010), *Quantitative Finance* 10(2), 143–157.                                         | Closed-form resilient-book sibling of OW                                    | [DOI](https://doi.org/10.1080/14697680802595700) · [arXiv](https://arxiv.org/abs/0708.1756)                                       | [[papers/alfonsi-fruth-schied-2010.pdf]]                   |
| Bouchaud, Gefen, Potters, Wyart (2004), *Quantitative Finance* 4(2), 176–190.                                  | Propagator / response function = empirical $G$                              | [DOI](https://doi.org/10.1088/1469-7688/4/2/007) · [arXiv](https://arxiv.org/abs/cond-mat/0307332)                                | [[papers/bouchaud-2004.pdf]]                               |
| Gatheral (2010), *Quantitative Finance* 10(7), 749–759. “No-dynamic-arbitrage and market impact.”              | Which $(I_0,G)$ pairs are legal                                             | [DOI](https://doi.org/10.1080/14697680903373692) · [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1292353)            | **Not downloaded** (SSRN/DOI blocked here)                 |
| Gatheral, Schied, Slynko (2012), *Mathematical Finance*                                                        | Transient impact optimal trajectories                                       | [DOI](https://doi.org/10.1111/j.1467-9965.2011.00478.x) · [arXiv](https://arxiv.org/abs/1008.1622)                                | [[papers/gatheral-schied-slynko-2012.pdf]]                 |
| Cont & Kukanov (2017), *Quantitative Finance* 17(1), 21–39. “Optimal order placement in limit order markets.”  | Catch-up cost of unfilled; take vs limit; schedule↔child split              | [DOI](https://doi.org/10.1080/14697688.2016.1190030) · [arXiv](https://arxiv.org/abs/1210.1625)                                   | [[papers/cont-kukanov-2017.pdf]]                           |
| Guéant, Lehalle, Fernandez-Tapia (2012), *SIAM J. Financial Math.*                                             | Reservation / intensity control (optional overlay)                          | [DOI](https://doi.org/10.1137/110850475) · [arXiv](https://arxiv.org/abs/1106.3279)                                               | [[papers/gueant-lehalle-2012.pdf]]                         |

Start: [[papers/obizhaeva-wang-2013.pdf]] for state + refill intuition, then Cont–Kukanov PDF for catch-up / child placement.