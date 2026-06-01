---
title: 04_financial_reports
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Financial Reports

### Key Terms
<details open>
<summary>Financial reports are the structured base of FA.</summary>
---
#### Report terms

| Term | Meaning |
|---|---|
| `income statement` | Report of revenue, costs, and profit over a period. |
| `balance sheet` | Snapshot of assets, liabilities, and equity at a point in time. |
| `cash flow statement` | Report of cash generated and used by operations, investing, and financing. |
| `revenue` | Money earned from selling goods or services. |
| `gross margin` | Gross profit divided by revenue. |
| `net profit` | Profit after costs, interest, and tax. |
| `debt` | Borrowed money the company must repay. |
| `free cash flow` | Cash left after operating needs and capital expenditure. |
| `period` | Quarter or year the report describes. |
| `announcement date` | Date the market could know the report. |

---
#### Accounting period vs announcement date

- **accounting period** says which quarter or year the numbers describe.
- **announcement date** says when the market could react to those numbers.
- A backtest must join by announcement date, not just fiscal period.

---
</details>

### Representation
<details open>
<summary>FA data should preserve statements, periods, and report timing.</summary>
---
#### Cast

- `FPT` = example company.
- `period` = `2025Q1`.
- `announcement_date` = `2025-04-20`.
- `fa_question` = whether the company is improving enough to support a watchlist thesis.

---
#### Table: financial_statement_items

| Field | Meaning |
|---|---|
| `company_id` | Company identity. |
| `statement_type` | income, balance, or cash_flow. |
| `period` | Fiscal period such as `2025Q1`. |
| `announcement_date` | Date the report became known. |
| `item_name` | Revenue, net profit, cash, debt, and other line item. |
| `value` | Numeric value. |
| `unit` | VND, billion VND, shares, percent, or other. |
| `source_id` | Report source. |

---
#### Derived metrics

| Metric | Meaning |
|---|---|
| `revenue_growth_yoy` | Revenue growth compared with the same period last year. |
| `net_profit_growth_yoy` | Net profit growth compared with the same period last year. |
| `gross_margin` | Gross profit divided by revenue. |
| `debt_to_equity` | Debt compared with shareholder equity. |
| `free_cash_flow_margin` | Free cash flow divided by revenue. |

---
</details>

### Worked Example
<details open>
<summary>The agent should compute and interpret values, not just list report numbers.</summary>
---
#### Example values

- `FPT` revenue in `2025Q1` = `16,000bn` VND.
- `FPT` revenue in `2024Q1` = `13,600bn` VND.
- Year-over-year revenue growth = `(16,000 / 13,600) - 1 = 17.65%`.
- Net profit growth = `20%` if net profit rises from `2,500bn` to `3,000bn` VND.
- Announcement date is `2025-04-20`.

---
#### Read

- Revenue growth around `17.65%` supports a positive FA thesis.
- Net profit growth above revenue growth can suggest margin improvement.
- The signal is not tradable before `2025-04-20` because the market did not know the report yet.
- The FA output should become a thesis object, not an immediate buy signal.

---
</details>

### Risks And Questions
<details open>
<summary>The main risk is using revised or future financial data in a historical decision.</summary>
---
#### Risks

- **announcement-date leakage** = joining financial data by fiscal quarter can leak future results.
- **restatement risk** = later revisions may differ from original reports.
- **unit risk** = VND, million VND, and billion VND can be confused.
- **consolidation risk** = parent-only and consolidated statements are different.
- **one-quarter risk** = one good quarter may not define a durable business trend.

---
#### Questions to ask mentor

- Which source should be canonical for financial statements?
- Should the MVP parse financial statements or only store report PDFs first?
- Which financial ratios are mandatory for the first FA Agent?
- Should revised statements overwrite old values or create new vintages?

---
</details>
