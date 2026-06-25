# Glossary — Alpha-Lake

Dashboards surface two families of metrics: **technical indicators** (derived from
daily OHLCV bars) and **fundamental metrics** (derived from SEC-filed financial
data and read-time valuation).

---

## Technical Indicators

All indicators are derived from daily OHLCV bars unless otherwise noted.
Category tags match the dashboard submenu: **Trend**, **Momentum**, **Volatility**,
**Volume**, **Structure**, **Relative Performance**, **Utility**.

---

## Trend

### SMA(20 / 50 / 200)
Simple Moving Average of closing price over N periods.
`SMA = sum(close, N) / N`
Category: Trend · Source: close · Period: 20 / 50 / 200

### EMA(12 / 26)
Exponential Moving Average — assigns greater weight to recent prices.
`EMA = close × α + EMA_prev × (1 − α)` where `α = 2 / (N + 1)`
Category: Trend · Source: close · Period: 12 / 26

### WMA (Weighted Moving Average)
Linear-weighted moving average. Most recent price receives weight N, oldest receives weight 1.
`WMA = sum(close_i × i) / sum(i)` for i = 1..N
Category: Trend · Source: close

### KAMA (Kaufman Adaptive Moving Average)
Adaptive MA that adjusts smoothing based on market noise vs trend efficiency.
Uses Efficiency Ratio (ER) to dynamically set the smoothing constant.
Category: Trend · Source: close

### MACD (Moving Average Convergence Divergence)
Difference between fast and slow EMAs. Measures trend direction and strength.
`MACD_line = EMA(close, 12) − EMA(close, 26)`
Category: Trend · Source: close · Periods: 12, 26, 9

### MACD Signal (MACD EMA)
EMA of the MACD line. A bullish crossover occurs when MACD crosses above its signal line.
`MACD_ema = EMA(MACD_line, 9)`
Category: Trend · Source: close · Period: 9

### MACD Histogram
Difference between MACD line and its signal line. Positive values indicate upward momentum.
`MACD_hist = MACD_line − MACD_ema`
Category: Trend · Source: close

### PPO (Percentage Price Oscillator)
Like MACD but expressed as a percentage of the slow EMA. Useful for comparing across price levels.
`PPO = (EMA(close, 12) − EMA(close, 26)) / EMA(close, 26) × 100`
Category: Trend · Source: close · Periods: 12, 26, 9

### PPO Signal
EMA of the PPO line. A bullish crossover occurs when PPO crosses above its signal line.
`PPO_signal = EMA(PPO, 9)`
Category: Trend · Source: close · Period: 9

### PPO Histogram
Difference between PPO and its signal line. Receding histogram values suggest fading momentum.
`PPO_hist = PPO − PPO_signal`
Category: Trend · Source: close · Periods: 12, 26, 9

### TRIX (Triple Smoothed Exponential Average)
Triple-smoothed EMA of close, then 1-period ROC. Acts as a momentum oscillator that filters out short-term noise.
`TRIX = ROC(EMA(EMA(EMA(close, N), N), N), 1)`
Category: Trend · Source: close

### ADX (Average Directional Index, 14)
Measures trend strength regardless of direction. Values above 25 indicate a strong trend; below 20 suggest ranging.
`ADX = EMA(100 × |+DI − −DI| / (+DI + −DI), 14)`
Category: Trend · Source: high, low, close · Period: 14

### DI+ (Positive Directional Indicator, 14)
Component of ADX. Measures upward price movement strength.
`+DI = 100 × EMA(+DM, 14) / EMA(ATR, 14)`
Category: Trend · Source: high, low, close · Period: 14

### DI− (Negative Directional Indicator, 14)
Component of ADX. Measures downward price movement strength.
`−DI = 100 × EMA(−DM, 14) / EMA(ATR, 14)`
Category: Trend · Source: high, low, close · Period: 14

