---

title: trd2605_a00_writing

toc_min_heading_level: 2

toc_max_heading_level: 3

---

## About

- The writing **and structure** reference for the `trd2605_*` docs — enough to reproduce their style, shape, and level of detail.

- `## Document architecture` = the page skeleton `+` section shapes; the rest = writing rules, each a **Do** / **Don't** / example (❌ -> ✅).

- One-line summary: **concise, causal, one-pass readable, with a worked example — define each term once, reference by exact heading.**

- For a **product / app deep-dive** (a30): describe it by its access surface, build its core mechanism up in levels, and end with an honest `#### Cons` — depth over breadth.

---

## Document architecture

### The page skeleton

- **Do:** open with YAML frontmatter, then nest `## -> ### -> <details open> -> #### -> bullets`; put `---` between `##` sections and around every `<details>` block.

- **Don't:** omit the frontmatter, use a bare `<details>` (always `open`), write `<br>` (must be `<br/>`), or write prose paragraphs (bullets only).

- **Skeleton:**

```text
---
title: <filename without .md>          # title MUST equal the filename
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

  - each `###` gets exactly one `<details open>`; the `<summary>` is a descriptive plain-text line (never "Details").

  - the block opens with `---` and ends with `---` before `</details>`; `####` subsections are `---`-separated.

### A section's anatomy (pick a shape, apply it consistently)

- **Do:** give every section of the same type the same parts, in the same order. The recurring shapes:

  - **data family** (a15): `#### Description` (`+` a cast) -> one `#### Representation: <shape>` per data shape -> `#### What it tells us` (a pointer list) -> `#### Supports which players` (a table mapping to the a10 player groups).

  - **instrument / player** (a12 / a10): Context -> Roles -> Flow (or the player template) -> Worked example -> Mindset.

  - **product / app deep-dive** (a30): `#### Snapshot` -> `#### Data it supports` -> `#### Methods it supports` -> `#### Retail & pricing` -> `#### How you'd use it` -> a mechanism `####` only if the core is non-obvious (e.g. `#### How signals combine`) -> `#### Cons` -> `#### References`.

- **Don't:** invent a new layout per section, or answer the questions inline in `#### What it tells us` (it only points to the representation that answers each).

- **Example:** `### Risk And Covariance` = Description (cast `fund_a`) -> `#### Representation: Security-level risk` … -> `#### What it tells us` -> `#### Supports which players`; each representation follows `## Structure & consistency` -> `### Give every representation the same shape`.

### Describe a product by its access surface (form / build / your code)

- **Do:** open every product's `#### How you'd use it` with the same triad, before the click-path:

  - **Access:** the form — desktop app / web / mobile (`+` the OS, if it bites).

  - **Build it:** how the user assembles logic — no-code visual / drag-drop / expression builder.

  - **Your own code:** can the user write code, in what language, and is it **embedded** in the platform or only **exported** — `+` at what scope (one signal vs the whole combination).

- **Don't:** bury the platform form in prose, or say "supports code" without the language `+` whether it is in-app or export-only.

- **Example:**

  - ❌ "a no-code tool that also lets you code".

  - ✅ "**Access:** Windows desktop. **Build it:** point-and-click GUI. **Your own code:** a custom signal in `Python`, imported as a block — not the combination" (a30 `### Build Alpha`).

### The cast — one reused example per section

- **Do:** name one concrete example in `#### Description` and reuse it (same names, same numbers) through every representation of that section.

- **Don't:** introduce a fresh, unrelated example in each `####`.

- **Example:** `### Index And Benchmark` reuses `VN30` with `VIC` / `HPG`; `### Risk And Fund Data` reuses the fund `fund_a` (≈ `E1VFVN30`).

### Markdown mechanics

- **Do:** backtick-wrap `` `<` `` `` `>` `` `` `$` `` `` `%` `` `` `{` `` `` `}` ``; prefer tables for dense facts (multi-line cells via self-closing `<br/>`, each bullet prefixed so it stands alone); use `->` for arrows.

- **Don't:** leave `%` / `$` / `<` unbacked; build a wide table that scrolls; write `<br>` instead of `<br/>`.

- **Example:** ❌ "`loss <40% on $800K`" -> ✅ "loss `<40%` on `$800K`".

---

## Clarity & reasoning

### Write causally — mechanism before conclusion

- **Do:** show *why* a result holds, step by step (the cause), not just the answer.

- **Don't:** drop a formula or conclusion with no derivation.

