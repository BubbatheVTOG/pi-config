---
name: pi-refresh
description: Update Pi, its installed packages, and reconcile the pi-config repo pins after a Pi release or package bump. Use when the user asks to update pi, refresh extensions, bump package pins, or push config changes. Codifies the pi list / pi update / pin-reconcile / commit / push sequence so it is not re-derived each time.
---

# Pi Refresh

Codified sequence for keeping Pi and the pi-config repo (`~/git/pi-config`) in
sync. Evidence: this workflow was re-derived manually in multiple sessions; the
repo carries recurring "Pin ..." commits. Steps are mechanical except where a
gate is marked (those need user approval before acting).

## 1. Update the harness

```bash
pi list                       # current packages and pinned refs
pi update --extensions        # reconcile package checkouts (does not move pins)
```

## 2. Reconcile pins against the repo

Compare `config/settings.json` package specs in the repo with live
`~/.pi/agent/settings.json` via `pi list` output. Bump a pin only when the
installed revision is older than the repo pin or the user asked for newest.

Gate: `pi install`/`pi remove` and any settings edit are separate actions;
report the exact spec deltas and get approval before changing either file.

## 3. Repo drift check (promotion direction: repo -> live)

For each tracked `config/` and `extensions/` file, compare with the same path
under `~/.pi/agent/`. Promote repo -> live; the repo is the source of truth.

Expected per-machine differences, NOT drift (see pi-config README):

- the GitLab Duo provider package (work machines only, deliberately unpinned)
- `models.json` contents (per-machine providers/credentials)
- `settings.work.json` is a delta, merged manually on work machines only

If live is newer than repo for a file (runtime drift), report it for a
reconciliation decision; never copy live files into the repo blindly.

## 4. Commit and push

Gate: commit (imperative subject, e.g. `Pin pi-subagents 0.78.0`) and push both
need explicit approval. Stay on `main`, preserve unrelated work.

## 5. Activate

Nothing above activates by itself. After live edits, `/reload` in Pi or a fresh
process is a separate approval. Voice/toggle packages stay inert until their
backends exist; reload does not imply they will work.
