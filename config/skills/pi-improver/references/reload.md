# Reload and restart are separate gates

Pi's interactive `/reload` refreshes keybindings, extensions, skills, prompts,
themes and context. It is not a process restart, package update or promise to reapply
every setting. Read the installed-version contract for the changed resource.

Before activation, validate source and candidate, review all resources that would
load (including unrelated edits), inspect the deployment diff, and obtain separate
deployment approval. Then ask separately whether to reload now, defer, or show
manual instructions. Check all jobs and pending work; unknown status means defer.

This skill adds no reload tool. Prefer the user running `/reload` while idle.
Use an already available documented agent-callable tool only after approval and
its own safety checks. Do not send terminal keys, signals, fabricated RPC actions,
or start a new Pi process to reload the owning session. Installing a bridge would
be a separate plugin proposal, not part of invoking this skill.

Startup-only changes need an approved restart; never kill or replace Pi yourself.
Record requested, completed and verified separately. Confirm discovery and changed
behavior after activation before claiming success. On failure stop retries, report
the sanitized error, and offer a verified generation rollback that preserves later
edits and credentials. Do not restore stale copies over current state.
