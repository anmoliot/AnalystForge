# Quantitative Finance Formulas Specification

All financial calculations are implemented in pure Python with exact `Decimal` arithmetic under `packages/quant`.

---

## 1. Valuation Models

### 1.1 Discounted Cash Flow to Firm (FCFF)
$$\text{NOPAT}_t = \text{EBIT}_t \times (1 - \text{Tax Rate})$$
$$\text{FCFF}_t = \text{NOPAT}_t + \text{D\&A}_t - \text{CapEx}_t - \Delta\text{NWC}_t$$
$$\text{PV}(\text{FCFF}) = \sum_{t=1}^N \frac{\text{FCFF}_t}{(1 + \text{WACC})^t}$$
$$\text{Terminal Value}_N = \frac{\text{FCFF}_N \times (1 + g)}{\text{WACC} - g}$$
$$\text{Enterprise Value} = \text{PV}(\text{FCFF}) + \frac{\text{Terminal Value}_N}{(1 + \text{WACC})^N}$$
$$\text{Equity Value} = \text{Enterprise Value} - \text{Net Debt}$$
$$\text{Implied Share Price} = \frac{\text{Equity Value}}{\text{Shares Outstanding}}$$

### 1.2 Free Cash Flow to Equity (FCFE)
$$\text{FCFE}_t = \text{Net Income}_t + \text{D\&A}_t - \text{CapEx}_t - \Delta\text{NWC}_t + \text{Net Borrowing}_t$$
$$\text{PV}(\text{FCFE}) = \sum_{t=1}^N \frac{\text{FCFE}_t}{(1 + r_e)^t}$$
$$\text{Terminal Value}_N = \frac{\text{FCFE}_N \times (1 + g)}{r_e - g}$$
$$\text{Equity Value} = \text{PV}(\text{FCFE}) + \frac{\text{Terminal Value}_N}{(1 + r_e)^N}$$
$$\text{Implied Share Price} = \frac{\text{Equity Value}}{\text{Shares Outstanding}}$$

### 1.3 Dividend Discount Model (DDM)
#### Single-Stage Gordon Growth:
$$P_0 = \frac{D_1}{r_e - g} = \frac{D_0 \times (1 + g)}{r_e - g}$$
$$\text{Dividend Yield} = \frac{D_1}{P_0}$$

#### Multi-Stage DDM:
$$P_0 = \sum_{t=1}^N \frac{D_t}{(1 + r_e)^t} + \frac{D_N \times (1 + g_L)}{(r_e - g_L) \times (1 + r_e)^N}$$

### 1.4 Residual Income Model (Edwards-Bell-Ohlson)
$$\text{Equity Charge}_t = r_e \times \text{BV}_{t-1}$$
$$\text{Residual Income}_t (\text{RI}_t) = \text{Net Income}_t - \text{Equity Charge}_t = (\text{ROE}_t - r_e) \times \text{BV}_{t-1}$$
$$\text{Clean Surplus Relation}: \text{BV}_t = \text{BV}_{t-1} + \text{Net Income}_t - \text{Dividends}_t$$
$$\text{Equity Value} = \text{BV}_0 + \sum_{t=1}^N \frac{\text{RI}_t}{(1 + r_e)^t} + \frac{\text{Terminal Value}_N}{(1 + r_e)^N}$$

### 1.5 Cost of Capital & CAPM
$$\text{CAPM Cost of Equity}: r_e = r_f + \beta \times \text{ERP}$$
$$\text{Blume Adjusted Beta}: \beta_{\text{adj}} = \frac{2}{3}\beta_{\text{raw}} + \frac{1}{3}(1.0)$$
$$\text{After-Tax Cost of Debt}: r_{d,\text{after-tax}} = r_d \times (1 - t)$$
$$\text{WACC} = \left(\frac{E}{V}\right) \times r_e + \left(\frac{D}{V}\right) \times r_d \times (1 - t)$$
$$\text{Hamada Unlevered Beta}: \beta_u = \frac{\beta_l}{1 + (1 - t) \times (D / E)}$$
$$\text{Hamada Relevered Beta}: \beta_l = \beta_u \times [1 + (1 - t) \times (D / E)]$$

### 1.6 Comparable Companies (Peer Multiples)
$$\text{EV/EBITDA} = \frac{\text{Market Cap} + \text{Total Debt} - \text{Cash}}{\text{EBITDA}}$$
$$\text{P/E} = \frac{\text{Market Cap}}{\text{Net Income}} = \frac{\text{Price}}{\text{EPS}}$$
$$\text{P/B} = \frac{\text{Market Cap}}{\text{Book Value of Equity}}$$
$$\text{PEG} = \frac{\text{P/E}}{\text{Annual Earnings Growth Rate (\%)}}$$
$$\text{Implied Equity Value (Enterprise Multiple)} = \text{Metric} \times \text{Peer Multiple} - \text{Net Debt}$$
$$\text{Implied Equity Value (Equity Multiple)} = \text{Metric} \times \text{Peer Multiple}$$

