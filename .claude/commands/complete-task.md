# /complete-task

Use after finishing each sub-task or milestone phase.

Steps:
1. Run all relevant tests (`pytest` or `vitest`)
2. Run linters (`flake8`/`black` or `eslint`)
3. Confirm pre-merge checklist from `docs/GIT_WORKFLOW.md` is satisfied
4. Update `docs/working/plan.md`:
   - Mark the completed task
   - Log any decisions made
   - Note what was tested and how
   - Record what comes next
5. Commit with the format from `docs/GIT_WORKFLOW.md`
6. Report completion summary to user and wait for sign-off before advancing
