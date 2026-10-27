# L3 Take–Wait — Compose & Simulator Guide (for AI)

Companion to [[L3 Take-Wait Training Guide]] · [[Data Preparation]] · [[Market Impact - Three Layers]] · [[Discussion]].

## 1. Goal

Wire the Layer-3 take/wait **decision** into a simulator. You already have trained $I_0$ and $G$. Build the rest as **live book**, **parent schedule math**, and **knobs** — then at each child decision compare $C_{\mathrm{take}}$ and $C_{\mathrm{wait}}(\tau)$.

$$
C_{\mathrm{take}}=W(q)+S_t+I_0(q)
$$
$$
q'(\tau)=\min\big(q_{\max},\, q + v^\star\tau + \kappa_L L_t\big)
$$
$$
C_{\mathrm{wait}}(\tau)=\lambda\sigma^2 Q^2\tau + W(q') + S_t G(\tau) + I_0(q')
$$

**Rule:** take if $C_{\mathrm{take}} \le C_{\mathrm{wait}}(\tau)$. Else wait $\tau$ (or join / cut $q$ — out of scope for MVP rule).

*[MVP: one symbol, one venue, one $\tau$ grid (e.g. $\{2,5,10\}$ s), freeze $I_0$ and $G$, sweep only $\lambda,\kappa_L$.]*

---

## 2. What is already trained vs what you build

| Piece | Status | Artifact / source |
| ----- | ------ | ----------------- |
| $I_0(q)=a q^b$ | **Trained** | `i0_fit.json` (or equiv.): $a$, $b$, size unit ($q$ or $q/\mathrm{ADV}$) |
| $G(\tau)$ or $\hat G(\ell)$ | **Trained** | `R_trade_time.csv` / `G` table, or local $e^{-\rho\tau}$ diagnostic |
| $W(q)$ | **Live** | Walk ask (buy) / bid (sell) on **current** book for size $q$ |
| $S_t$ | **Live state** | Start 0; on take add $I_0(q)$; between events multiply by $G(\Delta t)$ |
| $q'(\tau)$ | **Schedule math** | Parent $X^\star(t)$, $v^\star$, lag $L_t$, knobs $\kappa_L$, $q_{\max}$ |
| $\lambda\sigma^2 Q^2\tau$ | **Knob** | $\sigma$ from same vol as TCA; $Q$ = **parent** shares left; $\lambda$ swept |
| Decision | **Compose** | Compare costs; emit take / wait |

Do not re-fit $I_0$ or $G$ inside the simulator loop. Load artifacts once at session start.

---

## 3. Units and conventions (lock these first)

Pick one unit system and use it everywhere in $C_{\mathrm{take}}$ and $C_{\mathrm{wait}}$.

- **Price / cost unit:** bps of mid (recommended) **or** absolute price (currency). Mix breaks the inequality.
- **$I_0$:** if trained in bps, $W$ and $S_t$ must be bps too.
  - Book-walk in bps (buy): $W(q)=10^4\cdot(\bar p_{\mathrm{walk}}-m)/m$ where $\bar p_{\mathrm{walk}}$ is size-weighted average fill price walking the ask; sell: flip sign so cost is positive.
- **$G(\tau)$:** dimensionless, $G(0^+)=1$, nonincreasing. If you have trade-time $\hat G(\ell)$, map $\tau$ → lag via average trade rate, or keep a calendar-time $G(\tau)$ table for the sim clock.
- **Side:** buy $\varepsilon=+1$, sell $\varepsilon=-1$. $S_t$ is a **signed mid dent in cost space** (positive = adverse leftover for the parent side).
- **Time:** simulator clock in seconds. Parent $Q$, child $q$ in shares (same as training).
- **$\sigma$:** consistent with $\lambda\sigma^2 Q^2\tau$ (e.g. daily vol / $\sqrt{252\cdot\text{seconds in day}}$ if $\tau$ is in seconds — document the scale next to $\lambda$).

*[MVP: everything in bps; $G(\tau)=e^{-\rho\tau}$ from a short diagnostic fit **or** linear interp of calendar $G$ table; one $\sigma$ series per day.]*

---

## 4. Inputs the simulator must expose

At each **child decision time** $t$ the policy needs:

