## Overview

| Layer                                 | Role                      | Cadence                                         | Main question                                                                    |
| ------------------------------------- | ------------------------- | ----------------------------------------------- | -------------------------------------------------------------------------------- |
| **1. Pre-trade cost curve / surface** | Plan the parent schedule  | Once at start (and on major constraint changes) | “Given constraints, which trajectory is cheapest vs risk / urgency?”             |
| **2. Remaining-path cost (replan)**   | Update the plan mid-order | Minutes / on events                             | “With what’s left and how much time, should we speed up, slow down, or reshape?” |
| **3. Microstructure / child model**   | Print each slice          | Quote / book updates                            | “Take, join queue, cancel, or switch venue *now*?”                               |

---

## Layer 1 — Pre-trade curve

The curve is built from a **calibrated impact kernel + volume/vol assumptions**
- Typical inputs
	- Side, size $Q$, symbol features (ADV, ($\sigma$), spread, tick, liquidity bucket)
	- Horizon / deadline $T$ (soft vs **must-complete**)
	- Participation cap $\rho_{\max}$ (and maybe min)
	- Style family: VWAP / TWAP / POV / IS / backloaded / close-oriented
	- Start time / time-of-day window
	- Urgency / risk aversion $\lambda$
- Typical outputs
	- Expected IS / arrival shortfall (bps), often with a risk band
	- Recommended inventory path (schedule)
	- What-ifs ranked by predicted cost (e.g. POV 5% vs backload from 14:00)

-  How the curve is generated (high level)
	1. **Impact kernel** — maps trading $q$ in an interval to price displacement (e.g. $c\,\sigma\sqrt{q/V}$, plus temporary / decay terms).
	2. **Simulate schedules** — slice the parent along a volume curve; accumulate expected impact + spread (+ timing risk) along each path.
	3. **Sweep a lever** — vary duration / POV / start time → plot expected cost vs that lever. Optimizer picks the best feasible point.

-  quant models (Layer 1)

| Model family                                                             | Role in this layer                                                                                   |
| ------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------- |
| **Square-root law** $I \approx Y\sigma\sqrt{Q/V}$                      | Size / capacity / first-order pre-trade cost                                                         |
| **Almgren–Chriss (AC)**                                                  | Mean–variance schedule: temporary + permanent impact + risk $\lambda$; closed-form TWAP-like paths |
| **Almgren 2005-style power-in-rate** (e.g. $Q^{3/5}$ in participation) | Temporary impact as function of **trade rate** (distinct from SRL-in-total-$Q$)                    |
| **Obizhaeva–Wang**                                                       | Resilient LOB; block + trickle + block schedule                                                      |
| **Propagator / transient impact** (Gatheral, Bouchaud, etc.)             | Path cost with decay kernel $G(t-s)$; prices pauses / backloads                                    |
| **Kyle–Obizhaeva invariance**                                            | Cross-sectional prior when own-fill history is thin                                                  |
| **Hybrid metaorder + own fills** (e.g. BestEx-style)                     | Sensitivities from tape metaorders; level / spread / AS from own algo DB                             |

See also: [[Market Impact model]] for propagator discretization → QP.

---

## Layer 2 — Cost of path for remaining size (intraday replan)

-  High-level idea: Same **parent/metaorder cost model** as Layer 1, re-run with:
	- Remaining quantity $Q_{\text{left}}$
	- Time left / deadline
	- Updated $\sigma$, expected volume, maybe realized vs plan error
	- Current constraints (must-complete still on? POV cap changed?)
- **Output:** updated recommended trajectory (speed up / slow down / backload more / pause), not a brand-new model class.
-  When it fires
	- Periodic (e.g. every $N$ minutes)
	- Behind / ahead of volume curve
	- Vol spike, liquidity regime change
	- PM changes urgency or deadline
	- Predicted cost of finishing *now* vs waiting crosses a threshold

