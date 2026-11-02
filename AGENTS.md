# Agent Working Agreement

These instructions apply to every agent working in this repository.

## Mandatory approval workflow

Before making any change, the agent must:

1. Explain what it intends to change.
2. Explain what behavior, features, dependencies, data, or systems may be affected.
3. List every file it expects to create, modify, move, or delete.
4. Describe any commands or migrations that may change project state.
5. Wait for the user's explicit approval before performing the proposed work.

The agent must not edit files, run state-changing commands, install or remove dependencies, perform migrations, or make external changes until the user approves the proposal.

## After approval

Once the user approves, the agent may perform only the approved changes. If the scope changes, additional files become necessary, or a new impact is discovered, the agent must stop, explain the revised scope and impact, list the additional affected files, and request approval again.

Read-only inspection and diagnostic commands are allowed before approval when needed to prepare an accurate proposal. They must not modify project files, dependencies, data, external services, or system state.

After completing approved work, the agent must report:

- What was changed.
- Which files were changed.
- What validation or tests were run and their results.
- Any remaining risks, limitations, or follow-up work.

User approval must be explicit. Silence, lack of response, or a general request to continue does not approve changes whose scope and affected files have not been described.
