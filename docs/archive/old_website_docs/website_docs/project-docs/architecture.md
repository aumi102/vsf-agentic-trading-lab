---
sidebar_position: 3
---

# Architecture

## Initial Direction

The project starts as a CLI-first autonomous trading agent research lab.

The goal is not to build a full trading platform immediately. The first goal is to design a clean, reviewable, and reproducible pipeline.

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
Signal Generation
  ↓
Decision Layer
  ↓
Risk Control
  ↓
Backtesting
  ↓
Evaluation Report
```

## Design Principles

- Build domain knowledge before development
- Keep the first prototype CLI-first
- Avoid unnecessary backend/frontend complexity
- Use LLMs only when they are useful
- Do not fine-tune LLMs in the early stage
- Always consider cost vs efficiency