### Aroon Up / Aroon Down
Aroon Up measures time since the most recent N-period high; Aroon Down measures time since the most recent N-period low.
`Aroon_Up = 100 × (N − periods_since_highest_high) / N`
`Aroon_Down = 100 × (N − periods_since_lowest_low) / N`
Category: Trend · Source: high, low · Period: 25

### Aroon Oscillator
Aroon Up minus Aroon Down. Positive values indicate uptrend; negative values indicate downtrend.
Category: Trend · Source: high, low · Period: 25

### MA Stack
Relative ordering of short, medium, and long-term moving averages. A bullish stack has SMA(20) > SMA(50) > SMA(200); bearish is the reverse.
Category: Trend

### MA Slope
Slope of the moving average over a backward-looking window, expressed as a rate of change per period.
Category: Trend

### Linear Regression Slope
Slope coefficient from a linear regression of close on time over N periods. Positive = upward drift.
Category: Trend · Source: close

### Linear Regression Channel
Linear regression line ± standard-deviation bands around the fitted line. Represents a trend channel.
Category: Trend · Source: close

---

## Momentum

### RSI (Relative Strength Index, 14)
Measures speed and magnitude of recent price changes. Overbought above 70; oversold below 30.
`RSI = 100 − 100 / (1 + avg_gain / avg_loss)`
Category: Momentum · Source: close · Period: 14

### Stochastic %K (14, 3)
Compares close to the high-low range over N periods. Values above 80 indicate overbought; below 20 oversold.
`%K = 100 × (close − lowest_low(N)) / (highest_high(N) − lowest_low(N))`
Category: Momentum · Source: high, low, close · Periods: 14, 3

### Stochastic %D
Simple moving average of %K. The %K / %D crossover generates the classic stochastic signal.
Category: Momentum · Source: high, low, close · Period: 3

### Stochastic RSI
Applies the stochastic formula to RSI values rather than price. More sensitive to RSI extremes.
`Stoch_RSI = (RSI − min(RSI, 14)) / (max(RSI, 14) − min(RSI, 14))`
Category: Momentum · Source: close · Period: 14

### Williams %R (14)
Inverse of stochastic. Identical formula to %K but inverted; −80 below is oversold, −20 above is overbought.
`%R = −100 × (highest_high(N) − close) / (highest_high(N) − lowest_low(N))`
Category: Momentum · Source: high, low, close · Period: 14

### CCI (Commodity Channel Index, 20)
Measures deviation of typical price from its statistical mean. Above +100 = overbought; below −100 = oversold.
`CCI = (TP − SMA(TP, 20)) / (0.015 × mean_abs_deviation(TP))`
Category: Momentum · Source: high, low, close · Period: 20

### TSI (True Strength Index)
Double-smoothed rate of change. Measures momentum with reduced noise.
`TSI = 100 × EMA(EMA(momentum, N), M) / EMA(EMA(abs(momentum), N), M)`
Category: Momentum · Source: close

### Ultimate Oscillator
Weighted average of three timeframes of buying pressure. Designed to identify divergences.
`UO = 100 × (a × BP(N1) + b × BP(N2) + c × BP(N3)) / (a × TR(N1) + b × TR(N2) + c × TR(N3))`
Category: Momentum · Source: high, low, close · Periods: 7, 14, 28

### Chande Momentum Oscillator (CMO)
Momentum oscillator based on the ratio of upward vs downward sum of price changes.
`CMO = 100 × (sum_up − sum_down) / (sum_up + sum_down)`
Category: Momentum · Source: close

### Balance of Power (BoP)
Measures the ability of buyers vs sellers to push price through the session range.
`BoP = (close − open) / (high − low)`
Category: Momentum · Source: open, high, low, close

### ROC (Rate of Change, 12)
Percentage change in closing price over N periods.
`ROC = (close / close(N_periods_ago) − 1) × 100`
Category: Momentum · Source: close · Period: 12

