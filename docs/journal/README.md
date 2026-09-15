# Engineering journal

Chronological narrative of the project's evolution: what was built, what
test or observation triggered a change, and what was learned. One file per
date (`YYYY-MM-DD.md`), append-only.

This is deliberately NOT any of these (don't duplicate them here):
- **State** (done/blocked/next) → `../../TODO.md`
- **Design reasoning** → `../../live-ai-interpretation-design.md`
- **Evidence/metrics** → `../../validation/latency/`, `../../TEST-RESULT*.md`
- **How the code works now** → `../HOW-IT-WORKS.md`

The journal answers: *why does this feature/tweak exist — what happened
that made us add it?* Link to evidence files rather than restating numbers.

Convention: add an entry the same day a session of work happens, written as
"we implemented X, then Y revealed Z, so we changed it to W." Keep lessons
at the bottom — they're the part that never appears in commit messages.