- **Example:**

  - ❌ `ex-date = record − settlement`.

  - ✅ to get the benefit you must be on the register; the register needs a *settled* trade; `HOSE` settles `T+2`; so buy by `record − 2`, and the next day (`record − 1`) is ex.

### Define jargon; write for a non-expert

- **Do:** spell out every term a non-trader wouldn't know, at first use.

- **Don't:** lean on bare jargon (`book`, `exposure`, `redemption`, `ex-date`).

- **Example:**

  - ❌ "the book's factor exposure".

  - ✅ "exposure = how sensitive the **whole fund** is to a force like the market (a beta) — not how much of a stock you hold".

### Disambiguate look-alike concepts

- **Do:** when two terms are easily confused, define **each** separately, then add a one-line "X vs Y" — ideally with an everyday analogy.

- **Don't:** use them interchangeably, or define one and leave the other implied.

- **Example:**

  - ❌ `book` and `holdings` used as if identical.

  - ✅ "**book** = the managed whole (your account); **holdings** = its line-by-line contents (the statement) — same portfolio, different framing".

### Build a non-obvious mechanism up in named levels

- **Do:** when a product's core is not obvious, give it its own `####` and build it bottom-up: **define the nouns first** (smallest to largest), then one **named level** at a time, each with a worked example `+` its meaning.

- **Don't:** explain it in one dense pass, or use a term (`strategy`, `ensemble`) before you have defined it.

- **Example:**

  - ✅ `#### How signals combine` (a30 `### Build Alpha`): define `signal` / `strategy` / `ensemble`, then `Level 1` (one signal) -> `Level 2` (signals -> a strategy) -> `Level 3` (strategies -> an ensemble), each with a worked example `+` what it means.

### Pre-empt the reader's predictable confusion

- **Do:** name the misreading the reader is about to make, and answer it inline as its own bullet.

- **Don't:** leave a look-alike step or a reused word to be silently misread.

- **Example:**

  - ✅ "'isn't this just Level 1?' — for a rule you already know, almost; the real split is author-vs-search".

  - ✅ "careful — 'picks 2 of 3' here means which signals are *included* — **not** the `2-of-3` voting of Level 3; same words, different thing" (a30 `### Build Alpha`).

### State what it means, not just how it works

- **Do:** after a mechanic / step / combination, add the **so-what** — what it implies, what it is for, what it buys you. (For a *number*, use `## Examples & numbers` -> `### Show the values, then interpret them`.)

- **Don't:** leave a correct mechanic with no interpretation.

- **Example:**

  - ❌ "entry `=` `RSI(2) < 10` `AND` `Close > SMA(200)`".

  - ✅ that `+` "meaning: stacking `AND`-conditions filters to fewer, higher-conviction trades — here 'buy the dip, but only in an uptrend'".

---

## Conciseness & formatting

### Short sentences — break long ones into multiline

- **Do:** one idea per line; split a dense line across lines.

- **Don't:** pack clauses, parentheticals, and examples into one sentence.

- **Example:**

  - ❌ `= E[ wᵀ(r−μ)(r−μ)ᵀw ] (scalar a²=a·aᵀ, a=wᵀ(r−μ)) = wᵀΣw`.

  - ✅ each step on its own line; the justification on its own `//` line beneath it.

### One point (or one entity) per bullet

- **Do:** give each actor / fact its own bullet.

- **Don't:** cram several roles into one bullet.

- **Example:**

  - ❌ "outside investors' money; an asset manager runs it; the risk team updates it".

  - ✅ `asset manager` — runs the fund. / `investors` — own the units. / `risk team` — updates the record.

### Keep each bullet on one source line

- **Do:** let the renderer wrap; one bullet = one line in the source.

- **Don't:** hard-wrap a bullet at ~80 chars (noisy diffs).

- **Example:**

  - ✅ a long bullet stays one source line; if it feels too long, split into a parent `+` sub-bullets.

### Use bullets, not numbered lists

- **Do:** use `-` bullets; if a sequence needs order, give each step a short **bold label**.

- **Don't:** number steps (`1.`, `2.`, `3.`) or headings.

- **Example:**

  - ❌ "`1.` pick the shock / `2.` set the factors / `3.` compute".

  - ✅ "**pick the shock** / **set the factors** / **compute**" as bullets.

### Use bold sparingly

- **Do:** bold at most one key term per bullet.

- **Don't:** bold every phrase.

- **Example:**

  - ❌ "**high** `cov` **inflates** risk; **negative** `cov` **cancels** it".

  - ✅ "high `cov` inflates risk; negative `cov` partly **cancels** it".

