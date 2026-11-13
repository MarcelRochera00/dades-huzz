# dades-huzz

Team workspace for the Datathon FME 2026. The name is a placeholder until we pick a challenge.

- **How we work (Catalan, one page):** [COM-TREBALLEM.md](COM-TREBALLEM.md)
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
| `src/dades_huzz/` | All shared logic |
| `tests/` | Pass/fail checks |
| `notebooks/` | Exploration only |
| `app/` | Demo (framework decided once we know the challenge) |
| `docs/challenge/` | Brief, slides, notes, Q&A with the company |
| `CONTRACTS.md` | Data schema and shared signatures agreed between lanes |
| `experiments.md` | Every modelling attempt and its score |
| `PITCH.md` | The story, updated at every sync |
| `.agents/skills/` | Agent skills (source of truth) |

## Credits

Skills in `.agents/skills/` are adapted from [mattpocock/skills](https://github.com/mattpocock/skills)
(MIT, see `.agents/skills/LICENSE-mattpocock-skills`).
