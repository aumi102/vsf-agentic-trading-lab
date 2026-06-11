# trd2605 Writing and Structure Reference — Archived

**Source:** `docs/conventions/trd2605_a00_writing.md` (archived 2026-06-11)
**Why archived:** Writing style guide for the `trd2605_*` doc series. Exceeded the 1500-word
policy; content is a style reference rather than a project technical doc. Preserved here for
reference when authoring `trd2605_*` series docs.

---

## About

- The writing **and structure** reference for the `trd2605_*` docs.
- One-line summary: **concise, causal, one-pass readable, with a worked example — define each term once, reference by exact heading.**

---

## Document architecture

### The page skeleton

- Open with YAML frontmatter, then nest `## -> ### -> <details open> -> #### -> bullets`.
- Put `---` between `##` sections and around every `<details>` block.
- Do NOT omit frontmatter, write bare `<details>` (always `open`), write `<br>` (must be `<br/>`), or write prose paragraphs (bullets only).

```text
---
title: <filename without .md>
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## <Top-level part>

### <Section>

<details open>
<summary>one plain-text line describing the section</summary>

---

#### <Subsection>

- bullets, one idea each (no paragraphs)

---

</details>
```

Each `###` gets exactly one `<details open>`; the `<summary>` is a descriptive plain-text line.

### Section shapes

- **data family** (a15): `#### Description` → one `#### Representation: <shape>` per shape → `#### What it tells us` → `#### Supports which players`.
- **instrument / player** (a12 / a10): Context → Roles → Flow → Worked example → Mindset.
- **product / app deep-dive** (a30): `#### Snapshot` → `#### Data it supports` → `#### Methods it supports` → `#### Retail & pricing` → `#### How you'd use it` → optional mechanism `####` → `#### Cons` → `#### References`.

### The cast

- Name one concrete example in `#### Description` and reuse it through every representation of that section. Do not introduce a fresh example in each `####`.

### Markdown mechanics

- Backtick-wrap `` `<` `` `` `>` `` `` `$` `` `` `%` `` `` `{` `` `` `}` ``.
- Prefer tables for dense facts; use `->` for arrows.
- Do not leave `%` / `$` / `<` unbacked in text.
- Use `<br/>` not `<br>`.

---

## Clarity and reasoning

- **Write causally:** show *why* a result holds (the cause), not just the answer.
- **Define jargon:** spell out every term a non-trader wouldn't know, at first use.
- **Disambiguate look-alike concepts:** define each separately, then add a one-line "X vs Y".
- **Build non-obvious mechanisms bottom-up:** define the nouns first, then one named level at a time with a worked example.
- **Pre-empt reader confusion:** name the misreading the reader is about to make, and answer it inline.
- **State what it means:** after a mechanic, add the so-what — what it implies, what it is for.

---

## Conciseness and formatting

- One idea per line; split dense lines across lines.
- One point (or one entity) per bullet.
- Keep each bullet on one source line; let the renderer wrap.
- Use `-` bullets; if a sequence needs order, give each step a short **bold label** — do not number steps.
- Bold at most one key term per bullet.

---

## Examples and numbers

- Always include a worked example with concrete numbers — show the arithmetic, not just the rule.
- Unpack procedural terms (pro-rata, rebalance, deploy, roll) — show concretely what they do with numbers.
- Make examples realistic and named (VN context). Show the values, then interpret them.
- Show how a computed value is derived through the model. Keep numbers consistent across the whole doc.

---

## Context

- Frame every example: what, who, why.
- Make each role's job distinct — say what it does AND what it does NOT do.
- Be specific — state the concrete limit/number, not "stays inside its limits".

---

## Definitions and references (keep it DRY)

- Define each standard term once, in `### Key Terms`. Do not re-define it inside every representation.
- Reference by the exact heading — hash level + full title (e.g., `` `#### Representation: NAV + flows` ``).
- A reference adds depth — the sentence must stand without it.

---

## Structure and consistency

- Give every representation the same shape: context → fields defined → sample with real values → how it ties out → takeaway.
- `### Key Terms`: lead with a `Term | Meaning` table; add bullets only for what won't fit a cell.
- Show formulas; name variables; prefer matrix form. Define every field a sample uses.
- Code samples (JSON / jsonc): short one-line comments; flag omitted items and invariants.

---

## Sourcing

- Verify facts; cite authoritative sources for numbers.
- Give every product a `#### Cons`; lead with the most important one. If reviews skew promotional, say so.
