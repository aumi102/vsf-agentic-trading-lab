---
title: 03_vbma
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Source Review

### Snapshot
<details open>
<summary>VBMA is a macro and bond-market source, not a stock-price source.</summary>
---
#### Source role

- **source** = Vietnam Bond Market Association.
- **purpose** = collect primary market data, auction calendars, government bond auction plans, actual issuance, and auction results where available.
- **agent usage** = Macro Agent, Bond Agent, Risk Agent, and Strategy Context Agent.
- **official fact** = VBMA lists primary-market pages such as auction calendar, government bond auction plan and actual issuance, and auction result export data.
- **MVP stance** = use VBMA as a macro regime and rates context source, not as a direct buy/sell signal.

---
#### Access surface

- **Access:** public website pages and downloadable exports where available.
- **Build it:** crawl tables or export files after confirming terms and format stability.
- **Your own code:** parser code can normalize tenor, coupon, auction volume, winning yield, issue date, and maturity date.

---
</details>

### Data Categories
<details open>
<summary>Bond data helps explain liquidity, rates, and risk appetite in the equity market.</summary>
---
#### Categories

| Category | Example | Agent use |
|---|---|---|
| auction calendar | upcoming government bond auctions | expected supply and liquidity context. |
| auction plan | planned issuance by tenor | policy and funding context. |
| auction result | offered amount, winning amount, yield | rates and demand context. |
| yield curve | tenor-level yields if available | discount-rate and macro regime input. |
| bond reports | market commentary | macro evidence retrieval. |

---
#### Important fields

- `auction_id` = internal event ID.
- `issuer` = government or related issuer.
- `tenor` = maturity bucket such as `5Y`, `10Y`, or `15Y`.
- `auction_date` = date of auction.
- `issue_date` = date the bond is issued.
- `maturity_date` = date principal is due.
- `offered_amount` = amount offered.
- `winning_amount` = amount accepted.
- `winning_yield` = accepted yield.
- `bid_to_cover` = demand ratio if calculable.

---
</details>

### Proposed Schema
<details open>
<summary>Bond-market data should be event-based and series-based.</summary>
---
#### Tables

| Table | Fields | Notes |
|---|---|---|
| `bond_auctions` | `auction_id`, `issuer`, `auction_date`, `tenor`, `offered_amount`, `winning_amount`, `winning_yield`, `source_id` | one auction row. |
| `bond_instruments` | `bond_id`, `issuer`, `coupon`, `issue_date`, `maturity_date`, `currency` | optional instrument master. |
| `yield_curve_points` | `curve_date`, `tenor`, `yield`, `source_id` | one row per tenor per date. |
| `bond_reports` | `report_id`, `published_at`, `title`, `raw_path`, `source_id` | document evidence. |

---
#### Worked example

- **auction** = `10Y` government bond auction.
- **offered amount** = `5,000bn` VND.
- **winning amount** = `3,000bn` VND.
- **bid-to-cover proxy** = if bids are `7,500bn`, then demand ratio is `7,500 / 5,000 = 1.5x`.
- **read** = stronger demand and lower yields can suggest easier local funding conditions, but the equity agent must still connect this to stock data carefully.

---
</details>

### Quality And Usage
<details open>
<summary>The main risk is overclaiming a direct causal link from bond data to stock moves.</summary>
---
#### Data quality issues

- **frequency mismatch** = bond auctions are event-based while stocks trade daily.
- **unit issue** = amounts may be reported in VND, billion VND, or another unit.
- **tenor normalization** = `10 years`, `10Y`, and `120M` should map to the same tenor.
- **missing demand fields** = bid amount may not always be available.
- **causality issue** = lower yields can support equities, but it does not prove a single-stock move.

---
#### Agent rules

- Macro Agent can use VBMA to describe local rates and bond-market conditions.
- Risk Agent can treat yield spikes as a regime warning.
- Strategy Agent should use bond data as context, not as a standalone trade trigger.
- Answer Composer must say `possible macro context`, not `proven cause`, unless evidence is stronger.

---
#### Cons and references

- **main con** = public pages may not provide a complete historical API.
- **net** = VBMA is useful for macro/bond context, but needs careful frequency alignment.
- `REF_VBMA_PRIMARY_MARKET`: VBMA primary-market data page.

---
</details>
