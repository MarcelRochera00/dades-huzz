---
name: branch-review
description: "Review a branch or PR along three axes: bugs, standards and spec. Use when asked to review code."
---

Three-axis review of the diff between `HEAD` and a fixed point.

1. **Fixed point.** The one given in the arguments; if it is a PR, its base branch; if none is given, `main`. Done when `git diff <fixed-point>...HEAD` returns a non-empty diff.
2. **Standards and Spec.** Follow the `spec-review` skill with that fixed point. If your agent can start sub-agents, run each axis in one with a fresh context; otherwise run the two axes one after the other.
3. **Bugs.** Hunt for correctness bugs in the same diff. If your agent has a built-in code review command (in Claude Code, `/code-review high`), use it. Otherwise read every changed hunk with its surrounding code and report only defects you can describe as concrete input -> wrong output or crash.
4. **Report.** Three sections, `## Bugs`, `## Standards` and `## Spec`, each as its step returned it, without merging or reordering findings across axes. Close with one line per axis: number of findings and the worst one.
