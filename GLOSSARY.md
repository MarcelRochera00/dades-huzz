# Glossary

**Lane**: the part of the solution one person owns for a work block. Changes inside your lane need
nobody's confirmation. Catalan: *carril*.

**Contract**: something two or more lanes depend on, written in `docs/contracts.md`: a data schema, a
shared function signature, the submission format. Changing it needs confirmation from the lanes that
use it.

**Confirmation**: an explicit yes from a named person on a specific question, recorded as a checked
box in a PR. Asked for only when blocking and significant. _Avoid_: approval, review.

**Sync**: the ten-minute team check-in held around meals. Catalan: *sincronització*.
_Avoid_: stand-up, meeting.

**Shippable**: the state `main` must always be in: it runs from scratch and can be shown to a judge
right now. _Avoid_: deployed, production-ready.

**Trial submission**: a real submission made early through the official channel, to prove we know how
to deliver.

**Integrator**: the person who watches that `main` stays shippable and sweeps open PRs at each sync.
