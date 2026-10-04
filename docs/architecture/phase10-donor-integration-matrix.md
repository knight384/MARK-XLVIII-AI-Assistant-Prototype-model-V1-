# Phase 10 Donor-to-MARK Integration Matrix

## 1. Awareness System
- **Donor source**: `jarvis-main/src/awareness/service.ts`, `context-tracker.ts`, `suggestion-engine.ts`
- **Donor responsibility**: Collect sidecar events (screen capture, idle, focus), track context, rate-limit proactive suggestions.
- **Donor lifecycle**: Background singleton daemon processing stream of events.
- **Donor data model**: `ScreenContext`, `LiveContext`.
- **Closest MARK subsystem**: `actions/proactive.py`, `core/runtime/events.py` (EventBus).
- **Existing MARK code to extend**: `EventBus` for signal ingestion, `ProactiveEngine` for decision making.
- **New MARK modules required**: `core/awareness/tracker.py`, `core/awareness/signals.py`, `core/awareness/opportunity.py`.
- **Implementation elements adapted**: Rate-limiting, deduplication, signal types (stuck, error, repeated task failure).
- **Changes required for MARK**: Do not ingest continuous screen OCR. Ingest bounded system events (task_failed, goal_at_risk).
- **Security implications**: Awareness is strictly observational. It CANNOT execute tools or bypass authorization.
- **Memory implications**: Uses `MemoryService` for context; keeps a small sliding window in memory for tracker.
- **Mission integration**: Generates `CREATE_MISSION` opportunities.
- **EventBus integration**: Subscribes to runtime events (Task/Mission success/fail).
- **Tests**: `tests/test_awareness.py`
- **Provenance status**: ADAPT FROM DONOR

## 2. Context Graph
- **Donor source**: `jarvis-main/src/awareness/context-graph.ts`
- **Donor responsibility**: Links captures to vault entities (projects, tools, facts).
- **Donor lifecycle**: Synchronous on capture.
- **Closest MARK subsystem**: `core/memory/service.py`
- **New MARK modules required**: Bounded link models in memory metadata.
- **Changes required for MARK**: Will not build a continuous graph of screen text. Will build explicit relations (Goal -> Mission -> Task).
- **Provenance status**: DEFER massive graph; REIMPLEMENT FROM DONOR DESIGN for explicit structured relations.

## 3. Goals
- **Donor source**: `jarvis-main/src/goals/service.ts`, `accountability.ts`, `estimator.ts`
- **Donor responsibility**: Track user objectives, milestones, and estimate completion.
- **Donor lifecycle**: CRUD via REST, evaluated periodically for rhythm/accountability.
- **Closest MARK subsystem**: New subsystem.
- **New MARK modules required**: `core/goals/models.py`, `core/goals/service.py`, `core/goals/estimator.py`.
- **Implementation elements adapted**: Goal state machine (DRAFT, ACTIVE, PAUSED, COMPLETED, AT_RISK), milestones, accountability rhythm.
- **Changes required for MARK**: Goals must be strictly distinguished from Missions. Goal = Intent, Mission = Scheduled Work.
- **Memory implications**: Store goals natively, possibly in a `goals.db` SQLite store or as explicit memory records. Will use SQLite store for robust relations.
- **Mission integration**: Missions will carry a `goal_id` foreign key.
- **Provenance status**: ADAPT FROM DONOR

## 4. Commitments
- **Donor source**: implicit in goals/accountability.ts
- **Donor responsibility**: Track promises and deadlines.
- **New MARK modules required**: `core/goals/commitments.py`
- **Changes required for MARK**: First-class abstraction for promises.
- **Provenance status**: CREATE MARK-NATIVE MODULE

## 5. Personality & Learning
- **Donor source**: `jarvis-main/src/personality/model.ts`, `learner.ts`, `adapter.ts`
- **Donor responsibility**: Maintain user interaction preferences and adapt tone/verbosity.
- **Closest MARK subsystem**: `core/memory/preferences.py`
- **New MARK modules required**: `core/personality/models.py`, `core/personality/learner.py`, `core/personality/service.py`.
- **Implementation elements adapted**: Preference schema, confidence intervals, explicit decay/reversibility.
- **Changes required for MARK**: Must explicitly NOT influence the `PolicyEngine` or security decisions.
- **Memory implications**: Delegate storage to `MemoryService.save_preference()`.
- **Provenance status**: ADAPT FROM DONOR
