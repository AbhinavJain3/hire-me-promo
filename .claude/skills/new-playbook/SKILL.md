---
name: new-playbook
description: Scaffold a new HireMe playbook from a spec use-case id (A1-H5) - playbook JSON, English and Hindi templates, simulator scenario and test - then validate it. Use when the user says "add playbook X" or wants to change an existing playbook's definition.
---
# Add a playbook

1. Delegate the drafting to the playbook-author agent, passing the use-case id and any overrides from the user.
2. When it returns, run the validate-contract skill.
3. Run the run-scenario skill for the new scenario.
4. Log any non-default choice with the log-decision skill, and add business questions to docs/OPEN_QUESTIONS.md.
5. Summarise for the user: what the playbook does, trigger, audience, offer ladder, channels, message class, and test results.