### Choppiness Index (CHOP)
Measures whether the market is trending or ranging. Values above 61.8 = ranging; below 38.2 = trending.
`CHOP = 100 × log10(sum(ATR, N) / (highest_high(N) − lowest_low(N))) / log10(N)`
Category: Momentum · Source: high, low, close · Period: 14

### RSI Divergence
Detects divergence between price and RSI. Bullish divergence: price makes lower low, RSI makes higher low. Bearish divergence: price makes higher high, RSI makes lower high.
Category: Momentum · Source: close · Period: 14

---

## Volatility

### Bollinger Bands (20, 2)
SMA ± 2 standard deviations. Upper and lower bands act as dynamic support/resistance during trending moves.
`Upper = SMA(close, 20) + 2 × σ(close, 20)`
`Lower = SMA(close, 20) − 2 × σ(close, 20)`
Category: Volatility · Source: close · Periods: 20, 2

### %B (Percent B)
Indicates price position within the Bollinger Bands. 1.0 = at upper band, 0.0 = at lower band, 0.5 = at middle.
`%B = (close − lower_band) / (upper_band − lower_band)`
Category: Volatility · Source: close · Period: 20

### Bandwidth
Width of the Bollinger Bands relative to the middle band. Narrow bandwidth precedes volatility expansion.
`Bandwidth = (upper_band − lower_band) / middle_band`
Category: Volatility · Source: close · Period: 20

### Bollinger Squeeze
Occurs when Bollinger Bandwidth contracts below a threshold (e.g., 6-month minimum), suggesting an imminent breakout.
Category: Volatility · Source: close · Period: 20

### Keltner Channels
EMA-based channel with ATR bands. Similar to Bollinger but uses ATR instead of standard deviation.
`Middle = EMA(close, 20)`, `Upper = Middle + 2 × ATR(10)`, `Lower = Middle − 2 × ATR(10)`
Category: Volatility · Source: high, low, close · Periods: 20, 10, 2

### ATR (Average True Range, 14)
Average of the true range over N periods. Measures price volatility in absolute units.
`TR = max(high − low, |high − close_prev|, |low − close_prev|)`
`ATR = SMA(TR, 14)`
Category: Volatility · Source: high, low, close · Period: 14

### ATR% (ATR as % of Close)
ATR normalized by closing price. Allows cross-asset volatility comparison.
`ATR% = ATR / close × 100`
Category: Volatility · Source: high, low, close · Period: 14

### True Range (TR)
The greatest of: current high − low, absolute high − previous close, absolute low − previous close.
Category: Volatility · Source: high, low, close

### Standard Deviation (rolling, 20)
Rolling standard deviation of closing price. Measures statistical dispersion.
Category: Volatility · Source: close · Period: 20

### Realized Volatility (21 / 63d)
Annualized volatility of daily log returns over N periods.
`RV = σ(log_return, N) × √252`
Category: Volatility · Source: close · Periods: 21, 63

### Range Expansion / Contraction
Ratio of current true range to the average true range over N periods. Values > 1.0 = expanding, < 1.0 = contracting.
Category: Volatility · Source: high, low, close

### Donchian Channels (20)
Highest high and lowest low over N periods. Forms a price channel.
`Upper = highest_high(N)`, `Lower = lowest_low(N)`, `Middle = (Upper + Lower) / 2`
Category: Volatility · Source: high, low · Period: 20

---

## Volume

### OBV (On-Balance Volume)
Cumulative volume where volume is added on up days and subtracted on down days.
`OBV = OBV_prev + volume × sign(close − close_prev)`
Category: Volume · Source: close, volume

### OBV Slope (20)
Simple linear slope of OBV over 20 periods. Positive = OBV trending up → accumulation.
Category: Volume · Source: close, volume · Period: 20

### VWAP (Volume-Weighted Average Price)
Cumulative (typical_price × volume) / cumulative volume. Represents the average price weighted by volume.
`VWAP = sum(TP × volume) / sum(volume)`
Category: Volume · Source: high, low, close, volume

