---
description: Merge develop into origin/main and prepare for lab PC deployment. Run after /complete-task has merged the working branch into develop.
allowed-tools: Bash
---

You are executing a production deployment merge. Follow every step in order. Stop and report to the user at any failure point — do not attempt to recover automatically.

## Step 1 — Pre-flight checks

Run these three checks in sequence. Stop if any fails.

```bash
git branch --show-current
```
If the result is not `develop`, run `git checkout develop` and confirm before continuing.

```bash
git status
```
If the output is not "nothing to commit, working tree clean", stop and tell the user what is dirty. Ask whether to stash or commit before continuing.

```bash
git fetch origin
git rev-list --count origin/develop..develop
```
If the result is not `0`, run `git push origin develop` before continuing.

## Step 2 — Check for divergence between develop and origin/main

```bash
git fetch origin main
git rev-list --left-right --count develop...origin/main
```

The output is two numbers: `<ahead> <behind>`.

- `N 0` — normal, continue to Step 3
- `0 0` — branches are identical, tell the user "Nothing to deploy — develop and main are already in sync" and stop
- `0 N` — main is ahead of develop, which violates the workflow rules. Stop. Report the divergence and wait for explicit user instruction before touching anything
- `N M` (both non-zero) — branches have diverged. Stop. Run `git merge-base develop origin/main` and report the divergence point and affected commits to the user. Wait for explicit instruction

## Step 3 — Merge develop into main

```bash
git checkout main
git pull origin main
git merge develop --no-edit
```

If `git merge` exits with a conflict:

1. Run `git merge --abort` immediately
2. Report which files have conflicts: `git diff --name-only --diff-filter=U`
3. Report what each side introduced: `git log --oneline develop ^main` and `git log --oneline main ^develop`
4. Ask the user: "There are merge conflicts in the files listed above. Would you like me to walk through each conflict, or will you resolve them manually?"
5. Wait for explicit instruction before taking any further git action

## Step 4 — Push to origin/main

```bash
git push origin main
```

If the push is rejected:

1. Do NOT run `git push --force` or `git push --force-with-lease` under any circumstances
2. Run `git fetch origin main && git log --oneline HEAD..origin/main` to show the user what is on the remote that is not local
3. Report: "Push was rejected — origin/main has commits not present locally. Force-pushing main is prohibited. Here is what is on the remote:" followed by the log output
4. Wait for explicit user instruction

## Step 5 — Return to develop and confirm

```bash
git checkout develop
git log --oneline -5
```

Report the last 5 commits so the user can confirm the expected work is included.

## Step 6 — Deployment reminder

Tell the user:

> **origin/main is updated.**
>
> To deploy to the lab PC, right-click `update.ps1` and choose **Run with PowerShell**.
>
> To verify the update completed:
> ```powershell
> Get-Content "C:\Logs\experiment-tracker\updates.log" -Tail 20
> ```
>
> If the service does not restart automatically: `nssm restart ExperimentTracker`
