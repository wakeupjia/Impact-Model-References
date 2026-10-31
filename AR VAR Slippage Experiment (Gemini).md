
## 1. The model proposal

### Part 1: The Slippage Model (State → Cost)

You need to prove that your $z$-scores possess predictive power over execution shortfall.

**The Experiment:** Run a historical replay of your L3 data. Every second, calculate the theoretical slippage of taking a fixed volume $q$ (e.g., calculating the cost to cross the visible resting liquidity, plus the latent impact measured by the midprice exactly 1 second later). Pair this realized slippage with the $z$-scores calculated in the microsecond prior to the trade.

**Model Design:** While you can start with a simple linear regression, the relationship between the Limit Order Book (LOB) state (like queue sizes and imbalances) and order flow intensities is typically highly non-linear. You should use a non-linear estimator (like a decision tree or random forest) to map the $z$-scores to the expected slippage.

### Part 2: The VAR Model (State → Future State)

You need to confidently project the $z$-scores forward by $\tau$ seconds.

**The Experiment:** Sample your $z$-scores at a fixed frequency (e.g., every 1 second). Fit your Vector Autoregression (VAR) model to establish the transition matrix $A$.

**Model Design:** This step effectively turns your VAR into a lightweight Queue-Reactive (QR) model. QR models demonstrate that the arrival of market orders, limit orders, and cancellations are deeply dependent on the current state of the LOB (such as the queue sizes at the best bid and ask). By capturing this in the transition matrix, you model the endogenous self-excitation and liquidity replenishment of the market without needing to simulate every individual limit order.

### Gemini agreement + two extra design suggestions

Gemini strongly agreed with the two-part architecture (modular, interpretable, efficient for live execution), and added:

1. **Include Queue Imbalance** in the $z$-scores explicitly — imbalance between bid and ask queues is one of the strongest predictors of short-term price moves and execution costs.
2. **Direct forecasting alternative:** train a single ML model to predict the cost difference (slippage at $t+\tau$ minus slippage at $t$) from current $z_t$ only. Mathematically simpler, but the two-step VAR approach is generally preferred because it isolates market dynamics (VAR) from execution constraints (slippage function).

---

## 2. Step-by-step experiment design

### User questions that drove this section

- How do I design my experiment? Right now I don't know the relationship between all this, and how can I make it linear?
- How do I know if it's linear, or how can I transform it to make it linear? If it's not linear, what other model should I use, and how do I know if it's suitable?
- How do I verify that my autoregressive model makes sense? What are my evaluation metrics?
- (Follow-up) Do more in-depth research and propose a research / experiment plan; think about factor selection.
- (Follow-up) How do I define my slippage? If I just choose the next trade, what if slippage worsens after a few more trades (lingering effect)? Should I take that into consideration?

### 2.A Immediate experiment recipe (Gemini reply)

#### 1. Designing the Experiment

Goal: build a supervised learning dataset that links the market state just before a trade to the cost of that trade.

- **Data Collection:** Replay your historical LOB data. For every child order executed, record the exact microsecond timestamp before the first routing decision.
- **Feature Extraction ($X$):** At that exact timestamp, calculate your $z$-scores for the state variables (e.g., `buy_flow`, `ask_maxdepth`, order book imbalance).
- **Target Variable ($y$):** Calculate the realized slippage of that specific child order — difference between arrival mid-price and VWAP fill price (or post-trade mid at a short horizon).
- **Alignment:** Pair pre-trade $z$-scores ($X$) with realized slippage ($y$).

#### 2. Testing and Transforming for Linearity

Market impact and slippage are notoriously non-linear; impact is typically concave (square-root or log in volume).

- **How to test for linearity:** Fit OLS. Plot residuals vs predicted values. Random scatter ⇒ linear; curve/pattern ⇒ non-linear. Formalize with the **Ramsey RESET** test.
- **How to transform it:** Industry practice for concave impact — **log-log**: regress $\log(\text{Slippage})$ on $\log(\text{Volume})$ and state variables (instead of raw slippage on volume and state).

#### 3. Non-Linear Model Alternatives

If transforms fail to linearize:

- **Tree-based:** Random Forests or Gradient Boosted Trees (XGBoost) — handle non-linear LOB interactions without manual transforms.
- **Splines / GAMs:** if you need interpretability of how each variable affects slippage.
- **Suitability check:** chronological out-of-sample CV. Use non-linear models only if OOS $R^2$ / RMSE **significantly beats** linear OLS.

#### 4. Verifying the VAR Model and Evaluation Metrics

VAR predicts **future $z$-scores**, not slippage directly.

- **Training / lag selection:** use **AIC** to choose how many lags (e.g. 1 s vs 5 s lookback); AIC penalizes overfitting.
- **OOS evaluation:** map $z_t$ forward by wait horizon $\tau$ to get $\hat{z}_{t+\tau}$. Compare to realized $z_{t+\tau}$ with **RMSE** and **MAE**.
- **Baseline:** naive **random walk** $\hat{z}_{t+\tau}=z_t$. If VAR RMSE is consistently lower than random walk OOS, the AR model is extracting forward-looking microstructure information.