### Relative Volume (RVOL, 20)
Ratio of current volume to its 20-period average. Values > 2.0 indicate unusually high volume.
`RVOL = volume / SMA(volume, 20)`
Category: Volume · Source: volume · Period: 20

### Dollar Volume
Closing price × volume. Represents the total monetary value traded.
Category: Volume · Source: close, volume

### Average Dollar Volume (20)
Rolling 20-period average of dollar volume.
Category: Volume · Source: close, volume · Period: 20

### Volume Spike Detection
Boolean: true when RVOL exceeds a configurable threshold (typically 2.5×) OR when volume exceeds its trailing average by more than N standard deviations.
Category: Volume · Source: volume

### A/D Line (Accumulation/Distribution)
Cumulative measure of where the close falls within the high-low range, weighted by volume.
`A/D = A/D_prev + volume × (close − low − (high − close)) / (high − low)`
Category: Volume · Source: high, low, close, volume

### CMF (Chaikin Money Flow, 20)
Accumulation/Distribution summed over N periods divided by total volume. Above 0 = buying pressure; below 0 = selling.
`CMF = sum(Money_Flow_Volume, 20) / sum(volume, 20)`
Category: Volume · Source: high, low, close, volume · Period: 20

### Chaikin Oscillator
EMA of A/D Line minus a longer EMA of A/D Line. Crossovers signal buying/selling pressure shifts.
`Chaikin = EMA(A/D, 3) − EMA(A/D, 10)`
Category: Volume · Source: high, low, close, volume · Periods: 3, 10

### MFI (Money Flow Index, 14)
Volume-weighted RSI. Compares positive vs negative money flow.
`MFI = 100 − 100 / (1 + positive_money_flow / negative_money_flow)`
Category: Volume · Source: high, low, close, volume · Period: 14

### VPT (Volume Price Trend)
Running cumulative total of volume multiplied by percentage price change.
`VPT = VPT_prev + volume × (close − close_prev) / close_prev`
Category: Volume · Source: close, volume

### Force Index (13)
Price change × volume. Measures the power of a price move backed by volume.
`Force = (close − close_prev) × volume`
Category: Volume · Source: close, volume · Period: 13

### EOM (Ease of Movement, 14)
Relates price movement to volume. High values indicate price moved easily (low volume); low values indicate difficulty (high volume).
`EOM = ((high − low) / 2 − (high_prev − low_prev) / 2) / (volume / 10000)`
Category: Volume · Source: high, low, volume · Period: 14

---

## Structure (Price Action & Patterns)

### Returns (1d / 5d / 21d / 63d)
Simple periodic return as a decimal fraction.
`Return(N) = close / close(N_periods_ago) − 1`
Category: Structure · Source: close · Periods: 1, 5, 21, 63

### Log Return
Natural logarithm of the simple return ratio.
`Log_Return = ln(close / close_prev)`
Category: Structure · Source: close

### Gap % (Overnight Gap)
Percentage change from previous close to current open.
`Gap% = (open / close_prev − 1) × 100`
Category: Structure · Source: open, close

### Gap Fill Detection
Boolean: does price return to the previous close within N periods following a gap?
Gaps may be "filled" (price retraces to fill the gap) or "unfilled."
Category: Structure · Source: open, high, low, close

### % Off 52-Week High
Percentage below the rolling 252-period maximum high.
`%Off_High = (close / rolling_max(high, 252)) − 1`
Category: Structure · Source: close, high · Period: 252

### % Off 52-Week Low
Percentage above the rolling 252-period minimum low.
`%Off_Low = (close / rolling_min(low, 252)) − 1`
Category: Structure · Source: close, low · Period: 252

### New 52-Week High
Boolean: current high equals the rolling 252-period maximum high.
Category: Structure · Source: high · Period: 252

### New 52-Week Low
Boolean: current low equals the rolling 252-period minimum low.
Category: Structure · Source: low · Period: 252

### Distance to MA (Price vs MA)
Relative distance of closing price from a moving average.
`Distance = (close / MA − 1) × 100`
Category: Structure · Source: close

