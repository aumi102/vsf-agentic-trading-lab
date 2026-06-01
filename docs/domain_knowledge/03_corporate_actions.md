---
title: 03_corporate_actions
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Corporate Actions

### Key Terms
<details open>
<summary>Corporate actions change the relationship between price, shares, and returns.</summary>
---
#### Corporate-action terms

| Term | Meaning |
|---|---|
| `dividend` | Cash or stock distribution from company to shareholders. |
| `cash dividend` | Payment in cash per share. |
| `stock dividend` | Additional shares distributed to holders. |
| `split` | Share count changes while economic ownership stays roughly the same. |
| `rights issue` | Existing holders receive rights to buy new shares. |
| `ex-date` | First date the stock trades without the benefit of the action. |
| `record date` | Date used to determine eligible holders. |
| `adjusted price` | Historical price transformed to make return calculation comparable across actions. |
| `raw price` | Price as traded on the day, without adjustment. |

---
#### Raw price vs adjusted price

- **raw price** is what the market printed.
- **adjusted price** is used to compute historical returns consistently.
- A backtest should know which one it uses.
- Mixing raw and adjusted prices can create fake drawdowns or fake profits.

---
</details>

### Mechanism
<details open>
<summary>Corporate actions can make a price drop look like a loss when it is not.</summary>
---
#### Cast

- `FPT` = example stock.
- `cash_dividend` = `2,000` VND per share.
- `pre_ex_close` = `100,000` VND.
- `ex_date_open` = roughly `98,000` VND if the dividend effect is reflected.

---
#### Cash dividend example

- Before ex-date, the share closes at `100,000` VND.
- The company pays a `2,000` VND cash dividend.
- On ex-date, the price can mechanically adjust down by about `2,000` VND.
- A raw close-to-close calculation may show `-2%`.
- The investor did not necessarily lose `2%`, because the dividend is received separately.
- Read: backtest returns must include dividends or use adjusted prices.

---
#### Stock split example

- A `2-for-1` split doubles the number of shares.
- A `100,000` VND raw price may become around `50,000` VND.
- Economic value is roughly unchanged before market movement.
- A raw price chart may show a `-50%` drop.
- Read: unadjusted price will destroy return calculations around split dates.

---
</details>

### Schema Representation
<details open>
<summary>Corporate actions need event dates, terms, and adjustment factors.</summary>
---
#### Table: corporate_actions

| Field | Meaning |
|---|---|
| `action_id` | Internal event ID. |
| `security_id` | Affected security. |
| `action_type` | dividend, split, rights, merger, delisting, or other. |
| `announcement_date` | Date the action was announced. |
| `ex_date` | First date trading without entitlement. |
| `record_date` | Date eligibility is determined. |
| `payment_date` | Date benefit is paid when available. |
| `ratio` | Split or stock dividend ratio when available. |
| `cash_amount` | Cash dividend per share when available. |
| `adjustment_factor` | Factor used to adjust historical prices. |
| `source_id` | Source record. |

---
#### Agent use

- Data Agent uses corporate actions to validate price jumps.
- Backtest Agent uses adjusted returns or total-return logic.
- Risk Agent checks whether large drawdowns are real or corporate-action artifacts.
- Answer Composer should mention when a result depends on adjusted-price availability.

---
</details>

### Risks And Questions
<details open>
<summary>The main risk is backtesting raw prices as if they were total-return data.</summary>
---
#### Risks

- **fake loss risk** = cash dividend creates a raw price drop that is not a pure capital loss.
- **fake crash risk** = split creates a huge raw price move.
- **lookahead risk** = using an action before its announcement date can leak future information.
- **schema risk** = missing ex-date makes adjustment timing ambiguous.
- **net** = VN stock backtests should not be trusted until corporate-action handling is explicit.

---
#### Questions to ask mentor

- Can MVP backtest use adjusted close from a trusted vendor?
- Which corporate actions are mandatory for the first VN equity demo?
- Should raw and adjusted prices be stored in the same table or separate tables?
- Should the first strategy avoid periods with missing corporate-action data?

---
</details>