### 2.B In-depth research / experiment plan (Phases 1–4)

#### Phase 1: Factor Selection (Feature Engineering)

Standardize microstructure factors into $z$-scores (not volume alone):

- **Queue Imbalance (top-of-book):** $(Q_{\mathrm{bid}}-Q_{\mathrm{ask}})/(Q_{\mathrm{bid}}+Q_{\mathrm{ask}})$ — especially important for large-tick names.
- **Order Flow Imbalance (OFI):** net buy vs sell pressure over a short window (e.g. 1–5 s); aggregates market orders, limit inserts, cancels; literature cited as explaining a large share of short-term mid variance.
- **Trade Arrival Intensity:** EWMA of trades/sec — volatility clustering / Hawkes-like self-excitation proxy.
- **Normalized Spread and Depth:** spread in ticks; depth through first three levels, normalized by ADV.

#### Phase 2: The Slippage Model (State → Execution Cost)

- **Data:** millisecond ITCH/OUCH or TAQ; historical replayer; simulate fixed volume $q$.
- **Target $y$:** absolute difference between mid just before trade and realized execution price (or mid exactly **1 second** after execution).
- **Model:** GBDT (XGBoost / LightGBM) — expect linear regression to fail; trees capture state-dependent interactions (e.g. impact surges when OFI high and queue imbalance adverse).
- **Evaluation:** rolling train on historical days, test on the **strictly subsequent** day. Success if GBDT OOS RMSE ≪ constant-cost baseline.

#### Phase 3: The VAR Autoregressive Model (State → Future State)

- **Data:** sample factors uniformly (e.g. every 100 ms or 1 s); standardize to $z$ via minute-of-day distributions.
- **Model:** VAR on the multivariate series — transition matrix $A$ captures cross-excitation (e.g. surge in `buy_flow` → depletion of `ask_maxdepth`). Lightweight queue-reactive framing.
- **Hyperparameters:** lag order via **AIC**.
- **Evaluation:** project $\hat{z}_{t+\tau}=A^{\tau} z_t$ (as written in the share); MAE vs **random-walk** baseline $\hat{z}_{t+\tau}=z_t$. Success if VAR beats random walk OOS.

#### Phase 4: Integration and Policy Testing

At decision time $t$:

1. Observe current LOB state $z_t$.
2. Slippage model on $z_t$ → expected cost of **take now**.
3. VAR on $z_t$ → forecast $\hat{z}_{t+\tau}$.
4. Slippage model on $\hat{z}_{t+\tau}$ → expected cost of **take after wait $\tau$**.
5. Execute the action with the lowest expected cost.

---

## 3. Remaining considerations or questions

### Open questions you asked (and Gemini's answers)

**Q: How do I define my slippage? If I only look at the next trade, what about lingering effects that worsen over later trades?**

**A (Gemini):** Define slippage over a **very short, strict horizon** — typically **exactly one second** post-trade — and **deliberately exclude** longer-term lingering effects from that definition.

Reasons not to lengthen the markout:

- **Avoiding double-counting:** the solver already evaluates immediate take cost and evolving wait cost separately. A 10 s slippage markout would bake future penalty into “immediate” cost; VAR would then also forecast a worse state over those same 10 s → **penalize twice**.
- **Minimizing exogenous noise:** longer horizons are dominated by news, broad vol, and other agents — not your child order's mechanical/informational disruption.

How lingering **is** handled:

- **Slippage model** = immediate impact (1 s markout when you punch resting liquidity).
- **VAR model** = transient impact / resilience tracker. If your trade induces copy-cat momentum or severe book depletion, $A$ projects toxic future $z$-scores over the next few seconds.

Keeping slippage short and assigning lingering dynamics to VAR keeps take-vs-wait **clear and arbitrage-free** between immediate costs and future states.

### Other unresolved / design choices left open in these rounds

- Factor set: Vat's six quantities vs Gemini's recommended imbalance / OFI / intensity / depth — how to merge with [[Simulated Market and Market Impact]] encoders.
- Linear path (OLS + log-log) vs jump straight to GBDT for Part 1 — still an empirical gate (RESET / residual plots / OOS lift).
- Direct one-shot cost-delta model vs two-step VAR+slippage — Gemini prefers two-step for interpretability; not empirically decided.
- Exact $\tau$ grid for wait alternatives in Phase 4.
- Whether VAR is fit on observed tape only or must match dynamic Vat feedback when your own fills change $z$.
- Theoretical fixed-$q$ every-second takes vs labels from **own historical child fills** — two datasets; which first.

---

## Link

- Share: https://share.gemini.google/A3M56L8LCsJ9
- Resolved share page: https://gemini.google.com/share/fa0c62baea0c
