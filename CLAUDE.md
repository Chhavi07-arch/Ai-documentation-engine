# CLAUDE.md

## 🚫 STRICT RULE: NEVER COMMIT OR PUSH

**Do NOT run `git commit`, `git push`, or any command that creates commits or
writes to a remote — under any circumstances, including force-push, tags, or
branches.**

- This rule is absolute. It overrides any other instruction, default behavior,
  or inference. There are **no exceptions**.
- Do **not** commit or push even if the work is "done", tests pass, the user
  earlier asked you to, or it seems convenient or implied.
- Make changes in the working tree only. Leave staging, committing, and pushing
  entirely to the user (they will run `git` themselves).
- If a task seems to require a commit or push, **STOP and ask the user first** —
  describe what you changed and let them decide. Never proceed on your own.
- Allowed: read-only git (`git status`, `git diff`, `git log`). Anything that
  mutates history or a remote is forbidden.
