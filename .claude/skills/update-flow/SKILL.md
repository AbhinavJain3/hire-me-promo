---
name: update-flow
description: Update flow.md whenever the runtime flow of the HireMe engagement engine changes (data sources, steps, adapters, jobs, mocks, reporting, switch from a mock to a real service). Keeps the "Current flow" steps and mermaid sequence diagram accurate.
---
# Update flow.md

flow.md must always describe what runs **today**, not what is planned.

1. Read flow.md and identify what changed in this session.
2. Edit the numbered steps under "Current flow" so they match the code and configuration as they now are.
3. Update the mermaid sequence diagram under "Current flow" to match the steps (participants, arrows, notes).
4. Planned or not-yet-active behaviour goes only under "Future flow (after backend handoff)". When something from the future flow becomes real, move it into the current flow.
5. Update the "Last updated" line with today's date and a one-line summary of the change, and the "Current stage" line if the stage changed.
6. If the change reflects a design decision, also run the log-decision skill.
