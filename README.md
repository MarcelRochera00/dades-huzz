# dades-huzz

Team workspace for the Datathon FME 2026. The name is a placeholder until we pick a challenge.

- **How we work (Catalan, one page):** [docs/COM-TREBALLEM.md](docs/COM-TREBALLEM.md)
- **Rules for coding agents:** [AGENTS.md](AGENTS.md)
- **The challenge:** [docs/challenge/](docs/challenge/)

## Setup

```
./scripts/setup.ps1      # Windows
sh scripts/setup.sh      # macOS / Linux
```

Requires [git](https://git-scm.com), [uv](https://docs.astral.sh/uv/) and the
[GitHub CLI](https://cli.github.com).

## Layout

| Path | What |
|---|---|
| `src/dades_huzz/` | All shared logic: data, features, model, evaluation |
| `tests/` | Pass/fail checks, one file per module |
| `scripts/` | Commands you run: setup, train, predict, submit |
| `app/` | Demo (framework decided once we know the challenge) |
| `notebooks/` | Exploration only; nothing imports from here |
| `docs/challenge/` | Brief, slides, notes, Q&A with the company |
| `docs/contracts.md` | Data schema and shared signatures agreed between lanes |
| `docs/experiments.md` | Every modelling attempt and its score |
| `docs/pitch.md` | The story, updated at every sync |
| `.agents/skills/` | Agent skills (source of truth; `.claude/` and `.github/` hold copies) |

`data/`, `outputs/` and `scratch/` are local only. The full map, with naming rules, is in
[AGENTS.md](AGENTS.md#where-things-go).

## Credits

Skills in `.agents/skills/` are adapted from [mattpocock/skills](https://github.com/mattpocock/skills)
(MIT, see `.agents/skills/LICENSE-mattpocock-skills`).
