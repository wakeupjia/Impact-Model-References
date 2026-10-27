# 2026-10-27 Discussion

Feedback:
- Model fits **no-posting** algos cleanly:
	- $q'(\tau)$ rises with lag and is forecastable from schedule + leftover.
	- Today's catch-up throttle (fixed ~1 s after catch-up) is arbitrary → replace with scored $\tau^\star$ from $C_{\mathrm{take}}$ vs $C_{\mathrm{wait}}(\tau)$.
	- Deep / long-queue names: $W(q)\approx W(q')$ often → $I_0$, $S_t G$, and $\lambda$ drive the flip.
	- $\lambda$ = style knob (passive ≈ 0, aggressive high); sweep later, skip tape MLE.
	- Lock the markout label for $I_0$ / $R$: mid (standard dent) vs bid/ask touch vs subsequent trade price.
- **Posting model** (existing posting lag, already running):
	- Decision stays take vs wait on the impact model — no post / make action in this layer.
	- Resting posts can fill while we wait → shrinks catch-up $L_t$ and thus $q'$.
	- Same-side aggressive flow raises those passive fill odds → lower effective catch-up than a pure no-post $q'$ forecast.

When a posting algo is also on:
- Before scoring wait, subtract q by expected fills from  posting leg:
	- $q'_{\mathrm{eff}}(\tau)=q'(\tau)-\mathbb{E}[q_{\mathrm{fill}}^{\mathrm{post}}(\tau)]$ (floor at residual still owed).
- Posting leg fill can be conditional on
	- Resting age, depth ahead, same-side trades — inputs to **$q'_{\mathrm{eff}}$**.
- All the other parameters in my existing model shouldn't change. It's mainly this q that got changed.




