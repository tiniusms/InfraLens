# InfraLens AI Onboarding Pack

Copy these files into the root of the InfraLens GitHub repository. The goal is to make ChatGPT, Cursor, Claude, and other assistants operate from the same project language without re-explaining scope in every conversation.

`PROJECT_CONTEXT.md` is the stable product/research brief. `AGENTS.md` contains shared rules. `CLAUDE.md` and `.cursor/rules/infralens.mdc` are thin platform adapters that point back to the shared context. `DECISIONS.md` is the change log. `TASKS.md` is the current work queue.

GitHub remains the source of truth; AI chat history does not.
