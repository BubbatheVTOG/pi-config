---
name: plan
description: Plan non-trivial work before executing it. Clarifies the goal, defines observable success criteria, designs the environment so the correct path is the easiest one (pit of success), runs a pre-mortem over failure modes with mitigations and rollbacks, and sequences the work into small verifiable checkpoints that become pi-tasks with dependencies and blockers. Use for multi-file changes, unclear requirements, risky or irreversible operations, or any multi-step implementation. Asks follow-up questions with ask_user_question.
---

# Plan

Produce a plan that can actually be executed successfully. The plan is a
**risk-reduction document**, not a restatement of the request.

Pi has no built-in plan mode by design, so the plan lives in a file
(`PLAN.md` at the project root, or `~/.pi/agent/plans/<name>.md` when the work
is not project-local). That file is the source of truth: it survives compaction,
it is what you check boxes in as you go, and it is what the user reviews.

## Ground rules

- **Read before planning.** Use `scout` for codebase recon you don't already
  have, and `researcher` for external facts. A plan built on guesses is a plan
  to redo the work.
- **Planning is read-only. The user says when to go.** No source edits, no new
  project files, no deletes, no installs, no migrations, no pushes, and no git
  state changes (branch, commit, stash) — all of that waits for an explicit go.
  The only write planning may make is the plan file itself, and only when the
  user wants it on disk; otherwise present the plan in chat. When in doubt, the
  answer is: don't write it, ask.
- **Stop and ask when a blocker is a decision, not a fact.** Missing information
  that only the user has is a question, not an assumption to paper over.
- **Plans are cheap; execution is expensive.** Prefer one extra clarifying round
  over one wrong implementation.

## Workflow

### 1. Clarify the goal

Establish: what changes, for whom, why now, and what is explicitly out of scope.
Separate what the user said from what you inferred, and label the inference.

Ask the questions that change the plan's shape — scope, approach, constraints,
definition of done. Do not ask questions you can answer by reading the code.

### 2. Define what success looks like

Success must be **observable and checkable**, not aspirational. For each
criterion, name the command, test, or artifact that proves it.

- Behavior: what is different after the change that wasn't before?
- Verification: the exact command(s) that go green (`just test`, `npm test`,
  `mvn verify`, a curl, a screenshot).
- Non-goals and anti-goals: what must *not* happen (no perf regression, no
  schema migration, no new dependency, no changed public API).
- Exit signal: how do we know we're done rather than merely finished?

If success can't be observed, the first step of the plan is to make it
observable — add the test, the probe, or the metric before making the change.

### 3. Engineer the pit of success

This is the core of the skill: make the correct path the easiest path, so the
agent (and the next human) succeeds by default rather than by vigilance.

Ask, for each: *"what would make the wrong thing hard or impossible here?"*

- **Make it fail loudly.** Types, schema validation, assertions, lint rules,
  compiler flags (`-Werror`, `failOnWarning`) — push detection to the earliest
  possible moment instead of relying on review.
- **Make the right thing the default.** Safe defaults, scaffolding/generators
  that emit the correct pattern, wrappers that handle the sharp edge so callers
  can't forget it.
- **Shorten the feedback loop.** A test or probe that runs in seconds and
  answers "did this work?" — before the slow full suite, not instead of it.
- **Capture the baseline first.** Run the existing checks *before* touching
  anything so you know what green looks like on this machine.
- **Remove the need for care.** Idempotent scripts (`stow -R`, `spotless:apply`,
  `mix precommit`), pre-commit hooks, dry-run flags, `--check` modes.
- **Make reversibility cheap.** Branch, git checkpoint, stash, backup, feature
  flag, env toggle. Prefer additive changes; delete in a later commit.
- **Make the order forgiving.** Sequence steps so each is verifiable on its own
  and a failure is caught at the step that caused it.

### 4. Pre-mortem: how this fails

