# Memory Layers — What Goes Where

See `docs/architecture/memory-system.md` for the full architecture. This
page is a practical reference for what belongs in each layer.

## Working Memory

**What**: the current task's in-flight state — an active plan, a
decision made mid-task, a recent tool observation you'll need again in
the next step.

**Lifetime**: in-process only, never written to disk, cleared when the
task ends (or explicitly via `MemoryService.clear_working(scope)`).

**Good examples**:
- `"Chose to use SQLite over Postgres for this task's storage decision"`
- `"User confirmed: yes, delete the old branch"`
- A running list of files touched so far in a multi-step refactor

**Bad examples** (should be Episodic/Semantic instead if worth keeping):
- Anything you want to survive past this one task
- Full tool output dumps "just in case"

## Preferences (User Memory)

**What**: durable facts about the user — the same categories as before
Phase 5: `identity`, `preferences`, `projects`, `relationships`, `wishes`,
`notes`.

**Lifetime**: persistent (JSON file), until explicitly forgotten.

**Good examples**:
- `identity/name = "Vikram"`
- `preferences/food = "pizza"`
- `relationships/sister = "Priya"`

**Bad examples**:
- API keys, passwords, tokens — `MemoryService.remember()` actively
  refuses these; `save_memory`/`PreferenceMemory.set()` should never be
  handed one in the first place
- One-off session details ("user is currently on a phone call") — that's
  Working Memory, not a durable preference

## Episodic Memory

**What**: meaningful events — task completions/failures, significant
decisions, explicit "remember this" moments. NOT a transcript.

**Lifetime**: persistent (SQLite), optionally with a retention window
(`memory_episodic_retention_days` config, default 180 days — set `None`
for no automatic expiry; nothing currently runs the expiry sweep
automatically, call `MemoryService.purge_expired()` where appropriate).

**Good examples**:
- `"Task completed: fixed the build error in auth.py"` (Orchestrator,
  automatically, on every task completion/failure)
- `"User explicitly rejected the SQLite recommendation, chose Postgres instead"`
- `"Deployment to staging succeeded"`

**Bad examples**:
- Every individual tool call's raw output
- Every sentence of a conversation
- Routine, low-importance status updates (`should_record_episodic()`
  returns `False` for these by default — see
  `core/memory/policies.py`)

## Semantic Memory

**What**: structured facts/concepts, not tied to one event — "the kind of
thing you'd want to recall regardless of when you learned it."

**Lifetime**: persistent (SQLite), with a `confidence` score reflecting
how trustworthy the fact is (spec Part 27 — explicit user statements
score higher than agent inferences by default).

**Good examples**:
- `"Python is dynamically typed"` (concept="python", high confidence)
- A promoted, repeatedly-confirmed pattern from episodic memory

**Bad examples**:
- A one-time observation that isn't actually a stable fact — that
  belongs in Episodic memory instead, or nowhere
- Anything requiring semantic *search over meaning* rather than
  keyword/metadata match — that's the not-yet-implemented vector
  retrieval extension point, not something to force into today's
  text-match scoring

## Project Memory

**What**: everything scoped to one specific project/repository —
architecture, tech stack, known issues, testing/deployment state, prior
fix outcomes.

**Lifetime**: persistent (SQLite), namespaced `project:<id>`, isolated
from every other project.

**Good examples**:
- `tech_stack = "Python 3.12 + FastAPI + SQLite"`
- `known_issue = "flaky integration test in test_auth.py"`
- `last_dev_agent_outcome = "..."` (written automatically by
  `DeveloperAgent` after a successful step)

**Bad examples**:
- User-level preferences unrelated to this specific project (that's
  Preference memory)
- Full build/compiler output (summarize first, or don't persist)

## Quick decision guide

```
Is it about THIS task only, gone once it's done?        -> Working
Is it a durable fact ABOUT THE USER?                     -> Preference
Did something MEANINGFUL just happen (task done/failed)? -> Episodic
Is it a stable FACT/CONCEPT, not tied to one moment?      -> Semantic
Is it specific to ONE PROJECT/repo?                       -> Project
Could it be a secret (key/password/token)?                -> Don't store it at all
```
