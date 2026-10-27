# L3 Take–Wait — Boss Catch-up Notes & Model Extensions

Companion to [[L3 Take-Wait Simulator Guide]] · [[L3 Take-Wait Training Guide]] · [[Data Preparation]] · [[Market Impact - Three Layers]].

Date: 2026-10-27 (discussion with boss).

---

## 1. Discussion summary

Boss largely agrees with the take/wait cost model:

$$
C_{\mathrm{take}}=W(q)+S_t+I_0(q)
$$
$$
q'(\tau)=\min\big(q_{\max},\, q + v^\star\tau + \kappa_L L_t\big)
$$
$$
C_{\mathrm{wait}}(\tau)=\lambda\sigma^2 Q^2\tau + W(q') + S_t G(\tau) + I_0(q')
$$

**Take** if $C_{\mathrm{take}}\le C_{\mathrm{wait}}(\tau)$.

### Fit to current algos

- Especially suitable for **no-posting** models: $q'$ is essentially always increasing with lag / catch-up, and is easy to forecast from schedule + remaining work.
- With **posting**, prior resting orders may fill while you wait, so effective catch-up and inventory are more dynamic; the model still helps, but the state is richer.
- Today’s catch-up throttle is a **fixed** rule (e.g. after catch-up completes, wait at least ~1 s before catching up again). That 1 s is arbitrary. This framework can replace it with a **dynamic** wait: choose $\tau$ (or take now) by comparing $C_{\mathrm{take}}$ and $C_{\mathrm{wait}}(\tau)$.

### Book walk $W$