Assume the plan has already failed. Write down *how*. For every failure mode:
the **mitigation** (how we prevent or contain it), the **early-warning signal**
(what we'd see first), and the **rollback** (how we get back).

Cover at least these categories, and drop the ones that don't apply:

- **Ambiguous or wrong requirements** — building the right thing badly vs. the
  wrong thing well. Mitigate by asking, and by building a visible slice early.
- **Unknown unknowns** — the codebase has a non-obvious constraint (load-bearing
  config, virtual threads, a rate limiter that fails open *by design*).
  Mitigate with recon and a spike before committing to an approach.
- **Scope creep** — the plan grows mid-flight. Mitigate by writing non-goals
  down and re-planning explicitly rather than drifting.
- **Irreversible actions** — dropped tables, force-push, deleted files, published
  packages, changed public API or signature formats. Mitigate by not doing them
  in the first pass; make them a separate, explicitly approved step.
- **Environment and dependency drift** — wrong JDK/Node, unsourced env file,
  missing credentials, a tool that exists on one host only. Mitigate by
  verifying the toolchain before step one.
- **Flaky or absent verification** — no test covers the change, or the test
  depends on network/time/order. Mitigate by adding a deterministic test first.
- **Silent breakage** — the change works but breaks a downstream consumer or a
  contract (header format, event shape, migration path). Mitigate by grepping
  for consumers and naming them in the plan.
- **Security and secrets** — keys in diffs, secrets in logs, new exposure.
  Mitigate by keeping credential files out of the change and checking the diff.
- **Performance and cost** — hot-path allocations, N+1 queries, an expensive
  model used for a trivial subtask. Mitigate by naming the budget up front.

### 5. Sequence into verifiable steps

Break the work into steps small enough that a failure points at its own cause.
For each step: **what** changes, **how to verify** it, and **what to do if
verification fails**. Order them so the riskiest unknown is probed earliest.

Mark the checkpoints where you will stop and report rather than continue.

### 6. Set the environment up for success

Before step one — which is to say, *after* the go: branch or checkpoint, confirm
the toolchain, capture the green baseline, decide the rollback, then create the
tasks (step 7).

For genuinely uncertain plans, run `oracle` over the finished plan for a second
opinion before executing — it is cheaper than one wrong implementation.

### 7. Create the tasks

Never rely on memory or the transcript: long sessions compact, and a forgotten
step is a silently unfinished plan. Record the work with pi-tasks.

- **One task per verifiable step.** `subject` imperative and short; `description`
  carries the acceptance criteria, the verification command, and the rollback.
  Set `activeForm` for the spinner ("Adding the migration", not "add migration").
- **Dependencies, not just order.** Add `addBlockedBy` for edges that are real —
  B cannot start until A produces something B consumes (a schema, a file, a
  decision, a passing baseline). Do not chain tasks that are merely sequential;
  false serialization kills parallelism and hides the actual critical path.
- **Name the blockers.** A step blocked by something outside the work (a user
  decision, a credential, an upstream merge, a deploy, a hardware box being up)
  is still a task. Create it, put `BLOCKED: waiting on <thing>` in the
  description, and wire `addBlockedBy` to whatever unblocks it. Then create the
  unblocking task too ("Decide X", "Get Y credential") so the blocker has an
  owner and a checkbox instead of living in someone's head.
- **Call out what can run in parallel.** Tasks with no unmet dependencies can go
  at once — say so in the plan, and consider handing independent ones to `worker`
  children so they happen concurrently.
- **Name the critical path.** The longest dependency chain is where delay
  actually costs; everything else has slack. Say which chain it is.
- **When to create them:** after the user says go — or immediately if the user
  asks for them during planning. Skip task creation only for genuinely trivial
  plans.
- **Drive them yourself.** Mark `in_progress` before starting a task and
  `completed` only when its verification passes. `TaskExecute` and auto-cascade
  are inert here (they expect `@tintinweb/pi-subagents`), so check `TaskList`,
  pick the next unblocked task, and never start one that is still blocked.

## The go / no-go gate

When the plan is complete, **stop**. Do not begin step 1, do not "just scaffold
it quickly," do not create the branch "while we're here."

If you believe the plan is ready to execute, say so in one clear statement and
then wait:

> Plan is complete and I'm ready to execute — say go and I'll start at step 1.
> If you'd rather change the approach, scope, or verification first, tell me and
> I'll re-plan that part.

Rules for the gate:

- **One statement, then wait.** State readiness once. Do not re-ask, do not
  nudge, do not start the work "provisionally" while waiting.
- **Enthusiasm is not authorization.** "That looks right", "nice", or an answer
  to some *other* question is not a go. Wait for the go.
- **A conditional go is a re-plan.** "Go, but use Redis instead" means update the
  affected steps, the pre-mortem, and the task graph before touching anything.
- **On go:** create the branch/checkpoint, capture the baseline, create the
  tasks, then work the steps in order and check them off as each verification
  passes.
- **Resuming later:** if the session ends mid-execution, `PLAN.md` plus the task
  list is the handoff. Re-read both before continuing; do not work from memory.

## Asking follow-up questions

Use `ask_user_question` (from pi-ask) at every real decision point: after
recon and before committing to an approach, and again when the draft plan has
tradeoffs the user should own.

Rules:

- 1–4 questions per call, each with 2–4 options. Every option needs a `value`
  (stable key) and a `label` (shown to the user).
- Mark the option you'd recommend with `recommended: true` — it moves to the top
  with a hint, but is never pre-selected.
- Use `multiSelect: true` only when combinations are meaningful (traversal
  tradeoffs, which checks to run, which risks to accept).
- Use `showWhen: { questionId, equals }` for one level of conditional follow-up
  (e.g. only ask about migrations after "yes, schema changes").
- Keep `header` ≤ 12 characters. Never add an "Other" option — it is automatic.
- `required: false` lets the user explicitly skip a question; otherwise submit
  is blocked until visible required questions are answered.
- Ask about **decisions**, not facts you can look up. Batch them — one dialog
  with a conditional chain beats three interruptions.

Good moments to ask:

- Scope: minimal fix vs. proper fix vs. refactor-and-fix
- Approach: the 2–3 real options you found, with the tradeoff in the label
- Verification: which checks gate "done", whether to add new tests
- Reversibility: branch/flag/migration strategy, whether to keep a fallback
- Risk acceptance: which of the pre-mortem risks the user is willing to take

## Output: the plan file

Write the plan to `PLAN.md` only if the user wants it on disk — otherwise present
it in chat. Either way the shape is:

```markdown
# Plan: <goal>

## Goal
What changes and why. Separate stated requirements from inferred ones.

## Success criteria          <- observable, with the command that proves each
- [ ] <criterion> — verified by `<command>`

## Non-goals
What this deliberately does not do.

## Pit of success            <- what we set up so the right path is the easy one
- <guardrail / default / automation / feedback loop>

## Pre-mortem                <- failure mode -> mitigation -> early signal -> rollback
| Failure mode | Mitigation | Early warning | Rollback |
|---|---|---|---|

## Steps
1. <change> — verify: `<command>` — if it fails: <what to do>
2. ...

## Environment setup
Branch/checkpoint, toolchain, baseline command, rollback command.

## Task graph
```

# 1 (no deps) ─┐
# 2 (no deps) ─┴→ #3 → #5      critical path: #2 → #3 → #5
# 4 BLOCKED: waiting on <decision / credential / upstream> — unblocked by #6
# 6 Unblock: <the unblocking task>

```
Parallel: #1 and #2 can start together.

## Open questions
Anything still unresolved, with who answers it.
```

Keep it tight — a plan nobody reads is a plan that doesn't reduce risk. Update
the checkboxes as you execute, and re-plan explicitly if reality diverges
instead of drifting silently.

## Anti-patterns

- Writing to the repo while still planning, or treating "looks good" as a go.
- Restating the request as steps without defining success or failure modes.
- Assuming instead of asking, then discovering the mismatch at the end.
- Planning only the happy path — no rollback, no baseline, no early warning.
- Making the first step irreversible.
- A plan so long it can't be reviewed; prefer a probe now, full plan after.
- Treating the plan as fixed: if step 2 invalidates step 3, stop and re-plan.