1. **Book** — depth by level (price, size) on the take side, mid $m_t$, spread.
2. **Child intent** — side, candidate size $q$ (from parent slice / L2), optional $q_{\max}$.
3. **Parent state** — remaining $Q$, done $X_{\mathrm{done}}$, target path $X^\star(t)$ (or TWAP/POV rule that defines $v^\star$), deadline / time left.
4. **Impact state** — current $S_t$ (scalar).
5. **Market** — $\sigma_t$ (or day-level $\sigma$).
6. **Policy knobs** — $\tau$ candidates, $\lambda$, $\kappa_L$, $q_{\max}$.
7. **Artifacts** — $I_0(\cdot)$, $G(\cdot)$.

Parent schedule API (minimum):

- $v^\star(t)$ = target shares per second from $X^\star$
- $L_t=\max(0, X^\star(t)-X_{\mathrm{done}})$

---

## 5. Modules to implement (order)

Build in this order. Each module is pure / testable without the full sim.

### 5.1 `load_artifacts`

- Read $a,b$ → `I0(q) = a * q**b` (or `a * (q/ADV)**b` if that was the fit).
- Read $G$: callable `G(tau_seconds) -> float` (table interp or `exp(-rho*tau)`).
- Assert $I_0(q)>0$ for $q$ in training range; $G(0)=1$; $G$ decreasing on the grid.

### 5.2 `book_walk_W(book, side, q) -> cost_bps`

- Consume levels until filled size $=q$ (or partial if book thin → treat as infeasible / force take smaller $q$).
- Return positive cost in the same unit as $I_0$.
- Unit test on recorded books: known depth → known $W$.

### 5.3 `I0(q) -> bps`

- Thin wrapper on artifact. Clamp $q$ to training support or flag OOD.

### 5.4 `ImpactState` ($S_t$)

```
state: S = 0 at parent start
on_elapsed(dt):  S = S * G(dt)
on_take(q):      S = S + I0(q)     # same sign convention as costs
```

- Call `on_elapsed` on every clock advance **before** scoring a decision.
- Call `on_take` only on **confirmed** take fills (simulator fill event), size = filled $q$.

### 5.5 `catchup_q_prime(q, tau, v_star, L_t, kappa_L, q_max) -> q_prime`

$$
q'=\min\big(q_{\max},\, q + v^\star\tau + \kappa_L L_t\big)
$$

- $q'\ge q$. If schedule says you are ahead ($L_t=0$) and $v^\star\tau$ small, $q'\approx q$.

### 5.6 `wait_risk(lambda, sigma, Q, tau) -> bps`

- $\lambda\sigma^2 Q^2\tau$, converted into **bps** with the same mid-notional convention you use for $W$ (document the conversion once).
- *[MVP: implement the formula; calibrate $\lambda$ by sweep so wait-risk is same order of magnitude as $W+I_0$ on typical clips — do not MLE-fit $\lambda$.]*

### 5.7 `score_take_wait(...) -> (C_take, C_wait, action)`

```
on_elapsed(dt_since_last)
W_q  = book_walk_W(book, side, q)
C_take = W_q + S + I0(q)

for each tau in tau_grid:
  q_p = catchup_q_prime(...)
  W_p = book_walk_W(book, side, q_p)   # same snapshot; larger size
  C_wait = wait_risk(...) + W_p + S*G(tau) + I0(q_p)
  keep best (min C_wait) or evaluate fixed tau

action = TAKE if C_take <= C_wait else WAIT
```

*[MVP: single $\tau$ (e.g. 5 s) first; multi-$\tau$ min later.]*

### 5.8 `DecisionPolicy` facade

One function the simulator calls:

`decide(t, book, side, q, parent_state, impact_state, knobs) -> {action, q, tau, C_take, C_wait, debug}`

---

## 6. Simulator integration (hooks)

Wire these events. Names are illustrative; map to your sim’s API.

| Simulator event | What the policy / state does |
| --------------- | ---------------------------- |
| `on_parent_start` | $S\leftarrow 0$; load artifacts; set $\lambda,\kappa_L,\tau$ |
| `on_clock` / `on_quote` | Optional: only decide on a timer or when book/slice updates |
| `on_child_decision` | `on_elapsed`; compute $q$ from parent slice; `decide`; if TAKE → send marketable order size $q$; if WAIT → sleep / requeue after $\tau$ |
| `on_fill` (own take) | `impact_state.on_take(filled_qty)`; update $X_{\mathrm{done}}$, $Q$ |
| `on_parent_end` | Log path; no further $S$ updates |

**Decision cadence (MVP):** every $\tau$ seconds while parent unfinished, or whenever Layer-2 issues a new child $q$. Do not decide on every book update unless the sim is event-driven and cheap.

