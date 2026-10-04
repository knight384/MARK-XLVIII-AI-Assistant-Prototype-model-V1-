# Memory Architecture

Phase 5 adds `core/memory/` — a layered memory subsystem serving the
current task (Working), user facts (Preference), meaningful past events
(Episodic), structured knowledge (Semantic), and per-project context
(Project). Agents never touch storage directly; everything goes through
`MemoryService`.

## Why "memory is a service, not a file"

Before Phase 5, user-fact memory lived entirely in
`memory/memory_manager.py` reading/writing `memory/long_term.json`
directly, and `actions/computer_control.py` had its own second direct read
of that same file. Adding episodic/semantic/project memory on top of that
pattern would have meant more ad hoc file access scattered across the
codebase — exactly what Phase 4's Tool Registry avoided for actions.
`MemoryService` is the equivalent consolidation for memory: one interface,
storage swappable behind it.

## Memory types

```python
class MemoryType(str, Enum):
    WORKING = "working"
    PREFERENCE = "preference"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROJECT = "project"
```

| Type | Persistent? | Store | Typical writer |
|---|---|---|---|
| WORKING | No — in-process, scope-bounded | in-memory dict (`working.py`) | any agent, mid-task |
| PREFERENCE | Yes | JSON (`preferences.json`) | user (explicit `save_memory` tool), migration |
| EPISODIC | Yes | SQLite (`memory.db`) | Orchestrator (task outcomes), agents |
| SEMANTIC | Yes | SQLite (`memory.db`) | agents (`promote_to_semantic`), explicit facts |
| PROJECT | Yes | SQLite (`memory.db`) | DeveloperAgent, project tooling |

## MemoryRecord

Storage-neutral, one shape for every type: `memory_id`, `memory_type`,
`content`, `summary`, `source` (provenance), `created_at`/`updated_at`/
`last_accessed_at`, `importance`, `confidence`, `tags`, `namespace`,
`project_id`, `user_id`, `expires_at`, `metadata`.

## MemoryStore — the storage abstraction

```python
class MemoryStore(ABC):
    save(record) -> None
    get(memory_id) -> MemoryRecord | None
    update(record) -> None
    delete(memory_id) -> bool
    delete_by_namespace(namespace) -> int
    delete_by_project(project_id) -> int
    search(memory_types=(), namespace=None, project_id=None, tags=(), limit=None) -> list[MemoryRecord]
    all() -> list[MemoryRecord]
    purge_expired(now=None) -> int
```

Two implementations exist, both behind this same interface — nothing above
`MemoryStore` knows or cares which one is in use:

- **`JsonMemoryStore`** — used for Preference memory. Small, infrequently
  written, matches the existing `memory/long_term.json`'s storage model
  (whole-file JSON), just moved behind the interface.
- **`SqliteMemoryStore`** — used for the combined Episodic/Semantic/Project
  store. Chosen because that combined store can grow to many more records
  than the hand-curated preference set, and benefits from indexed
  type/namespace/project lookups and safe concurrent writes when multiple
  agents complete steps close together within one orchestrated task (spec
  Part 39). Stdlib `sqlite3`, one file, a thread lock around writes — no
  server process, no new infrastructure. **This decision is intentionally
  the smallest step up from JSON that meets the "needs indexed queries and
  concurrent access" bar** (Phase 5 spec, Part 11) — not a jump to
  Postgres/Redis/a vector database.

## MemoryService — the single interface

```python
class MemoryService:
    remember(content, memory_type, ...) -> MemoryRecord | None
    retrieve(query: RetrievalQuery) -> list[RetrievalResult]
    get(memory_id, memory_type) -> MemoryRecord | None
    update(record) -> None
    forget(memory_id, memory_type) -> bool
    forget_by_namespace(namespace) -> int
    forget_by_project(project_id) -> int
    clear_working(scope) -> int
    summarize(scope, model_gateway=None) -> str
    promote_to_episodic(scope, key, event, ...) -> MemoryRecord | None
    promote_to_semantic(episodic_record, concept, ...) -> MemoryRecord
    demote(memory_id, memory_type, new_importance=0.2) -> None

    # typed sub-layer access
    .working / .preferences / .episodic / .semantic / .projects
```

