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

**Escaped request**: a request whose feedback is not `served_by = team`, so the shopper saw the fallback. Its
reason is `missing`, `late` or `invalid`. _Avoid_: lost, dropped, failed request.

**Unavailable product**: a product that would make an answer invalid: inactive, or whose latest stock change is
`out_of_stock`.

**Handover**: how the serving loop moves between laptops: every loop sends a heartbeat, one is *active*
(answers) and the others are *standby* (wait), and a standby takes over when the active one goes silent.
_Avoid_: failover, leader election.

**Tati**: our recommender as a product. Each model version that beats the live champion takes the next
rank: Tati (`tati-0-bestsellers`, the baseline), Tati Destroyer, Tati Terminator, Tati Ultimatum, Tati
Apocalypse, Tati Armageddon, Tati Omega; the model version is `tati-<rank>-<idea>`, e.g.
`tati-destroyer-category`. A challenger carries the rank it is aiming for from the start; it holds that
rank only once it beats the champion live. Tati versions rank products by rules. _Avoid_: the bot, the
model.

**Lauri**: our second recommender family, for versions that learn the chance of a purchase from the old
carousel log instead of following rules. Its ranks, in order: Lauri Titan, Lauri Colossus, Lauri
Singularity; the model version is `lauri-<rank>-<idea>`, and ranks are won as for Tati.

**Returning shopper**: a shopper who is not new (`is_new_user` false) and so has past activity in the
store's history. _Avoid_: old user, known user.

**Shopper profile**: a returning shopper's share of their past activity in each category (purchases count
more than add-to-carts, which count more than views). _Avoid_: user embedding, user vector.

**Champion**: the model version the team currently serves as its best, the one a challenger must beat
live to take the next rank. _Avoid_: production model.

## Offline evaluation

**Cut**: the instant that splits the history: signals use only what happened before it, and evaluation
uses the carousel impressions after it. _Avoid_: split date, test date.

**Propensity**: the probability the old carousel had of showing a product in a slot, logged next to
each impression. _Avoid_: score, probability.

**Slate IPS**: the primary offline metric: carousel purchases per request a policy would get, counting
only the slots where it matches the old carousel, each purchase weighted by 1 / propensity with a cap.
_Avoid_: IPS (alone), offline conversion.

**Weighted hit**: a secondary replay metric: whether the product bought from the old carousel is in our
answer, worth more the higher it sits. Biased towards policies that resemble the old carousel.
_Avoid_: hit rate, accuracy.

**Organic purchase**: a purchase in `shop.history_events` / `shop.events`, made outside the carousel.
Not used to score policies: it rarely follows a request closely. _Avoid_: conversion.
