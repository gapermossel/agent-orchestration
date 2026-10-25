# Code samples

Short excerpts copied from our own apps and lightly cleaned up for public
reading. Names, data and config are placeholders. Each file has a header saying
what it does and where it comes from. The Python files need only the standard
library (the test file also needs pytest). The JavaScript file is an ES module
that runs in a browser.

| File | What it does | Why it is interesting |
|---|---|---|
| `ledger_money.py` | Money as whole cents: a `Cents` int type that refuses floats, parsing and formatting of rand amounts, and a `Rate` type with half-up rounding. | Rounding errors in money can't happen by accident, because floats are rejected at the type level. |
| `ledger_vat.py` | VAT rate lookup by date (with the historical 14% to 15% change), exclusive and inclusive VAT maths, and a per-line check. | Old entries keep their old rate. Rounding is limited to one cent, and large claims need a supporting document. |
| `bank_statement_parser.py` | Reads a bank's CSV export with a declared column layout, checks the running balance row by row, and puts newest-first files back in date order. | It is strict: an unknown layout or a balance that doesn't add up stops the import instead of guessing. |
| `test_ledger_money.py` | A pytest suite for the money types: parsing, formatting, rounding at the halfway point, and refusing floats. | Small, readable tests that cover the edge cases that matter in bookkeeping. |
| `append_only_journal.py` | A SQLite journal where triggers block UPDATE and DELETE, and inserts only work through a writer object that the code hands out on purpose. | It is defence in depth: the database enforces the rule, and at start-up the app checks the triggers haven't been changed. |
| `snapshot_redaction.py` | Cleans a data snapshot before it is published: it masks credential-like strings, replaces listed names (matched by hash, not plain text), and checks the output again before writing it. | It fails closed. If anything sensitive survives, the build stops with exit code 2 and writes nothing. |
| `org_chart.mjs` | Draws org-chart connector lines in SVG, measured from the real page layout, and adds mouse/touch pan, pinch zoom and wheel zoom. | No framework or canvas is needed, and the lines stay correct when rows wrap on a phone. |