**Fill model:** use your simulator’s existing marketable-order fill against the book. $W(q)$ must use the **same** book walk the fill engine uses (or accept a documented gap).

**Parent $X^\star$:** TWAP / POV / AC path already in the sim is enough. Expose $v^\star$ and $L_t$; do not re-implement Layer 1 inside this guide.

---

## 7. Step-by-step build runbook

1. Load $I_0$, $G$ artifacts; unit-test `I0(q)` and `G(tau)` on a few points from training plots.
2. Implement `book_walk_W`; unit-test on 2–3 frozen books (hand-checked bps).
3. Implement `ImpactState`; unit-test: take $q$ → $S=I_0(q)$; wait $\tau$ → $S\leftarrow S G(\tau)$; second take accumulates.
4. Implement `catchup_q_prime` + `wait_risk`; unit-test arithmetic only.
5. Implement `score_take_wait` / `decide`; golden tests: (a) $S=0$, $q'=q$, $\lambda=0$ ⇒ $C_{\mathrm{take}}=C_{\mathrm{wait}}$ ⇒ TAKE (tie → take); (b) large $S$, long $\tau$, $\lambda=0$, $q'=q$ ⇒ WAIT preferred when $S(1-G(\tau))$ beats nothing else; (c) $q'\gg q$ with thin book ⇒ WAIT cost rises via $W(q')+I_0(q')$.
6. Hook `on_parent_start` / `on_child_decision` / `on_fill` in the simulator.
7. Offline replay one historical parent day: log every decision’s $C_{\mathrm{take}}$, $C_{\mathrm{wait}}$, $q$, $q'$, $S$, action.
8. Freeze $I_0,G$; sweep $\lambda,\kappa_L$ on a small grid; score **parent** IS, leftover, participation — not child hit-rate alone.
9. *[Full later:]* multi-$\tau$ choose; calendar vs trade-time $G$; OW refill target; index residual; Gatheral check on $(I_0,G)$.

---

## 8. MVP defaults (start here)

- 1 symbol, continuous session only (same session clean as [[Data Preparation]]).
- $\tau=5\,\mathrm{s}$ (also try $2$ and $10$).
- $G(\tau)=e^{-\rho\tau}$ if you have a local $\rho$; else interpolate trained $G$ on seconds.
- $\kappa_L\in\{0,1\}$; $q_{\max}=$ min(remaining $Q$, participation cap × expected volume in window).
- $\lambda$ sweep until wait-risk on a median clip is roughly $0.25\times$–$2\times$ typical $W+I_0$.
- Tie $C_{\mathrm{take}}=C_{\mathrm{wait}}$ → **TAKE**.
- No quote-age filter; no dropping paths when another trade arrives (sim keep-all).

---

## 9. Logging (required for debug)

Each decision row:

`t, side, q, q_prime, tau, W_q, W_qp, I0_q, I0_qp, S_before, G_tau, wait_risk, C_take, C_wait, action, Q_left, L_t, v_star, mid, spread`

Each fill row: `t, filled_q, S_after, X_done`.

---

## 10. Do not

- Re-estimate $I_0$ or $G$ inside the decision loop
- Put $Q$ (parent) into $I_0$; $I_0$ is child size $q$ / $q'$
- Use metaorder square-root day impact as child $I_0$
- Mix currency cost with bps in the same inequality
- Wait until $S_t=0$ (OW: dent need not fully heal)
- Claim production $\lambda$ from one short backtest — treat as knob
- Change book between $W(q)$ and $W(q')$ inside one decision (same snapshot)

---

## 11. Acceptance checks

- Golden unit tests in §7 step 5 pass.
- On replay, $S_t$ rises after takes and falls over waits; never NaN.
- Raising $\lambda$ increases take rate (more urgency).
- Raising $\kappa_L$ when behind schedule increases $q'$ and can flip WAIT→TAKE when catch-up is cheap on the book, or TAKE→WAIT when $W(q')$ blows up.
- Parent leftover at deadline falls as $\lambda$ rises (until liquidity caps bind).

---

## 12. Refs

- Formulas and paper table: [[L3 Take-Wait Training Guide]]
- Tape → $I_0$, $R$, $G$: [[Data Preparation]]
- Layer map: [[Market Impact - Three Layers]]
- Cont–Kukanov catch-up / placement · OW resilience · AC $\lambda$ — see training guide §5 PDFs
