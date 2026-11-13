# Agent rules

Four people work in this repo at the same time, each with their own coding agent, for the Datathon FME
2026 (challenge revealed Saturday 10:00, submission Sunday 12:00). These rules keep us from breaking
each other's work. The human-facing version is `COM-TREBALLEM.md`.

## Commands

- Install: `uv sync`
- Tests: `uv run pytest`
- Lint: `uv run ruff check` (fix with `uv run ruff check --fix`, format with `uv run ruff format`)
- Add a dependency: `uv add <package>`; never edit `uv.lock` by hand

## Before planning any task

Read `docs/challenge/` (what the company asked for), `CONTRACTS.md` (what the lanes agreed) and
`GLOSSARY.md` (the words we use). If the task contradicts one of them, say so before writing code.

## Workflow per task

1. **Align.** Use the `grill-with-docs` skill before any task bigger than a small fix. No code until
   the user confirms the shared understanding.
2. **Prototype** only when a question needs to be seen to be answered: use the `prototype` skill on a
   throwaway branch. Only the decision reaches `main`.
3. **Build** in small vertical slices. Every task has a pass/fail check you can run (a test, the
   evaluation script, the submission format check). Use the `tdd` skill when writing tests.
4. **Ship** with the `pr-final` skill: review, executed evidence, PR.

## Git

- `main` must always be shippable: it runs and can be shown at any moment.
- Never commit to `main`. Work on a short branch named `<name>/<topic>` and merge by squash PR.
- Integrate at least once per work block; a branch older than about 4 hours is a risk.
- The author merges their own PR once CI is green and every **Needs confirmation from** box is
  checked. Never merge a PR with an unchecked box, and never check a box on someone's behalf.
- Ask for confirmation only when it is blocking and significant: the change touches another person's
  lane or anything in `CONTRACTS.md`. A contract change gets its own PR.
- If `main` breaks, fix or revert within 10 minutes and tell the team.

## Code

- Logic lives in `src/dades_huzz/`. Notebooks in `notebooks/` are for exploring; nothing imports
  from them.
- Data stays out of git (`data/` is ignored). Record how to obtain it in `docs/challenge/`.
- Log every modelling attempt as a row in `experiments.md`, including the ones that got worse.
- Validation must imitate how the company will score us. State the validation scheme next to any
  score you report.
- Everything the product outputs is in English: code, comments, commits, PRs, README, slides.

## Skills

Skills live in `.agents/skills/` (the source of truth). `.claude/skills/` and `.github/skills/` are
copies made by `uv run python scripts/sync_skills.py`; edit only the source, then run the script.
