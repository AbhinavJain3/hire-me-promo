---
name: log-decision
description: Append a new design or architecture decision to decision.md in the HireMe engagement engine repo, using the project's ADR format and the next D- id. Use whenever a design choice is made or changed in a session, even a small one, or when the user says "record this decision".
---
# Log a design decision

1. Read decision.md. Find the highest existing `D-###` id; the new id is that number + 1. Never reuse or renumber ids.
2. Add a row for the new id to the **Index** table near the top: `| D-### | <title> | <area> |`.
3. Append the entry at the end of the file in this format:

```
## D-### <short title>
- **Date:** <today, YYYY-MM-DD> · **Status:** Proposed — pending client review · **Decided by:** <AI (model name) or the person's role>
- **Context:** <why a decision is needed; cite the spec section or constraint>
- **Options considered:** <2-4 options, one line each>
- **Decision:** <what was chosen>
- **Consequences:** <trade-offs, follow-ups, what changes later; link OQ-xx if open>
```

   Always include the Date/Status/Decided-by line on new entries, because the defaults at the top of the file only describe the original 2026-11-02 entries.
4. If the new decision supersedes an older one, change only the older entry's status to `Superseded by D-###` (add a Status line to that entry if it relied on the defaults).
5. If business or backend input is still needed, add an entry to docs/OPEN_QUESTIONS.md that references the new D- id.
6. If the decision changes how the system runs, also run the update-flow skill.
7. Tell the user the new id and title.
