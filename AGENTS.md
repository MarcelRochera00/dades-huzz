# Agent rules

Four people work in this repo at the same time, each with their own coding agent, for the Datathon FME
2026 (challenge revealed Saturday 10:00, submission Sunday 12:00). These rules keep us from breaking
each other's work. The human-facing version is `docs/COM-TREBALLEM.md`.

## Commands

- Install: `uv sync`
- Tests: `uv run pytest`
- Lint: `uv run ruff check` (fix with `uv run ruff check --fix`, format with `uv run ruff format`)
- Add a dependency: `uv add <package>`; never edit `uv.lock` by hand

## Before planning any task

Read `docs/challenge/` (what the company asked for), `docs/contracts.md` (what the lanes agreed) and
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
  lane or anything in `docs/contracts.md`. A contract change gets its own PR.
- If `main` breaks, fix or revert within 10 minutes and tell the team.
- Before you start a branch and again before you open a PR, run `git fetch` and `gh pr list`. Do not
  edit a file someone else has in an open PR; ask them first. Exception: lanes B and C share
  `model.py` and `features.py` by design; each edits only its own functions and rebases before merging.

## Issues and progress

Each lane has one issue on GitHub (label `area:live`, `area:model`, `area:learning` or
`area:decisions`), linked from the index issue (label `wayfinder:map`). Lanes and owners are in
`docs/contracts.md`.

- Work on your lane issue and tick its checklist as slices reach `main`.
- When you find a problem or an idea outside the current task, do not fix it in this branch. Open an
  issue with `gh issue create`: give it its area label, assign the owner or owners from
  `docs/contracts.md`, and link it from the index issue in a comment.
- A finding that changes what another lane should do (a data quirk, a latency limit, a segment that
  converts) goes as a comment on the index issue as well as in the chat.
- At each sync, the owner posts a status comment on their lane issue: done, next, blocked.

## Where things go

Judges and teammates read this repo cold. Every file has one home; before creating a file, find its
row here. If nothing fits, ask the user instead of inventing a place.

| What | Where | Naming |
|---|---|---|
| Loading and cleaning data | `src/dades_huzz/data.py` | |
| Feature building | `src/dades_huzz/features.py` | |
| Training and prediction | `src/dades_huzz/model.py` | |
| Live serving loop: pull requests, keep the state fresh, push answers | `src/dades_huzz/serving.py` | |
| Metric, validation, submission check | `src/dades_huzz/evaluation.py` | |
| Tests | `tests/test_<module>.py` | mirrors the module it tests |
| Commands a person runs (train, predict, submit) | `scripts/<verb>_<thing>.py` | thin: parse args, call `src/` |
| Demo app | `app/` | one entry point, named in the README |
| Exploration | `notebooks/<name>-<topic>.ipynb` | your name first |
| The company's material | `docs/challenge/` | |
| Team agreements | `docs/contracts.md`, `docs/experiments.md`, `docs/pitch.md` | |
| Figures and slides we present | `docs/assets/` | |
| Raw and processed data | `data/raw/`, `data/processed/` | never committed |
| Models, predictions, submissions, logs | `outputs/` | never committed |
| Throwaway files, prototypes, drafts | `scratch/` | never committed |

- A module in `src/dades_huzz/` becomes a folder only when it passes about 300 lines; then split it
  by what it does, never into `utils.py`, `helpers.py` or `misc.py`.
- Search before you create: extend the existing module instead of adding a second one that does a
  similar job (`model2.py`, `new_features.py`, `final_v3.py` are never the answer).
- No new files or folders at the repo root. `tests/test_structure.py` fails if one appears; adding
  to its allow-list is a contract change.
- Create a folder with its first real file, not before.
- Delete what a change makes dead, in the same PR.

## Code

- Logic lives in `src/dades_huzz/`. Notebooks in `notebooks/` are for exploring; nothing imports
  from them.
- Data stays out of git (`data/` is ignored). Record how to obtain it in `docs/challenge/`.
- Log every modelling attempt as a row in `docs/experiments.md`, including the ones that got worse.
- Validation must imitate how the company will score us. State the validation scheme next to any
  score you report.
- Everything the product outputs is in English: code, comments, commits, PRs, README, slides. The only
  exceptions are `docs/COM-TREBALLEM.md` (Catalan, for the team) and the spoken demo, whose language
  the team picks for the jury.
- Secrets (`RAWTREE_API_KEY`) live only in the git-ignored `.env`; `.env.example` lists the names.
  Never print the key in logs, PRs or issues.

## Skills

A skill is a folder with a `SKILL.md` you must read in full and follow. When the user names a skill
(with or without a slash, in any language: "grill-with-docs", "/pr-final", "fes un prototype"), or a
step above calls for one, and your tool does not load it by itself, open the file and follow it
exactly. Never improvise a skill from its name, and never say it does not exist without looking here:

| Skill | File | Use it when |
|---|---|---|
| `grill-with-docs` | `.agents/skills/grill-with-docs/SKILL.md` | Before any task bigger than a small fix |
| `grilling` | `.agents/skills/grilling/SKILL.md` | Called by `grill-with-docs` |
| `domain-modeling` | `.agents/skills/domain-modeling/SKILL.md` | Called by `grill-with-docs` |
| `prototype` | `.agents/skills/prototype/SKILL.md` | A question must be seen to be answered |
| `tdd` | `.agents/skills/tdd/SKILL.md` | Writing tests or building test-first |
| `codebase-design` | `.agents/skills/codebase-design/SKILL.md` | Deciding the shape of a shared interface |
| `branch-review` | `.agents/skills/branch-review/SKILL.md` | Reviewing a branch; called by `pr-final` |
| `spec-review` | `.agents/skills/spec-review/SKILL.md` | Called by `branch-review` |
| `pr` | `.agents/skills/pr/SKILL.md` | Called by `pr-final` to write the PR body |
| `pr-final` | `.agents/skills/pr-final/SKILL.md` | The work is done and needs a PR |

How each tool calls a skill: Claude Code and Cursor `/<skill>`, Codex `$<skill>` (or `/skills`). Any
other tool: read the file from the table.

If a skill tells you to start sub-agents and your tool cannot, do the same steps yourself, one after
another, and keep each step's findings separate. If it names a command your tool lacks (such as
`/code-review`), use the manual fallback the skill gives.

Skills live in `.agents/skills/` (the source of truth). `.claude/skills/` and `.github/skills/` are
copies made by `uv run python scripts/sync_skills.py`; edit only the source, then run the script.
