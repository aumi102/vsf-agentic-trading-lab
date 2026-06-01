---
title: 05_macro_and_bonds
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Macro And Bonds

### Key Terms
<details open>
<summary>Macro and bond data explain the environment around stocks.</summary>
---
#### Macro terms

| Term | Meaning |
|---|---|
| `interest rate` | Cost of borrowing money or return on lending money. |
| `bond` | A debt contract where issuer borrows and investor receives principal plus interest terms. |
| `stock` | Ownership claim on a company, not a loan contract. |
| `yield` | Return implied by a bond price and its cash flows. |
| `coupon` | Fixed interest payment stated on a bond. |
| `yield curve` | Yields across different maturities. |
| `inflation` | General rise in prices. |
| `liquidity` | Availability of cash and funding in the market. |
| `VIX` | US equity option-implied volatility index often used as a fear gauge. |
| `breadth` | How many stocks participate in a market move. |

---
#### Stock vs bond

- **bond** = the issuer owes money to the holder under stated terms.
- **stock** = the holder owns equity and has uncertain upside and downside.
- **bond holder** is a lender.
- **stock holder** is an owner.
- **read** = stocks are not bonds with higher interest; they are a different claim type.

---
</details>

### Mechanism
<details open>
<summary>Rates affect valuation, alternatives, funding cost, and risk appetite.</summary>
---
#### Interest-rate channel

- When rates rise, safer fixed-income returns can become more attractive relative to stocks.
- When rates rise, company borrowing costs can increase.
- When rates rise, future earnings may be discounted more heavily.
- When rates fall, liquidity and risk appetite may improve.
- Read: rates do not mechanically set stock prices, but they shift the environment.

---
#### Bond price and yield

- A bond pays fixed cash flows.
- If market rates rise, old fixed cash flows become less attractive.
- Buyers demand a lower price to earn a higher yield.
- Therefore bond price and yield usually move in opposite directions.

---
#### Worked example

- A bond pays coupon `5%` on par value `100`.
- If market yield is `5%`, price is around `100`.
- If market yield rises to `7%`, the old coupon is less attractive.
- Price must fall below `100` so the buyer earns closer to `7%`.
- Read: rising yields can signal tighter financial conditions.

---
</details>

### Market Sentiment And Breadth
<details open>
<summary>VIX and breadth help the agent distinguish index strength from market-wide strength.</summary>
---
#### VIX

- `VIX` measures S&P 500 option-implied volatility over roughly the next `30` days.
- It often rises when investors demand downside protection.
- A high VIX can indicate fear, but it is not a direct VN stock signal.
- Approximate expected `30`-day move can be estimated as annual VIX divided by `sqrt(12)`.
- Example: VIX `20%` -> `20% / sqrt(12) ≈ 5.77%` expected `30`-day move.

---
#### Breadth

- Breadth checks whether many stocks support an index move.
- If VN-Index rises but most constituents fall, the rally is narrow.
- Narrow rallies can be fragile because index strength depends on a few large names.
- If more than `75%` of stocks are above a moving average, the market may be crowded or overbought.
- If fewer than `25%` of stocks are above a moving average, the market may be oversold.

---
#### Contrarian sentiment

- Extreme optimism can appear near market tops.
- Extreme pessimism can appear near market bottoms.
- The agent should treat contrarian signals as warnings, not automatic reversal trades.

---
</details>

### Risks And Questions
<details open>
<summary>The main risk is forcing macro explanations onto stock moves without evidence.</summary>
---
#### Risks

- **causality risk** = rates, VIX, and breadth can align with stock moves without proving cause.
- **frequency risk** = macro data is often monthly while stock data is daily.
- **country risk** = US macro matters, but its link to VN stocks varies over time.
- **revision risk** = macro series can be revised after first publication.
- **net** = macro is context and regime input first; it becomes a signal only after validation.

---
#### Questions to ask mentor

- Which macro variables are required for MVP: rates, FX, CPI, VIX, or bond yields?
- Should macro be used only for explanation first, or also for strategy features?
- Should the system store macro release dates and vintages from the beginning?
- Which local bond-market fields from VBMA are most useful for Vietnamese equities?

---
</details>