---

## Examples & numbers

### Always include a worked example with concrete numbers

- **Do:** show the arithmetic, not just the rule.

- **Don't:** state a metric with no number.

- **Example:**

  - ❌ "`VaR` = the loss you stay under at a confidence".

  - ✅ "daily vol `1.1%` at `95%`: `1.65 × 1.1% ≈ 1.8%` -> on a `10bn` book ≈ `180m`".

### Unpack a procedure, don't just name it

- **Do:** when a sentence uses a procedural term (pro-rata, rebalance, deploy, roll), show concretely what it does — with the numbers.

- **Don't:** leave the reader to guess what "do X pro-rata" means.

- **Example:**

  - ❌ "deploy the flow pro-rata across the basket so weights don't drift".

  - ✅ "pro-rata = split the new cash by current weights — `HPG 11%` gets `11%` of it, `VIC 9%` gets `9%` — so every holding grows the same `%` and the weights stay put".

### Make examples realistic and named (VN)

- **Do:** use a real VN name when it grounds the point.

- **Don't:** stay abstract when a concrete name would help.

- **Example:**

  - ❌ "an equity fund".

  - ✅ "a long-only VN equity fund like VinaCapital's `VEOF`".

### Show the values, then interpret them

- **Do:** give a sample with values, then a plain-words "read".

- **Don't:** give numbers with no interpretation (or interpretation with no numbers).

- **Example:**

  - ❌ "`VaR` is the daily loss limit".

  - ✅ sample: `1-day 95% VaR = 1.8% = 180m`. read: lose under `180m` on `95%` of days; more on the worst ~`1` day in `20`.

### Show how a computed value is derived

- **Do:** show the method behind a modelled value (a scenario P&L, a `VaR`, a fee). If a model already defines it, derive it **through that model** and reference the model — not a one-off formula.

- **Don't:** drop a derived number (`-0.16`) with only a vague label ("modelled P&L").

- **Example:**

  - ❌ `"scn_2018_selloff": -0.16  // modelled P&L`.

  - ✅ run the factor regression with a shocked factor: `Fₘₖₜ −19%` (2018) × book `β 0.85` ≈ `−16%` -> `−0.16` (reference the `Factor model` block).

### Keep numbers consistent across the whole doc

- **Do:** when a value changes, fix it everywhere it appears.

- **Don't:** leave the same quantity at different values in different sections.

- **Example:**

  - ❌ `HPG` final weight `5%` in the sample but `8%` in the cast.

  - ✅ `HPG ~8%` in the cast, sample, rep, and Holdings — one consistent story.

---

## Context

### Frame every example: what, who, why

- **Do:** say what the thing is, who owns it, who updates it, and for what purpose.

- **Don't:** drop a sample (`fund_a`, `book`) with no backstory.

- **Example:**

  - ❌ "Context: one record per book per day".

  - ✅ "`fund_a` = a VN equity fund; **investors** own it; the asset manager's **risk team** strikes it daily to police the mandate".

### Make each role's job distinct

- **Do:** when you list several roles, give each its side and its one job; if they're confusable, add what it does NOT do (and how they relate).

- **Don't:** list parallel-looking roles the reader can't tell apart or assumes are one office.

- **Example:**

  - ❌ "administrator strikes NAV; manager runs the book; LP reads fees" — all sound like one back office.

  - ✅ "investor **owns** the money; manager **runs** it (for a fee); administrator (**independent**) holds `+` values it — three separate parties".

### Be specific — give the actual rule, not a vague mention

- **Do:** state the concrete limit / number.

- **Don't:** say "inside its limits" and stop.

- **Example:**

  - ❌ "stays inside its mandate limits".

  - ✅ "`SSC`: all of one company's securities ≤ `10%` of `NAV`; internal: a `drawdown` stop at `−10%`".

---

## Definitions & references (keep it DRY)

### Define each standard term once, in Key Terms

- **Do:** put standard terms (`beta`, `VaR`, covariance, settlement) in the right `####` of `### Key Terms`.

- **Don't:** define the same term inside every representation.

- **Example:**

  - ✅ `beta` / `VaR` / `Sharpe` defined in `### Key Terms` -> `#### Risk & portfolio terms`.

### Reference Key Terms; don't repeat the definition

- **Do:** in a representation, point to the Key Terms entry and just *apply* it (own sample + numbers).

- **Don't:** restate the mechanic the term already carries.