| Model family                                                | Role here                                                                      |
| ----------------------------------------------------------- | ------------------------------------------------------------------------------ |
| **Same AC / OW / propagator kernel as Layer 1**             | Re-optimize $x_t$ for remaining inventory                                    |
| **Signal-aware AC** (e.g. Cartea–Jaimungal order-flow tilt) | Tilt schedule if short-horizon alpha / expected flow updates                   |
| **Dynamic participation / POV controllers**                 | Map “behind schedule” → $\rho(t)$ within caps, using cost surface as the tax |
| **Stochastic-liquidity / uncertain-fill extensions of AC**  | Adaptive wait vs trade regions when fill risk is explicit                      |

---

## Layer 3 — Microstructure / child model

Given the **current slice size** from Layer 1–2, decide **how to print it** using the **live order book**.

| Model family                                                             | Role here                                                                                       |
| ------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------- |
| **Order-flow imbalance (OFI)** (Cont–Kukanov–Stoikov)                    | Short-horizon mid move ~ linear in touch imbalance / depth                                      |
| **Queue-position / fill-probability models**                             | Join vs take; adverse selection rises deeper in queue                                           |
| **Avellaneda–Stoikov–style reservation / indifference**                  | Market-making style quotes around reservation price (more MM than pure IS, but related toolkit) |
| **Markout / toxicity overlays** (VPIN-like, short-horizon alpha of fill) | Slow down or go passive when flow is toxic                                                      |
| **Venue / dark selection scores**                                        | Route child where expected AS + impact beat alternatives                                        |
| **LOB sim / Hawkes-LOB / queue replay**                                  | Research & backtest child policy (ABIDES for reactive; hftbacktest for queue replay)            |
| **Child temporary / propagator add-on** (markout $I_0$ + decay $G$)   | Price this take vs mid; keep running wake $S_t$ for later clips                               |

- Child cost pieces (for a take of size $q$)
	- **Book-walk** — climb the ask (buy) / bid (sell) for $q$; from live L3 depth
	- **Temporary** $I_0(q)$ — temporary push from this clip; decays with $G(\tau)$
	- **Running state** $S_t$ — sum of leftover wakes from own earlier prints still alive
	- **Permanent** — small at child size; lives more in L1–L2 parent $Q$
	-  **$\tau$** — how long you wait before re-checking
- Decision (needs a yardstick)
	- From L2: — take when $C(q) \le X$
	- Without L2, pick a yardstick: half-spread, own historical take-bps, crude remaining parent budget, or short-horizon edge
	- Else wait / join / cut $q$ (lets $S_t$ decay and book refill)
- Cost this print puts on later fills
	- $q_0\cdot I_0 + \sum_{k\ge 1} q_k\cdot I_0\,G(\tau_k)$
	- Same structure as L1 propagator, on child time; see [[Market Impact model]]
