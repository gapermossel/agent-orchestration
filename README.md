# Multi-Agent Orchestration (Grok Bots)

Hierarchical multi-agent system with a central orchestrator (Chief of Staff) and specialised desks.

## Team structure
![Grok Bots team structure](hierarchy.png)

## Architecture
- **COS (Orchestrator)** — mission board, daily sitrep, and coordination of specialised desks.
- **Specialised desks**: Security Ops, Tech (host/network health), Archivist (knowledge vault), Intel (research briefs), Clerk (operational document capture).

## Key mechanisms
- Reusable skills
- Scheduled routines
- Explicit approval gates (“AWAITING APPROVAL”)
- Structured status reporting with file paths
- Clear boundaries per agent

## Evidence
- Case study (architecture diagram + worked example): [Grok_Bots_Case_Study.pdf](Grok_Bots_Case_Study.pdf)
- Daily host & network health sweep with drift detection and approval gate

## Code samples
Short, self-contained excerpts from our apps: [snippets/](snippets/)
- **Ledger**: money types, VAT logic, bank statement import, append-only journal, tests
- **HQ Dashboard**: fail-closed redaction, org chart rendering
- **Plaasboek**: livestock database, validation, offline herd sync
- **Aether Timetable**: timetable scheduler, clash detection, CSV import

Contact: lightfootwilrich@gmail.com