- **Example:**

  - ❌ re-explaining `var_95_1d` inside the rep.

  - ✅ "fields defined in `### Key Terms` -> `#### Risk & portfolio terms`" + the rep's worked reading.

### Reference by the exact heading — hash level `+` full title

- **Do:** point to a section / block by its real heading: the hash (`####`) `+` the full title (`#### Representation: NAV + flows`), so it is greppable. Give an unnamed block a clear bold name first.

- **Don't:** shorten the title (`NAV + flows`), drop the hash, or write "see below" / "the block below".

- **Example:**

  - ❌ "see `NAV + flows`" / "the block below".

  - ✅ "see `#### Representation: NAV + flows`"; cross-section: "`## Risk And Fund Data` -> `### Fund / Portfolio` -> `#### Representation: Holdings`".

### A reference adds detail — the sentence must stand without it

- **Do:** state the point in plain words inline; make the cross-reference optional depth ("detail: …").

- **Don't:** write a line the reader can't understand until they open the referenced section.

- **Example:**

  - ❌ "active weights feed the **tilt view** (`### Index And Benchmark` -> `Constituents + weights`)".

  - ✅ "the active weights add up to how far the fund strays from its index — its tilt (detail: `### Index And Benchmark` -> `Constituents + weights`)".

---

## Structure & consistency

### Give every representation the same shape (one-pass readable)

- **Do:** structure each `#### Representation` like its siblings — context (what / who / why) -> fields defined -> a sample with real values -> how it ties out -> a takeaway — so it reads in one pass.

- **Don't:** leave one representation bare (just "Used by" `+` a sample) while the one above it is rich.

- **Example:**

  - ❌ `#### Representation: Book aggregate` as only "Used by" `+` a JSON sample.

  - ✅ the same `####` with context (`fund_a` = a VN fund the asset manager's risk team updates daily to police the mandate), each field defined, the sample's values, and a worked reading — matching the `####` above it.

### Key Terms: lead with a table, bullets after

- **Do:** start each Key-Terms `####` with a `Term | Meaning` table; add bullets only for what won't fit a cell (a derivation, a worked example).

- **Don't:** write a wall of bullets where a table belongs.

- **Example:**

  - ✅ `#### Index & benchmark terms` opens with the term table, then the worked weight-build below it.

### Show the formula; name the variables; prefer matrix form

- **Do:** give the formula, name each symbol, derive multiline (one step per line); use vector/matrix form when cleaner.

- **Don't:** present a derivation as one dense line, or a formula with unnamed symbols.

- **Example:**

  - ✅ `R_p = wᵀr` -> name `w` (weights), `r` (returns), `Σ` (covariance) -> derive to `wᵀΣw`, one step per line.

### Define every field a sample uses

- **Do:** before (or beside) a JSON sample, define each field — what it is, its unit, how it's built.

- **Don't:** show a sample with undefined fields and assume the name explains itself.

- **Example:**

  - ❌ `"scn_2018_selloff": -0.16` with no definition.

  - ✅ first define "`scn_*` = scenario P&L: the loss if that shock hit today's book; `bp` = basis point = `0.01%`", then show the sample.

### Code samples (JSON / jsonc)

- **Do:** short one-line comments; flag omitted items and invariants.

- **Don't:** long-sentence comments; markdown backticks inside code; a `|` inside a table cell.

- **Example:**

  - ✅ `// ...28 more names` and `// sum of all 30 w = 1.00`.

  - ❌ `not |return|` inside a table cell -> use `abs(return)` (a `|` breaks the table).

---

## Sourcing

### Verify facts; cite authoritative sources for numbers

- **Do:** research and confirm quoted figures, then add a `REF_` for them.

- **Don't:** assert a number (settlement cycle, a cap, a methodology) from memory.

- **Example:**

  - ✅ stocks `T+2` settlement (cite VSD / HOSE); the index `10%` cap `+` redistribution (cite the capping methodology).

### Give an honest Cons — and flag weak sourcing

- **Do:** give every product a `#### Cons`; lead with the **most important** one and mark it, and close with a one-line "net". If public sources skew promotional or you could not reach independent ones, say so up front.

- **Don't:** present a product all-upside, or hide that the cons are thin because the reviews are vendor-positive.

- **Example:**

  - ✅ a30 `### Build Alpha` -> `#### Cons`: an honest caveat (reviews skew promotional), a table led by **data-mining bias** ("the big one"), each con sourced — including the vendor's own admission — then a "net".

---
