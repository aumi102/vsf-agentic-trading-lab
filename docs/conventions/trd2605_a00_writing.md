---

title: trd2605_a00_writing

toc_min_heading_level: 2

toc_max_heading_level: 3

---

## About

Writing and structure reference for the `trd2605_*` doc series.

Full content archived at: `notes/archive/trd2605_a00_writing_legacy.md`

---

## Quick reference

- **Skeleton:** YAML frontmatter → `## → ### → <details open> → #### → bullets`; `---` between `##` sections and around every `<details>` block.
- **`<details open>` rule:** every `###` gets exactly one; `<summary>` is a descriptive plain-text line (never "Details").
- **Bullets only:** no prose paragraphs; one idea per bullet; one bullet per source line.
- **Section shapes:** data family (a15), instrument/player (a12/a10), product deep-dive (a30).
- **The cast:** name one concrete example in `#### Description` and reuse it through every representation of that section.

## Clarity rules

- Write causally — show the mechanism before the conclusion.
- Define jargon at first use; disambiguate look-alike concepts.
- State what a result means, not just how it works.
- Pre-empt reader confusion inline.

## Format rules

- Backtick-wrap `` `<` `` `` `>` `` `` `$` `` `` `%` ``; use `<br/>` not `<br>`.
- Bold at most one key term per bullet; use `-` bullets not numbered lists.
- Tables for dense facts; `->` for arrows.

## Examples and numbers

- Always include a worked example with concrete numbers.
- Make examples realistic and VN-named.
- Show how a computed value is derived through the model.
- Keep numbers consistent across the whole doc.

## References (DRY)

- Define each term once in `### Key Terms`; reference by exact heading (`#### hash + full title`).
- A cross-reference adds optional depth — the sentence must stand without it.

## Sourcing

- Verify facts; cite authoritative sources for numbers.
- Every product `####` needs a `#### Cons`; lead with the most important one.