- Take vs wait (clearer form + sources)
	- **Take now**
		- $C_{\text{take}} = W(q) + S_t + I_0(q)$
		- $W(q)$ = book-walk from the **live** book
	- **Wait cost**
		- $C_{\text{wait}}(\tau) = \lambda\sigma^2 Q^2\tau + W(q') + S_t G(\tau) + I_0(q')$
			- **Later size if you wait**
			- $q'(\tau) = \min\big(q_{\max},\; q + v^\star\tau + \kappa_L L_t\big)$
			- $v^\star$ = target shares per unit time from the parent curve
			- $L_t$ = shares behind that curve ($X^\star(t) - X_{\text{done}}$)
		- $\lambda\sigma^2 Q^2\tau$ = parent wait-risk on **remaining** $Q$ (Almgren–Chriss 2001 style)
		- Optional add-on: $\beta\sigma\sqrt{\tau}$ as a clip mid-move knob (fit from adverse moves over wait gaps, or leave as urgency knob)
		- **Book-walk on wait**
			- $q'=q$: $W$ can stay the same (cancels with take)
			- $q'>q$: recompute $W(q')$ and $I_0(q')$ — main wait penalty (Almgren 2003)
			- Simple production: same book snapshot, larger $q'$. Refill haircut only if you have OW $\rho$
	- **Rule:** take if $C_{\text{take}} \le C_{\text{wait}}(\tau)$ (e.g. $\tau$ = 2–10s)
	- **Sources**
		- Cont & Kukanov (2017), *Quantitative Finance* — L3 placement; catch-up cost when remainder is larger
		- Almgren (2003), *Applied Mathematical Finance* — temp impact rises with size/rate; delay → costlier later print
		- Almgren & Chriss (2001), *Journal of Risk* — timing / inventory risk $\sim\lambda\sigma^2$ on remaining size
		- Kissell — POV / timing risk / schedule-relative pace (I-Star family)
		- Obizhaeva & Wang (2013), *Journal of Financial Markets* — refill target; do not wait until $S_t=0$ (this $q'$ fix does not replace that)
	- **Still missing vs OW:** interior displacement target / take-the-refill rule; full $D_t$ resilience dynamic

| Need | Term                                                    | How you get it                                    | Train?                                         |
| ---- | ------------------------------------------------------- | ------------------------------------------------- | ---------------------------------------------- |
| Now  | $W(q)$                                                  | Walk **live** book for size $q$                   | No — book only                                 |
| Now  | $I_0(q)$                                                | Fitted curve at size $q$                          | Yes — own-take short markouts vs size          |
| Now  | $S_t$                                                   | Running sum of past $I_0$, decayed by $G$         | Decay $G$ trained; $S_t$ is live state         |
| Now  | $C_{\text{take}}$                                       | $W(q)+S_t+I_0(q)$                                 | —                                              |
| Wait | $q'(\tau)$                                              | $q + v^\star\tau + \kappa_L L_t$ from parent pace | No — schedule arithmetic; $\kappa_L$ is a knob |
| Wait | $W(q')$                                                 | Same live book snapshot, walk size $q'$           | No — book only                                 |
| Wait | $I_0(q')$                                               | Same $I_0(\cdot)$ curve at $q'$                   | Reuse trained $I_0$                            |
| Wait | $S_t G(\tau)$                                           | Decay current $S_t$                               | Reuse trained $G$                              |
| Wait | $\lambda\sigma^2 Q^2\tau$ (or $\beta\sigma\sqrt{\tau}$) | Vol × remaining × urgency                         | Knob (optional light fit); not main IS train   |
| Wait | $C_{\text{wait}}$                                       | sum of wait row                                   | —                                              |

| Component | Source | How they get the number |
|-----------|--------|-------------------------|
| $W(q)$ | Book / Cont–Kukanov (2017) take cost | Live book walk — not fitted |
| $I_0(q)$ | Almgren et al. (2005); Gatheral / Bouchaud; Webster (2023) | Fit short-horizon mid move vs own take size |
| $G(\tau)$, $S_t$ | Obizhaeva–Wang (2013) $\rho$; Bouchaud et al. (2004); Gatheral (2010) | Multi-lag markouts → decay; live $S$ = sum of past $I_0\times G$ |
| $q'(\tau)$ | Cont–Kukanov (2017) catch-up; Kissell pace | Schedule arithmetic — not impact regression |
| $\lambda\sigma^2 Q^2\tau$ | Almgren–Chriss (2001) | $\sigma$ from returns; $\lambda$ urgency knob |
| $\beta\sigma\sqrt{\tau}$ (optional) | AC / Kissell timing risk | Light adverse-move ratio or knob |
| Decision $C_{\text{take}}\le C_{\text{wait}}$ | Cont–Kukanov (2017); related Guéant et al. (2012) | Compare assembled costs |
| Upgrade path | Obizhaeva–Wang (2013) | Target dent / take refill — not in v1 formulas |

See also: [[Impact Model References/L3 Take-Wait Training Guide]] (sourced training runbook + paper PDFs).
