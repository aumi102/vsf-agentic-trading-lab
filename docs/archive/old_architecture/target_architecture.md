# Target Architecture

## Overview

The project should start as a CLI-first autonomous trading agent research lab.

The initial goal is not to build a full trading platform, but to design a clean and reviewable pipeline that can later evolve into a more complete system.

## High-Level Pipeline

```text
Raw Data
  ↓
Data Cleaning
  ↓
Labeling
  ↓
Feature Engineering
  ↓
Model / Signal Generation
  ↓
Trading Decision Layer
  ↓
Risk Management
  ↓
Backtesting
  ↓
Evaluation Report
```

## Possible Agent Components

```text
Research Agent
  - Reads market news, papers, reports
  - Extracts useful signals or hypotheses

Data Agent
  - Loads structured time-series data
  - Validates missing values, timestamps, schema

Feature Agent
  - Builds technical, statistical, and event-based features

Strategy Agent
  - Produces buy/sell/hold decisions
  - Should not rely only on LLM output

Risk Agent
  - Applies position sizing, stop-loss, exposure limits

Evaluation Agent
  - Runs backtests
  - Reports returns, drawdown, Sharpe ratio, stability
```

## Design Principles

- Keep numerical trading logic deterministic where possible
- Use LLMs mainly for unstructured information and explanation
- Separate research notes from executable scripts
- Avoid building UI before the core pipeline is clear
- Optimize for reviewability and reproducibility
