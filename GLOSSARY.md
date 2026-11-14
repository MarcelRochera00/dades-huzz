# Glossary

## How we work

**Lane**: the part of the solution one person owns for a work block. Changes inside your lane need
nobody's confirmation. The four lanes and their owners (Marcel, Gabriel, Eudald, Miles) are in
`docs/contracts.md`. Catalan: *carril*.

**Lane issue**: the GitHub issue that tracks one lane's slices as a checklist. _Avoid_: epic, ticket.

**Index issue**: the GitHub issue labelled `wayfinder:map` that holds the destination, the decisions so
far and links to every lane issue. _Avoid_: roadmap, board.

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

## The challenge

**Request**: one shopper arriving at the carousel, a record in `shop.requests`. It is what we answer.
_Avoid_: query, event.

**Answer**: our ordered list of 10 product IDs for one request, written to `team_02.submissions`.
_Avoid_: prediction, submission (the table name only).

**Fallback**: what the shopper sees when our answer is missing, late or invalid: the all-time best
sellers in stock. The same list is the **baseline** that scores 0.

**Cold request**: a request from a new shopper (`is_new_user`) or whose recent views include a product
added during the event. Scored separately.

**Model version**: the name of the policy that produced an answer, sent as `model_version`, so feedback
can be compared between versions. _Avoid_: model, run.

**Candidate**: a product considered for an answer before ranking.

**Signal**: a precomputed or live input to ranking (co-views, trends, stock, price). _Avoid_: feature
when it lives outside a trained model.

**Serving loop**: the process that pulls new requests, keeps the state fresh and pushes answers. Only
one runs for the team at a time. _Avoid_: bot, script.

**State**: what the serving loop keeps fresh and passes to `recommend`: current catalogue, stock,
fallback list, trends, signals.

**Final round**: Sunday 10:00-12:00 CET, the only time that is scored. _Avoid_: test, evaluation.