`get_default_memory_service()` builds the process-wide instance, wiring
`JsonMemoryStore`/`SqliteMemoryStore` against Phase 1's `ConfigService`
paths, and runs the legacy migration (see below) on first construction.

## Namespaces (spec Part 18)

`global` (unscoped facts), `user` (preference memory), `project:<id>`,
`task:<id>`/`session:<id>` (working memory scopes). `MemoryStore.search()`
and `MemoryRetriever` both filter by namespace — an agent asking for
`project:X` memory never incidentally sees `project:Y`'s records (tested:
`tests/memory/test_projects.py::test_project_isolation`).

## Retrieval and relevance scoring

`RetrievalQuery(query, memory_types, namespace, project_id, tags, limit,
min_relevance)` → `MemoryRetriever.retrieve()` → coarse store-level
filtering (type/namespace/project/tags via `MemoryStore.search()`), then
deterministic scoring:

```
relevance = 0.4·text_match + 0.15·namespace_match + 0.15·project_match
          + 0.1·recency + 0.1·importance + 0.1·confidence
```

`text_match` is token-overlap (query words ∩ content/summary/tag words) —
**not embedding similarity**. Recency uses a 14-day half-life decay. Every
call returns a human-readable `reason` string (e.g. `"text=0.63
namespace=1 project=0 recency=0.94 importance=0.70 confidence=1.00"`) for
debug logging, without needing to log the memory content itself.

**Semantic vector retrieval: NOT YET IMPLEMENTED.** `MemoryRetriever`'s
`retrieve(query) -> list[RetrievalResult]` signature is the extension
point — a future `VectorSemanticStore`/embedding-based retriever could
implement the same interface without any caller (agents, Orchestrator,
Planner) changing. Metadata/text search meets Phase 5's actual
requirements; nothing currently demonstrates a need for embeddings.

Retrieval is always bounded: a hard ceiling of 50 results regardless of
what a caller requests, plus `MemoryConfig.retrieval_limit` (default 10) as
the practical default.

## Retention / expiration / limits

- `MemoryRecord.expires_at` + `MemoryStore.purge_expired()` /
  `MemoryService.purge_expired()` — opt-in per record; nothing expires by
  default except what a caller explicitly sets a TTL for.
- `WorkingMemory` is bounded per scope: `max_entries_per_scope` (default
  50) and `max_chars_per_scope` (default 8000), oldest-first eviction.
- `PreferenceMemory` preserves the legacy per-value length cap
  (`MAX_VALUE_LENGTH = 380`) and total-size cap
  (`MEMORY_MAX_CHARS = 2200`, oldest-first trim) — the exact limits the
  pre-Phase-5 `memory_manager.py` already enforced.

## Episodic write policy (spec Part 13)

Episodic memory captures **meaningful events**, not conversation logs.
`core.memory.policies.should_record_episodic()` offers a shared, explicit
rule set (explicit user request, task completed/failed, importance ≥ 0.8,
or a small set of trigger keywords) for callers that want a default
policy instead of ad hoc judgment calls — but callers that already know
their event matters (the Orchestrator recording a task outcome) just call
`EpisodicMemory.record_event()` directly.

## Promotion (spec Part 25) — explicit only

```
Working memory  --promote_to_episodic()-->  Episodic memory
Episodic event  --promote_to_semantic()-->  Semantic fact
```

No autonomous/automatic promotion exists — both are explicit method calls
a caller chooses to make.

## Project identity (spec Part 17)