### Above MA
Boolean: close is above a given moving average.
Category: Structure · Source: close

### Inside Bar
Boolean: current high ≤ previous high AND current low ≥ previous low. Indicates consolidation.
Category: Structure · Source: high, low

### Outside Bar
Boolean: current high > previous high AND current low < previous low. Indicates breakout / expansion.
Category: Structure · Source: high, low

### Pivot Points (Support / Resistance)
Local highs (resistance) and lows (support) identified over a rolling window.
A pivot high occurs when high(N + M) < high(N) > high(N − M). Pivot low is the inverse.
Category: Structure · Source: high, low

---

## Relative Performance

### Beta vs SPY (20d / 60d)
Measure of systematic risk: covariance of stock return with SPY return, divided by variance of SPY return.
`Beta = cov(R_stock, R_SPY) / var(R_SPY)`
Requires SPY daily bars. Category: Relative Performance · Periods: 20, 60

### Alpha vs SPY
Excess return of the stock over the risk-free rate minus the expected return predicted by Beta.
`Alpha = R_stock − (RFR + Beta × (R_SPY − RFR))`
Requires SPY daily bars. Category: Relative Performance

### Relative Strength vs SPY (20d / 60d)
Ratio of stock return to SPY return over the period. Values > 1.0 = outperformance.
`RS = (1 + R_stock) / (1 + R_SPY) − 1`
Requires SPY daily bars. Category: Relative Performance · Periods: 20, 60

### Rolling Correlation vs SPY
Pearson correlation coefficient of daily returns over a rolling window.
Requires SPY daily bars. Category: Relative Performance

---

## Utility

### Synthetic Mode Indicator
Boolean, true when the lake is running with synthetic (demo) data rather than live API data.
Controlled by `[lake] synthetic_mode` in `config/stack.toml`.
Category: Utility

### Data Health Status
Enum: `valid`, `stale`, `degraded`, `quarantined`. Read from the most recent bar's quality_status.
Category: Utility

### Trading Date Count
Number of trading days available in the lookback window for the symbol. Used to verify sufficient data for indicator computation.

---

## Fundamentals

Fundamental metrics are derived from SEC EDGAR company filings, analyst
estimates, earnings calendar events, and read-time valuations. Categories match
the dashboard **Fundamentals** tab: **Scale**, **Profitability**, **Cash Flow
Quality**, **Growth**, **Financial Health**, **Estimates**, **Events**,
**Valuation**.

Metrics with `⚠ not materialized` are registered for API exploration but are not
yet produced by the batch compute pipeline. They will return `unavailable` with
condition `not_materialized`.

Metrics with `⚠ no source data` are registered for API exploration but depend on
data sources not yet connected. They will return `unavailable` with condition
`no_source_data`.

### Scale

#### Revenue (TTM)
Total revenue over the last four standalone quarters.
`sum(last_four_standalone_quarter_revenue)`
Category: Scale · Basis: ttm · Unit: currency

#### Revenue per Share (TTM)
Revenue per share over the last four standalone quarters.
`revenue_ttm / diluted_shares_outstanding`
Category: Scale · Basis: ttm · Unit: currency · ⚠ not materialized

#### EBITDA (TTM)
Earnings before interest, taxes, depreciation, and amortization over TTM.
`sum(last_four_standalone_quarter_ebitda)`
Category: Scale · Basis: ttm · Unit: currency

#### EBITDA Margin (TTM)
EBITDA as a percentage of revenue over TTM.
`ebitda_ttm / revenue_ttm × 100`
Category: Profitability · Basis: ttm · Unit: percent

### Profitability

#### Gross Margin (TTM)
Gross profit as a percentage of revenue over TTM.
`gross_profit_ttm / revenue_ttm × 100`
Category: Profitability · Basis: ttm · Unit: percent

#### Operating Margin (TTM)
Operating income as a percentage of revenue over TTM.
`operating_income_ttm / revenue_ttm × 100`
Category: Profitability · Basis: ttm · Unit: percent