- On **long-queue / deep** names, $W(q)$ and $W(q')$ are often similar if $q$ and $q'$ sit in the same touch / first levels — so $W$ alone may not flip the decision; $I_0$, $S_t G$, and $\lambda$ do more work.

### $\lambda$ (risk aversion)

- Treat as a **style knob**, not a tape-fit parameter.
- Passive style → $\lambda\approx 0$; aggressive → high $\lambda$. Defer fine calibration.

### Training data / regression target

Train on **market trades** (tape takes), but the **label** (what price you regress markouts against) is an open design choice:

| Target | What you are measuring | Implication |
| ------ | ---------------------- | ----------- |
| Mid | Unrealized mid move after a take | Matches “dent on fair value”; algo also lives off bid/ask for $W$ and posting |
| Bid / ask (far touch) | Move of the passive side you care about | Closer to fill economics for one side |
| Trade price | Impact on **subsequent print** prices | Asks whether your take moves other people’s trades |

Need an explicit decision: mid is standard for $I_0$ / propagator $S_t$; trade-price impact answers a different question (downstream prints). Bid/ask matter because the live algo is constrained by the book, not only mid.

### With-posting complexity (boss)

No-posting state is simple: leftover own impact $S_t$ decaying with $G$.

With posting, state includes at least:

- Catch-up quantity / lag $L_t$
- **Existing** resting posts (size, price, queue position / age)
- **Potential** new posts

For existing posts: need fill probability in the model. Fill probability is hard — conditional on time waited, on the book, and on flow (e.g. more prints on our side → higher chance our post fills → tilt toward **post** instead of catch-up take).

---

## 2. Insights (keep)

- No-posting is the natural MVP: $q'(\tau)$ monotone in lag, forecastable; model maps cleanly onto “take now vs wait $\tau$ then take larger.”
- Dynamic $\tau$ / take vs wait can replace arbitrary catch-up throttle (fixed 1 s).
- Deep book: $\Delta W = W(q')-W(q)$ often small → do not expect $W$ alone to drive the policy.
- $\lambda$ = style (passive / aggressive), sweep later.
- Label choice (mid vs touch vs trade) changes what $I_0$ *means*; pick one and document it.
- Posting turns a 1-state ($S_t$) problem into a multi-state control (posts + catch-up + impact wake).
- Same-side aggressive flow raises passive fill odds → option value of posting rises vs taking.

---

## 3. Areas of improvement (first)

Priority order for the research / product track:

1. **Ship no-posting MVP** — freeze formula; wire $W$, $I_0$, $S_t$, $G$, $q'$, $\lambda$; replace fixed catch-up wait with scored $\tau$.
2. **Lock markout label** — decide mid vs ask/bid vs trade-price for $I_0$ / $R$ training; write it into [[Data Preparation]].
3. **Units and style grid** — bps everywhere; define 2–3 $\lambda$ presets (passive / neutral / aggressive) before continuous sweep.
4. **Throttle replacement design** — map current “wait ≥ 1 s after catch-up” to: evaluate $C_{\mathrm{wait}}(\tau)$ on a small $\tau$ grid; take if $C_{\mathrm{take}}$ wins.
5. **Deep-book diagnostics** — log $\Delta W$ vs $\Delta I_0$ vs $S_t(1-G)$ so we see which term flips decisions when $W(q)\approx W(q')$.
6. **Posting v2 scope** — do not block MVP; separately specify state (resting size, price, age/queue), fill model $p_{\mathrm{fill}}(\cdot)$, and how fills reduce $q'$ / $L_t$.
7. **Fill-probability research** — hazard vs time-in-queue, depth ahead, OFI / same-side trade intensity; condition “post vs catch-up” on that.
8. **Optional later** — permanent / L1–L2; $G$ floor; multi-venue; Gatheral checks.

---

## 4. Version A — No posting (minimum change)

### Goal

Take vs wait only. No resting orders. Match current no-posting algos.

### Keep as-is

- $C_{\mathrm{take}}$, $C_{\mathrm{wait}}$, $q'(\tau)$, live $W$ on **same** book snapshot for $q$ and $q'$
- Trained $I_0$, $G$; live $S_t$
- $\lambda$ as style knob (start with $0$ and one high value)

### Minimum additions vs today’s throttle

1. On each decision (or after a catch-up burst): compute $L_t$, $v^\star$, candidate $q$.
2. Build $q'(\tau)$ for $\tau\in\{\tau_{\min},\,2\tau_{\min},\,\ldots\}$ (e.g. 0.5, 1, 2, 5 s) instead of a hard-coded 1 s floor.
3. Action = TAKE $q$ if $C_{\mathrm{take}}\le\min_\tau C_{\mathrm{wait}}(\tau)$; else WAIT $\tau^\star=\arg\min C_{\mathrm{wait}}$.
4. On take fill: $S\leftarrow S+I_0(q_{\mathrm{filled}})$; on clock: $S\leftarrow S\cdot G(\Delta t)$.
5. Log terms so throttle A/B is auditable.

### What not to change in v1

- No fill-probability model
- No permanent $\gamma q$
- No posting branch
- Same-book $W(q')$ assumption
- Do not re-fit $I_0$/$G$ in the loop

### Acceptance

- Passive ($\lambda=0$) waits more when $S_t$ large and $q'\approx q$
- Aggressive (high $\lambda$) takes more when $Q$ / lag large
- Replacing fixed 1 s with $\tau^\star$ does not explode take-rate; parent leftover / IS comparable or better on replay

---

## 5. Version B — With posting (brainstorm)

### Why it is harder

Action set grows: **take** / **wait (no new post)** / **post (join)** / **cancel–replace** / **partial take + post**. Waiting can earn a **passive fill** that shrinks catch-up without paying $W+I_0$. Existing posts are inventory options with random exercise.

### Enriched state (minimal useful set)

| State | Role |
| ----- | ---- |
| $S_t$ | Own take-wake (same as v1) |
| $L_t$, $Q$, $v^\star$ | Schedule / catch-up |
| Resting: size $q_{\mathrm{rest}}$, price, side | Option to get filled passively |
| Age or queue proxy | Input to $p_{\mathrm{fill}}$ |
| Book + recent same-side flow | Inputs to $p_{\mathrm{fill}}$ and $W$ |

### Conceptual costs (sketch)

Keep take cost:

$$
C_{\mathrm{take}}=W(q)+S_t+I_0(q)
$$

**Wait without new post** (posts already resting): with probability $p$ over horizon $\tau$ you get passive fill size $q_{\mathrm{fill}}\le q_{\mathrm{rest}}$ at near-touch (cost ≈ half-spread or better vs take), and catch-up residual becomes $q'_{\mathrm{after}}=(q'-q_{\mathrm{fill}})_+$:

$$
\begin{aligned}
C_{\mathrm{wait}}^{\mathrm{post}}(\tau)
&\approx
\lambda\sigma^2 Q^2\tau
+ p\cdot C_{\mathrm{passive}}(q_{\mathrm{fill}})
+ (1-p)\cdot\big(W(q')+I_0(q')\big)\\
&\quad + S_t G(\tau)
+ \text{(optional adverse-selection if filled)}.
\end{aligned}
$$

Crude one-step form (good enough to brainstorm):

$$
C_{\mathrm{wait}}^{\mathrm{post}}(\tau)
\approx
\lambda\sigma^2 Q^2\tau
+ S_t G(\tau)
+ (1-p(\tau))\big(W(q')+I_0(q')\big)
+ p(\tau)\cdot c_{\mathrm{pass}}
$$

where $c_{\mathrm{pass}}$ is small (join cost / adverse selection), and $q'$ is reduced in expectation by $p\cdot\mathbb{E}[q_{\mathrm{fill}}]$.

**New post** action: pay queue delay / adverse selection, raise future $p$, maybe cut expected $q'$. Compare $C_{\mathrm{post}}$ to $C_{\mathrm{take}}$ and $C_{\mathrm{wait}}$.

### Fill probability $p$ (research path)

Boss point: $p$ rises when trades fire on our side and when we have waited in queue.

Practical MVP for $p$ (before a full queue model):

1. **Hazard by age** — Kaplan–Meier or logistic: fill within next $\tau$ | time-since-post, size, spread bucket.
2. **Book features** — depth ahead, our fraction of queue, spread, OFI / microprice.
3. **Flow feature** — same-side trade intensity or signed volume over the last few seconds (boss: more prints on our side → post more attractive than catch-up).
4. Start **unconditional on full LOB path**; add conditioning once baseline $p(\tau,\mathrm{age})$ works in replay.

### How to leverage the current model (do not throw it away)

- $I_0$, $G$, $S_t$, $W$ stay the **take / catch-up** engine.
- Posting adds an **option value** layer: expected reduction in future $W(q')+I_0(q')$ via $p\cdot q_{\mathrm{fill}}$.
- $\lambda$ still styles urgency: high $\lambda$ → take / chase; low $\lambda$ → lean on posts.
- Dynamic $\tau$ still replaces fixed throttle; posting only changes the wait continuation value.
- Cont–Kukanov-style split remains: schedule → child placement (take vs make); our formula is the take/make cost skeleton with an explicit wake $S_t$.

### Suggested build stages for posting

1. **Shadow only** — keep no-posting policy; log $p_{\mathrm{hat}}$, hypothetical $C_{\mathrm{wait}}^{\mathrm{post}}$, and whether posting would have won.
2. **Passive-fill credit in wait** — if resting size $>0$, use simple $p(\tau)$ from age + same-side intensity; no new post actions yet.
3. **Post vs take** — allow join when $C_{\mathrm{post}}<C_{\mathrm{take}}$ and lag below a cap.
4. **Full cancel/replace** — only after 2–3 are stable.

### Risks / traps

- Double-counting: passive fill benefit and lower $q'$ must not both be applied naively without reducing catch-up size.
- Adverse selection: fills arrive when the mid moves against you — $c_{\mathrm{pass}}$ should include a markout on *posted* fills, not only on takes.
- $p$ miscalibration → over-posting and under-catch-up near deadlines.
- Long-queue names: $W(q)\approx W(q')$ already; posting value is mostly avoiding $I_0$ and adverse take, not avoiding a deeper walk.

---

## 6. Decision framing (for next sync)

| Topic | No-posting MVP | With-posting later |
| ----- | -------------- | ------------------ |
| Core inequality | Keep | Keep take cost; extend wait with $p$ |
| $q'$ | Monotone forecast | Reduced by expected passive fills |
| Throttle | Replace 1 s with $\tau^\star$ | Same, plus post action |
| $\lambda$ | Style presets | Same |
| Training label | Decide mid vs touch vs trade | Add posted-fill markouts for $c_{\mathrm{pass}}$ |
| State | $S_t$ + schedule | + resting + $p$ features |

---

## 7. Refs

- Simulator wire-up: [[L3 Take-Wait Simulator Guide]]
- Train $I_0$, $G$: [[L3 Take-Wait Training Guide]] · [[Data Preparation]]
- Layer map: [[Market Impact - Three Layers]]
- Cont–Kukanov (2017) — take vs limit / catch-up
- OW — resilience; posting ≈ harvesting refill
