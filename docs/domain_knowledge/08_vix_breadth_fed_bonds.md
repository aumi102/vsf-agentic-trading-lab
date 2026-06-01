---
title: 08_vix_breadth_fed_bonds
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Fear, Breadth, And Macro Context

### VIX and implied volatility

<details open>
<summary>VIX is a market fear proxy because it reflects expected S&P 500 volatility from options prices.</summary>

---

#### Description

- **Cast:** `us_risk_dashboard` = a market dashboard that tracks `S&P 500`, `VIX`, breadth, sentiment, and policy rate context.
- **VIX:** an index of expected `30`-day volatility implied by S&P 500 option prices.
- **Implied volatility:** market-implied expected movement, not the same as realized movement that already happened.
- **Reader trap:** VIX rising often coincides with equity stress, but it is not a direct sell signal by itself.

---

#### Worked example

- **Given:** VIX = `20%` annualized implied volatility.
- **Approx `30`-day expected move:** `20% / sqrt(12) ≈ 5.77%`.
- **Read:** options imply an approximate one-month move around `5.77%`, not a guaranteed move.
- **Agent caution:** do not say the market will move exactly `5.77%`; say expected volatility is elevated or reduced relative to history.

---

#### Put demand and fear

- **Put option:** a contract that gains value when the underlying falls, often used for hedging.
- **Mechanism:** investors fear downside -> buy puts -> option implied volatility rises -> VIX often rises.
- **Equity relation:** VIX often moves opposite the S&P 500 during stress periods.
- **Unanswered case:** if the agent lacks options data or current VIX value, it should not infer fear from price alone.

---

</details>

---

## Breadth And Sentiment

### Internal strength of the market

<details open>
<summary>Breadth checks whether an index move is supported by many stocks or only a few leaders.</summary>

---

#### Key terms

| Term | Meaning |
|---|---|
| `market breadth` | Balance between rising and falling stocks. |
| `advance-decline` | Count or difference of advancing versus declining stocks. |
| `McClellan Oscillator` | Breadth oscillator using advancing and declining issues. |
| `above moving average` | Share of stocks trading above a chosen moving average. |
| `breadth thrust` | Sudden large improvement in breadth that can mark strong participation. |
| `contrarian sentiment` | Extreme optimism or pessimism used as a possible reversal warning. |

---

#### Worked example

- **Index move:** S&P 500 rises `1.0%` today.
- **Constituent breadth:** `320` stocks rise and `180` stocks fall.
- **Advance ratio:** `320 / 500 = 64.0%`.
- **Read:** the rally has decent breadth because most components participate.
- **Opposite case:** if the index rises but only `120` of `500` stocks rise, the rally may depend on a few large names.

---

#### Overbought and oversold breadth

- **Rule sample:** more than `75%` of stocks above moving average can indicate overbought participation.
- **Rule sample:** fewer than `25%` of stocks above moving average can indicate oversold conditions.
- **Careful:** overbought does not mean immediate crash; it can mean strong trend and high participation.
- **Agent output:** state condition, evidence, and caution instead of issuing a direct trade.

---

</details>

---

## Fed, Bonds, And Asset Choice

### Why rates matter

<details open>
<summary>Rates connect stocks and bonds because they change discount rates and the attractiveness of safer income.</summary>

---

#### Stock vs bond

| Instrument | What the investor owns | Cash-flow logic | Main risk |
|---|---|---|---|
| `stock` | Ownership claim on a company | uncertain future profit and dividends | business and valuation risk |
| `bond` | Loan claim against issuer | coupon and principal repayment schedule | default and interest-rate risk |

---

#### Correcting a common confusion

- **Bond:** a loan contract; investor lends money to government or company.
- **Stock:** ownership; investor owns part of the company, not a debt contract.
- **Stock vs bond:** bondholder is a lender; shareholder is an owner.
- **Yield vs return:** a bond's yield is not simply a higher or lower stock interest rate; it is the market return implied by bond price and payments.

---

#### Price-yield mechanism

- **Old bond:** face value `1000`, coupon `5%`, annual coupon `50`.
- **New market yield rises:** investors now demand `6%`.
- **Why old price falls:** `50` coupon is less attractive when new bonds offer more yield.
- **Approx price intuition:** price must fall below `1000` so `50 / price` becomes closer to `6%`.
- **Read:** bond prices and yields move in opposite directions.

---

#### Agent use

- **Macro feature:** falling rates can support risk assets by lowering discount rates and making bonds less competitive.
- **Risk note:** rate policy is not the only driver; earnings, inflation, liquidity, and shocks can dominate.
- **Unanswered case:** without current rate data and market context, the agent should not claim Fed policy caused a price move.

---

</details>
