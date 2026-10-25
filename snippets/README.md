# Code samples

Short excerpts copied from our own apps and lightly cleaned up for public
reading. Names, data and config are placeholders. Each file has a header saying
what it does and where it comes from. There is one folder per app. The Python
files need only the standard library (the test file also needs pytest). The
`.mjs` files are ES modules: the timetable ones run with Node 18+, and the org
chart runs in a browser. Files that end in a demo can be run directly, for
example `python3 herd_sync.py` or `node timetable_conflicts.mjs`.

## ledger/ — desktop bookkeeping app (Python + SQLite)

| File | What it does | Why it is interesting |
|---|---|---|
| `ledger_money.py` | Money as whole cents: a `Cents` int type that refuses floats, parsing and formatting of rand amounts, and a `Rate` type with half-up rounding. | Rounding errors in money can't happen by accident, because floats are rejected at the type level. |
| `ledger_vat.py` | VAT rate lookup by date (with the historical 14% to 15% change), exclusive and inclusive VAT maths, and a per-line check. | Old entries keep their old rate. Rounding is limited to one cent, and large claims need a supporting document. |
| `bank_statement_parser.py` | Reads a bank's CSV export with a declared column layout, checks the running balance row by row, and puts newest-first files back in date order. | It is strict: an unknown layout or a balance that doesn't add up stops the import instead of guessing. |
| `test_ledger_money.py` | A pytest suite for the money types: parsing, formatting, rounding at the halfway point, and refusing floats. | Small, readable tests that cover the edge cases that matter in bookkeeping. |
| `append_only_journal.py` | A SQLite journal where triggers block UPDATE and DELETE, and inserts only work through a writer object that the code hands out on purpose. | It is defence in depth: the database enforces the rule, and at start-up the app checks the triggers haven't been changed. |

## hq-dashboard/ — internal operations dashboard (Python build step + vanilla JS)

| File | What it does | Why it is interesting |
|---|---|---|
| `snapshot_redaction.py` | Cleans a data snapshot before it is published: it masks credential-like strings, replaces listed names (matched by hash, not plain text), and checks the output again before writing it. | It fails closed. If anything sensitive survives, the build stops with exit code 2 and writes nothing. |
| `org_chart.mjs` | Draws org-chart connector lines in SVG, measured from the real page layout, and adds mouse/touch pan, pinch zoom and wheel zoom. | No framework or canvas is needed, and the lines stay correct when rows wrap on a phone. |

## plaasboek/ — offline livestock record book (Python + Flet + SQLite, English/Afrikaans)

| File | What it does | Why it is interesting |
|---|---|---|
| `livestock_db.py` | The SQLite schema (farms, camps, animals, health and movement events) and the connection setup. | The database enforces the rules too (CHECK and UNIQUE constraints, WAL mode), and every row carries the timestamp and device id the sync step needs. |
| `livestock_validation.py` | Validates form input: money as 2-decimal strings, the date formats people actually type, species/sex/status choices, and which status changes are allowed. | Each error names its form field, so the UI can show the message in the right place. Sold and dead animals can't quietly come back. |
| `herd_sync.py` | Syncs a phone and a computer with no server: one side exports a checksummed zip, and the other merges it in. | A changed file is refused. An animal edited on both sides becomes a conflict for the farmer to resolve instead of being overwritten. |

## aether-timetable/ — offline timetable generator (React + Electron, English/Afrikaans)

| File | What it does | Why it is interesting |
|---|---|---|
| `timetable_scheduler.mjs` | Builds a weekly timetable with a greedy placement pass, then improves it with simulated annealing. | Hard rules (breaks, teacher clashes, unavailability) are never broken. Soft goals such as double periods are scored, and a seeded RNG makes results repeatable. |
| `timetable_conflicts.mjs` | Re-checks any timetable for unplaced periods, teacher clashes, unavailability and empty slots, and includes a runnable demo. | It trusts nothing, so hand edits and CSV imports get the same checks as generated timetables. |
| `timetable_csv.mjs` | Exports and imports the timetable as CSV that survives a round trip through Excel (BOM, `sep=` hint, proper quoting), with a self-test. | It handles the small details that usually break CSV files in real offices. |
