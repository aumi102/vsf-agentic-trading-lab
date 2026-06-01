# Docusaurus Notes

## Why Docusaurus?

Docusaurus can be used later to turn project documentation into a readable documentation website.

This is useful because the project is design-heavy and research-heavy. A documentation website makes it easier for mentors and teammates to review:

- Research notes
- Architecture decisions
- Pipeline design
- Experiment logs
- Future development roadmap

## Suggested Timing

Docusaurus does not need to be the first task.

Recommended order:

1. Clean repository structure
2. Push public-safe notes to GitHub
3. Add core architecture docs
4. Add CLI scripts
5. Scaffold Docusaurus when documentation becomes larger

## Possible Future Command

```bash
npx create-docusaurus@latest docs-site classic --typescript
```

Then:

```bash
cd docs-site
npm start
```