#### Net Margin (TTM)
Net income as a percentage of revenue over TTM.
`net_income_ttm / revenue_ttm × 100`
Category: Profitability · Basis: ttm · Unit: percent

#### FCF Margin (TTM)
Free cash flow as a percentage of revenue over TTM.
`free_cash_flow_ttm / revenue_ttm × 100`
Category: Profitability · Basis: ttm · Unit: percent

#### Diluted EPS (TTM)
Diluted earnings per share over the last four standalone quarters.
`sum(last_four_standalone_quarter_diluted_eps)`
Category: Profitability · Basis: ttm · Unit: currency · ⚠ not materialized

### Cash Flow Quality

#### CFO / Net Income (TTM)
Operating cash flow divided by net income over TTM.
`operating_cash_flow_ttm / net_income_ttm`
Category: Cash Flow Quality · Basis: ttm · Unit: multiple

#### FCF Conversion (TTM)
Free cash flow divided by net income over TTM.
`free_cash_flow_ttm / net_income_ttm`
Category: Cash Flow Quality · Basis: ttm · Unit: multiple

#### FCF per Share (TTM)
Free cash flow per share over the last four standalone quarters.
`free_cash_flow_ttm / diluted_shares_outstanding`
Category: Cash Flow Quality · Basis: ttm · Unit: currency · ⚠ not materialized

### Growth

#### Revenue YoY (TTM)
Year-over-year TTM revenue growth.
`revenue_ttm / revenue_ttm_1y_ago − 1`
Category: Growth · Basis: ttm · Unit: percent

#### EPS Diluted YoY (TTM)
Year-over-year TTM diluted EPS growth.
`eps_ttm / eps_ttm_1y_ago − 1`
Category: Growth · Basis: ttm · Unit: percent

#### EBITDA YoY (TTM)
Year-over-year TTM EBITDA growth.
`ebitda_ttm / ebitda_ttm_1y_ago − 1`
Category: Growth · Basis: ttm · Unit: percent

### Financial Health

#### Cash & Equivalents (MRQ)
Cash and short-term investments as of the most recent quarter.
Category: Financial Health · Basis: mrq · Unit: currency

#### Total Debt (MRQ)
Total debt (short-term + long-term) as of the most recent quarter.
Category: Financial Health · Basis: mrq · Unit: currency

#### Net Debt (MRQ)
Total debt minus cash and equivalents as of the most recent quarter.
Category: Financial Health · Basis: mrq · Unit: currency

#### Net Debt / EBITDA (TTM)
Net debt divided by TTM EBITDA. Measures leverage.
`net_debt_mrq / ebitda_ttm`
Category: Financial Health · Basis: ttm · Unit: multiple

#### Current Ratio (MRQ)
Current assets divided by current liabilities as of the most recent quarter.
`current_assets / current_liabilities`
Category: Financial Health · Basis: mrq · Unit: multiple

#### Debt / Equity (MRQ)
Total debt divided by total equity as of the most recent quarter.
`total_debt / total_equity`
Category: Financial Health · Basis: mrq · Unit: multiple

### Estimates

The following are computed at read time from the latest PIT-safe analyst estimates
snapshot. Metrics marked `⚠ no source data` depend on forward EPS/revenue
estimates not yet available from current connectors.

#### Target Price
Mean analyst price target from the latest available consensus.
`latest_analyst_target_mean`
Category: Estimates · Basis: snapshot · Unit: currency

#### Target High
Highest analyst price target from the latest available consensus.
`latest_analyst_target_high`
Category: Estimates · Basis: snapshot · Unit: currency

#### Target Low
Lowest analyst price target from the latest available consensus.
`latest_analyst_target_low`
Category: Estimates · Basis: snapshot · Unit: currency

#### Buy Ratio
Percentage of analyst ratings that are buy or strong buy.
`(strong_buy + buy) / (strong_buy + buy + hold + sell + strong_sell) × 100`
Category: Estimates · Basis: snapshot · Unit: percent

