# Native-speaker review guide (Q1 — MT sign-off)

What to show the reviewer, and what to ask for. Blocks MT sign-off (TODO).

## Setup

No software needed. Show them the two result tables:

1. `validation/mt/mt_smoke_results.md` — 20 complete conference-style sentences, side by side EN/FR with timings.
2. `validation/mt/mt_smoke_partials_results.md` — 15 deliberately truncated mid-sentence fragments (this is the harder test — simulates what live speech feeds the translator).

Optional, powerful: run `.\live-loop.cmd` live and let them hear the French output (Piper voice) while reading along.

## What to ask — review ALL lines, not just flagged ones

For each row, one of three verdicts:

- ✅ **Fine** — a French speaker would say this naturally.
- ⚠️ **Understandable but off** — grammar/agreement/word-order problems; note what's wrong.
- ❌ **Wrong** — meaning changed, invented content, or nonsense; note the damage.

Specifically watch for (the two known flagged issues, plus classes we haven't caught):

- «une heure précises» — agreement error (flagged in validation).
- «va maintenant ministre» — garbled word order (flagged in validation).
- **Invented content**: anything in the French that isn't in the English (the fragment table's job — the known case was "two million" → invented "of people").
- **Numbers and names**: wrong amounts, mangled names (Adebayo, Okafor, Kano, Jos).
- Register/tone: too casual or too formal for a conference.

## Output we need back

Per table: a count (fine / off / wrong), plus the IDs or quotes of every ⚠️/❌ row with a short note. Then one overall verdict: *usable for a live event / needs work*.

Record the outcome in `TODO.md` (the Blocking item) — not in this guide.