### 1.7 Sum of the Parts (SOTP)
$$\text{Total Enterprise Value} = \sum_{i=1}^M (\text{Segment Metric}_i \times \text{Segment Multiple}_i \times \text{Ownership}_i)$$
$$\text{Equity Value} = \text{Total EV} - \text{Net Debt} - \text{Minority Interest} + \text{Investments} - \text{Corp Overhead PV}$$
$$\text{Implied Share Price} = \frac{\text{Equity Value}}{\text{Shares Outstanding}}$$

### 1.8 Precedent Transactions
$$\text{Deal Multiple} = \frac{\text{Transaction Enterprise Value}}{\text{Target LTM Metric}}$$
$$\text{Implied Target Valuation} = \text{Target Metric} \times \text{Multiple}_{\text{Deal Percentile}} - \text{Net Debt}$$

---

## 2. Portfolio Mathematics

### 2.1 Money-Weighted Return (MWR / XIRR)
Find $r$ solving:
$$\sum_{i=0}^T \frac{C_i}{(1 + r)^{\frac{d_i - d_0}{365}}} = 0$$

### 2.2 Time-Weighted Return (TWR)
$$R_{\text{TWR}} = \prod_{k=1}^K (1 + R_k) - 1$$

### 2.3 Risk Metrics
$$\text{Annualized Volatility}: \sigma_{\text{ann}} = \sigma_{\text{daily}} \times \sqrt{252}$$
$$\text{Sharpe Ratio}: \frac{R_p - R_f}{\sigma_p}$$
$$\text{Sortino Ratio}: \frac{R_p - R_f}{\sigma_{\text{downside}}}$$
$$\text{Information Ratio}: \frac{R_p - R_b}{\text{Tracking Error}}$$
$$\text{Parametric VaR}_{\alpha}: - (\mu + z_{\alpha} \times \sigma)$$
$$\text{Expected Shortfall (CVaR)}_{\alpha}: - \mathbb{E}[R \mid R \le -\text{VaR}_{\alpha}]$$

### 2.4 Brinson-Fachler Performance Attribution
$$\text{Allocation Effect}: A_i = (w_{p,i} - w_{b,i}) \times (R_{b,i} - R_b)$$
$$\text{Selection Effect}: S_i = w_{b,i} \times (R_{p,i} - R_{b,i})$$
$$\text{Interaction Effect}: I_i = (w_{p,i} - w_{b,i}) \times (R_{p,i} - R_{b,i})$$
$$\text{Total Active Return} = \sum_i (A_i + S_i + I_i)$$

### 2.5 Fama-French Multi-Factor Regression
$$R_{p,t} - R_{f,t} = \alpha + \beta_{\text{Mkt}} (R_{m,t} - R_{f,t}) + \beta_{\text{SMB}} \text{SMB}_t + \beta_{\text{HML}} \text{HML}_t + \epsilon_t$$
$$\text{Annualized Alpha}: \alpha_{\text{ann}} = \alpha_{\text{daily}} \times 252$$
$$\text{Residual Volatility}: \sigma_{\epsilon,\text{ann}} = \sqrt{\frac{1}{N - k} \sum \epsilon_t^2} \times \sqrt{252}$$

### 2.6 Rolling Statistics
$$\sigma_{\text{roll}, t} = \sqrt{\frac{1}{W - 1} \sum_{s=t-W+1}^t (R_s - \bar{R})^2} \times \sqrt{252}$$
$$\beta_{\text{roll}, t} = \frac{\text{Cov}_{W}(R_p, R_b)}{\text{Var}_{W}(R_b)}$$
$$\text{MDD}_{\text{roll}, t} = \min_{s \in [t-W+1, t]} \left( \frac{P_s - \max_{\tau \le s} P_{\tau}}{\max_{\tau \le s} P_{\tau}} \right)$$

### 2.7 Portfolio Rebalancing & Turnover
$$\text{Target Dollars}_i = \text{Portfolio Value} \times w_i^{\text{target}}$$
$$\text{Target Shares}_i = \frac{\text{Target Dollars}_i}{P_i}$$
$$\text{Delta Shares}_i = \text{Target Shares}_i - \text{Current Shares}_i$$
$$\text{Turnover (One-Way)} = \frac{1}{2} \sum_{i=1}^N |w_i^{\text{target}} - w_i^{\text{current}}|$$
$$\text{Turnover Constraint}: \frac{1}{2} \|w - w_{\text{initial}}\|_1 \le \text{Turnover Cap}$$
$$\text{Sector Caps}: \sum_{i \in \text{Sector}_k} w_i \le \text{Cap}_k$$

### 2.8 Black-Litterman Asset Allocation
$$\text{Prior Equilibrium Returns}: \Pi = \delta \Sigma w_{\text{mkt}}$$
$$\text{Posterior Returns}: E[R] = \left[ (\tau \Sigma)^{-1} + P^T \Omega^{-1} P \right]^{-1} \left[ (\tau \Sigma)^{-1} \Pi + P^T \Omega^{-1} Q \right]$$
$$\text{Posterior Covariance}: \Sigma_{\text{post}} = \Sigma + \left[ (\tau \Sigma)^{-1} + P^T \Omega^{-1} P \right]^{-1}$$
$$\text{Optimal Weights}: w^* = (\delta \Sigma_{\text{post}})^{-1} E[R]$$
