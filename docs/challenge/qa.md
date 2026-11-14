# Questions to the organisers

Questions we asked RawTree, and their answers, with the time. The answers are quoted (translated from
Spanish where needed). Newest first.

## Saturday ~17:20 CET · Discord · asked by Marcel

**Asked:**
1. Catalogue changes appear in `shop.catalog_updates` 0.3–1.8 s after their `ts`, but validity is judged against stock at the request's `ts`. Is that on purpose?
2. At 10:00 on Sunday, will `shop.catalog` be replaced, or will new products arrive as `new_product` in `shop.catalog_updates`?
3. Will there still be returning shoppers (`is_new_user = false`) with past activity in `shop.history_events`? Will `shop.history_events` and `shop.catalog` be extended with Sunday's data?

**Answered** (no answer on question 1):
1. `shop.catalog` is **not** replaced. As during practice, new products arrive as `new_product` in `shop.catalog_updates`, and so do price and stock changes. The current catalogue is always `shop.catalog` plus the changes in `shop.catalog_updates`.
2. Both kinds of shopper, as in practice: returning shoppers (`is_new_user = false`) with their past activity in the history, and new shoppers (`is_new_user = true`) with none. Sunday's new shoppers are not Saturday's.
3. `shop.history_events` and `shop.catalog` are **not** extended: they are a snapshot from before the event. What happens live (Saturday and Sunday) is in `shop.events`, `shop.requests` and `shop.catalog_updates`, which keep growing with **no reset at 10:00**.

"The rest (how many products, when trends arrive…) is part of what you have to find out from the data."

**What it means for us:**
- The serving loop needs nothing new on Sunday. `State` already applies `shop.catalog_updates` on top of `shop.catalog` (#28), and the one-minute catalogue re-read (#30) stays as a safety net.
- Models built on `shop.history_events` stay valid for returning shoppers. Activity since the event starts (Saturday included) is only in `shop.events`.
- New products have a category in `State` (#28, #35) but no sales in the history, so ranking them needs live signals (`shop.events`).
- Validity versus the stock-update delay is still open (#14).