`derive_project_id(repo_path, explicit_id=None)`: explicit ID first, then
the repo's Git remote URL hash (stable across clones of the same repo),
then a hash of the absolute repo path as the final fallback. No new
manifest format required.

## Privacy (spec Part 36)

- `MemoryService.remember()` refuses to store content that looks like a
  secret (API key / password / bearer token shape — pattern-matched, not a
  vault) and logs a warning instead — tested in
  `tests/memory/test_service.py`.
- No memory content is logged at INFO level anywhere in `core/memory/` —
  logs carry counts, category names, namespaces, and (for retrieval) the
  scoring `reason` string, never raw content. `SaveMemoryTool`'s log line
  was fixed in this phase to stop logging the saved value.
- `MemoryService.forget()` / `forget_by_namespace()` / `forget_by_project()`
  provide real deletion, not just marking-inactive.
- `memory_enabled=False` (via `MemoryConfig`/`ConfigService`) disables all
  persistent writes and retrieval; `WorkingMemory` still functions (it was
  never persistent in the first place) so in-flight execution isn't broken.

## Configuration (spec Part 37)

All memory settings route through Phase 1's `ConfigService` — no second
config system:

```
memory_enabled                        (default True)
memory_working_limit                  (default 50)
memory_working_max_chars              (default 8000)
memory_retrieval_limit                (default 10)
memory_max_context_chars              (default 2000)
memory_episodic_retention_days        (default 180, None = no auto-expiry)
memory_semantic_search_enabled        (default True — metadata search, NOT vector)
```

## AgentContext integration (spec Part 28)

```python
@dataclass
class AgentContext:
    ...
    memory: Any = None   # core.memory.service.MemoryService
    ...

    def retrieve_memory(self, query, memory_types=(), project_id=None, limit=5) -> list:
        """Best-effort — returns [] on any failure, never raises."""
```

`Orchestrator` retrieves a small, bounded set of relevant memories
(`_retrieve_planning_context()`, capped at `memory.config.max_context_chars`)
before calling the Planner, and records a single episodic event
(`_record_task_outcome()`) when a task finishes — not per-step, not raw
logs. `Planner.plan(goal, memory_context="...")` accepts this pre-retrieved
text; the Planner itself never touches a store. `DeveloperAgent` layers
project-memory retrieval/write on top of the standard `ToolUsingAgent` flow
(see `docs/agents.md`).

Every memory touchpoint in the agent runtime is wrapped in try/except
returning an empty/no-op result on failure — a memory outage degrades
gracefully rather than breaking task execution (spec Part 40).

## Migration from the legacy JSON file

`core.memory.migration.migrate_legacy_json(legacy_path, preference_memory)`:
idempotent (re-running never duplicates or overwrites a since-changed
value), never deletes the original file, reports success/failure via a
`MigrationReport`, and only logs counts/category names — never content.
`MemoryService.__init__(..., legacy_json_path=...)` runs it automatically
on first construction of the default service. See `docs/memory.md` for the
documented transition plan.

## Backward compatibility: memory/memory_manager.py

Kept as a thin, deprecated shim (`load_memory`, `save_memory`,
`update_memory`, `format_memory_for_prompt`, `remember`, `forget`) —
same function signatures, same output shapes (including
`format_memory_for_prompt()`'s exact prior text format, since that string
is injected directly into the Gemini Live system prompt), now delegating
to `MemoryService` internally. This is why **`main.py` required zero
changes** in Phase 5 — its existing `load_memory()`/
`format_memory_for_prompt()` calls at session start keep working exactly
as before, just backed by the new system.

## What Phase 5 does NOT do

- No vector/embedding search (explicitly deferred — see above).
- No full Policy Engine / approval enforcement over memory access beyond
  basic namespace scoping (Phase 6).
- No distributed/multi-process memory store (single-process SQLite + JSON
  is sufficient; Phase 7 will address deployment topology generally).
- No automatic/autonomous memory promotion — every promotion is an
  explicit call.
