---
title: 04_agent_architecture_plan
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Agent Architecture Plan

### Goal And Principle
<details open>
<summary>The agent should be tool-first, traceable, and conservative in conclusions.</summary>
---
#### Goal

- Turn the architecture docs into an implementable agent plan.
- Define agent roles, tool contracts, decision states, and trace requirements.
- Ensure the final system can answer mentor questions about data flow and failure handling.

---
#### Principle

- The LLM plans and explains.
- Tools compute and validate.
- Traces prove what happened.
- Validation gates decide whether to continue.
- Abstention prevents unsupported conclusions.

---
</details>

### Agent Roles
<details open>
<summary>Start with fewer roles and add specialized agents only when tool outputs become complex.</summary>
---
#### MVP roles

| Role | Job | First tools |
|---|---|---|
| `Orchestrator` | parse request, plan steps, call tools, compose answer | intent parser, trace reader. |
| `Data Agent` | load and validate market data | market data tool, data quality tool. |
| `TA Agent` | compute features and signals | feature tool, signal tool. |
| `Backtest Agent` | simulate strategy and compute metrics | backtest tool. |
| `Risk Agent` | apply validation gates and abstention | validation gate tool, abstention tool. |
| `Evidence Agent` | retrieve reports and macro context | report retrieval, macro lookup. |

---
#### Future roles

- `FA Agent` for financial-statement and company-report analysis.
- `Macro Agent` for FRED, VBMA, rates, inflation, and regime context.
- `Execution Agent` for order book, liquidity, and slippage modeling.
- `Portfolio Agent` for multi-asset allocation and exposure control.

---
</details>

### Tool Contracts
<details open>
<summary>Every tool should return data, status, warnings, and failure reasons.</summary>
---
#### Contract shape

| Field | Meaning |
|---|---|
| `tool_name` | Tool identifier. |
| `input` | Structured input object. |
| `output` | Structured result object. |
| `status` | success, warning, or failure. |
| `warnings` | Non-blocking issues. |
| `failure_reason` | Blocking reason if failed. |
| `trace_id` | Link to stored trace. |

---
#### Worked example

- `market_data_tool` receives `symbol=FPT`, `start=2021-01-01`, `end=2025-12-31`, `timeframe=1d`.
- It returns `1,250` rows and `status=success`.
- `data_quality_tool` checks those rows and returns `status=success`, `missing_days=0`, `duplicates=0`.
- `feature_tool` computes MA20 and MA50.
- `signal_tool` returns `13` entries and `13` exits.
- `backtest_tool` returns metrics.
- `validation_gate_tool` returns `decision=revise`.

---
#### Failure contract

- If a tool fails, it must return `failure_reason`.
- If required input is missing, it must return `missing_input`.
- If data quality fails, downstream tools should not run unless the orchestrator explicitly marks a diagnostic run.
- If metrics are absent, Answer Composer must write `not available` instead of inventing numbers.

---
</details>

### Answer Policy
<details open>
<summary>The final answer must separate observation, interpretation, decision, and limitation.</summary>
---
#### Answer sections

| Section | Content |
|---|---|
| `observed` | Facts returned by tools. |
| `interpretation` | What the facts imply. |
| `decision` | reject, revise, promote, or unanswered. |
| `failed_gates` | Which gates failed and why. |
| `limitations` | Missing data, assumptions, or weak evidence. |
| `next_steps` | What to improve or ask mentor. |

---
#### Unanswered rules

- Return `unanswered` if required market data is missing.
- Return `unanswered` if strategy rules are undefined.
- Return `unanswered` if the user asks for a causal news explanation but evidence is weak or mistimed.
- Return `unanswered` if the user asks for real-money buy/sell advice and the system only has research outputs.
- Return `unanswered` if a required tool failed and no valid fallback exists.

---
</details>

### Review Checklist
<details open>
<summary>This checklist tells whether the architecture is ready for implementation.</summary>
---
#### Checklist

- Every agent role has a clear job.
- Every tool has input, output, status, warning, and failure fields.
- Every output feeds a named next block.
- Every final decision has reason codes.
- Every run is stored in trace.
- Every metric comes from a tool, not the LLM.
- Every unsupported conclusion becomes `unanswered`.

---
#### Questions to ask mentor

- Should the agent be implemented as one orchestrator plus tools first, before sub-agents?
- Should tool traces be user-visible in the demo?
- Which unanswered cases should be mandatory in the demo?
- Should the Answer Composer use a fixed template from day one?

---
</details>