#### Forward EPS Growth
Projected year-over-year EPS growth based on consensus forward estimates.
`(forward_eps − trailing_eps) / |trailing_eps|`
Category: Estimates · Basis: snapshot · Unit: percent · ⚠ no source data

#### EPS Revision (30d)
Percentage change in consensus EPS estimate over the last 30 days.
`(current_eps_estimate − eps_estimate_30d_ago) / |eps_estimate_30d_ago|`
Category: Estimates · Basis: snapshot · Unit: percent · ⚠ no source data

#### Revenue Revision (30d)
Percentage change in consensus revenue estimate over the last 30 days.
`(current_revenue_estimate − revenue_estimate_30d_ago) / |revenue_estimate_30d_ago|`
Category: Estimates · Basis: snapshot · Unit: percent · ⚠ no source data

### Events

#### Days to Earnings
Number of calendar days until the next confirmed earnings report date.
`next_earnings_report_date − as_of`
Category: Events · Basis: snapshot · Unit: days

#### Earnings Surprise
Percentage difference between actual and estimated EPS for the latest reported quarter.
`(actual_eps − estimated_eps) / |estimated_eps| × 100`
Category: Events · Basis: snapshot · Unit: percent · ⚠ no source data

### Valuation (read-time)

The following are computed at read time by combining the latest available price
with fundamental data. They are never stored.

#### P/E (TTM)
Latest price divided by TTM diluted EPS.
`price / diluted_eps_ttm`
Category: Valuation · Basis: read_time · Unit: multiple

#### P/S (TTM)
Latest price divided by TTM revenue per share.
`price / revenue_per_share_ttm`
Category: Valuation · Basis: read_time · Unit: multiple

#### P/FCF (TTM)
Latest price divided by TTM free cash flow per share.
`price / fcf_per_share_ttm`
Category: Valuation · Basis: read_time · Unit: multiple

### Threshold Profiles

Fundamental metrics carry a threshold profile that classifies each value into a
state with a tone (neutral gray, green, amber, red) and label. Profiles are
versioned TOML-derived data in `src/alpha_lake/interpretation/fundamentals_glossary.py`.

| Profile | Method | Description |
|---------|--------|-------------|
| `context_only_v1` | context | Always contextual; no directional classification |
| `relative_valuation_multiple_v1` | discrete | P/E, P/S, P/FCF: low (<15), median (15–30), high (≥30) |
| `yield_v1` | discrete | Yield metrics: low (<2%), median (2–5%), high (≥5%) |
| `profitability_peer_percentile_v1` | peer_percentile | Margins classified relative to peers (min 5 peers) |
| `roic_absolute_v1` | discrete | ROIC: low (<5%), median (5–15%), high (≥15%) |
| `growth_yoy_v1` | discrete | YoY growth: contracting (<−1%), stable (−1–1%), expanding (>1%) |
| `margin_change_v1` | discrete | Margin Δ: declining, stable, expanding |
| `leverage_v1` | discrete | Net Debt/EBITDA: low (<2×), median (2–4×), high (≥4×) |
| `debt_to_equity_v1` | discrete | D/E: low (<0.5×), median (0.5–2×), high (≥2×) |
| `liquidity_v1` | discrete | Current ratio: low (<1×), median (1–2×), high (≥2×) |
| `interest_coverage_v1` | discrete | EBIT/interest: low (<2×), median (2–5×), high (≥5×) |
| `cash_conversion_v1` | discrete | FCF/net income: low (<0.5×), median (0.5–1×), high (≥1×) |
| `share_count_change_v1` | discrete | Share count Δ: diluting, stable, reducing |
| `payout_ratio_v1` | discrete | Payout ratio: low (<20%), median (20–60%), high (≥60%) |
| `estimate_revision_v1` | discrete | Analyst revision direction |
| `proximity_v1` | discrete | Time proximity: imminent (<3d), near (3–14d), distant (≥14d) |
