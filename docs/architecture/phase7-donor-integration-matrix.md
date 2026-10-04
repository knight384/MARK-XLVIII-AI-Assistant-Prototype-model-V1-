# Phase 7 Donor Integration Matrix

## 1. Daemon / Lifecycle Subsystem
- **Donor Source Paths**: `jarvis-main/src/daemon/services.ts`, `jarvis-main/src/daemon/index.ts`
- **Responsibilities**: Application lifecycle, sequential startup/shutdown, dependency ordering, graceful degradation, status reporting.
- **Lifecycle Boundaries**: Process start -> Config load -> DB init -> Service init (ordered) -> Running -> Quiesce -> Drain -> Stop.
- **Data/Contracts**: `Service` interface (start, stop, status), `ServiceRegistry` (register, startAll, stopAll).
- **Closest MARK Equivalent**: `main.py` (currently ad-hoc script).
- **Structural Concepts to Preserve**: Explicit `Service` contracts, deterministic startup order, graceful shutdown phases (quiesce -> drain -> teardown).
- **MARK Files to Extend**: `main.py`
- **MARK Files to Create**: `core/runtime/lifecycle.py`, `core/runtime/services.py`, `core/runtime/identity.py`
- **Implementation Strategy**: Create a `Service` protocol and `ServiceRegistry` in Python. Wrap existing MARK singletons (MemoryService, ToolRegistry) as formal services. Implement headless vs desktop modes.
- **Security Implications**: Consistent lifecycle prevents dirty shutdowns and orphaned tasks that might bypass security gates.
- **Disposition**: CREATE NEW MARK MODULE USING DONOR STRUCTURE

## 2. Sidecar / Remote Capabilities Subsystem
- **Donor Source Paths**: `jarvis-main/src/sidecar/types.ts`, `jarvis-main/src/sidecar/protocol.ts`, `jarvis-main/src/sidecar/manager.ts`
- **Responsibilities**: Remote provider registration, capability advertisement, connection state, RPC routing.
- **Lifecycle Boundaries**: Connected -> Registered (capabilities sent) -> RPC Processing -> Disconnected.
- **Data/Contracts**: `SidecarRegistration`, `SidecarCapability`, `RPCRequest`, `RPCResultPayload`.
- **Closest MARK Equivalent**: None currently (only local tools exist).
- **Structural Concepts to Preserve**: Separation of capability *discovery* from *execution*, protocol contracts, trust validation (tokens).
- **MARK Files to Extend**: `core/tools/registry.py` (to handle remote capability metadata).
- **MARK Files to Create**: `core/runtime/capabilities.py`, `core/runtime/providers.py`, `core/runtime/sidecar_protocol.py`, `core/runtime/sidecar_manager.py`
- **Implementation Strategy**: Implement capability abstractions. Create `CapabilityProvider` base class. Implement `LocalCapabilityProvider` wrapping existing local tools. Implement `RemoteCapabilityProvider` that uses WebSocket protocols similar to donor `protocol.ts` to route requests.
- **Security Implications**: Trust boundaries between local runtime and remote provider. The remote execution MUST eventually map back to MARK's `ToolExecutor` and `PolicyEngine` on the brain side.
- **Disposition**: CREATE NEW MARK MODULE USING DONOR STRUCTURE

## 3. Authority / Security Subsystem
- **Donor Source Paths**: `jarvis-main/src/authority/engine.ts`, `jarvis-main/src/authority/approval.ts`
- **Responsibilities**: Policy enforcement, approvals, audits.
- **Lifecycle Boundaries**: Pre-execution validation.
- **Data/Contracts**: Access grants, impact levels.
- **Closest MARK Equivalent**: `core/policy/engine.py`, `core/policy/approval.py`
- **Structural Concepts to Preserve**: Centralized gating.
- **MARK Files to Extend**: N/A
- **MARK Files to Create**: N/A
- **Implementation Strategy**: MARK's existing PolicyEngine and ApprovalManager are already comprehensive and authoritative. The donor's authority system serves as a structural reference, but MARK's implementation takes precedence.
- **Security Implications**: Policy enforcement must remain strictly inside MARK's `ToolExecutor` -> `PolicyEngine` path.
- **Disposition**: KEEP MARK XLVIII

## 4. LLM / Model Tiers Subsystem
- **Donor Source Paths**: `jarvis-main/src/llm/`
- **Responsibilities**: Routing prompts to appropriately sized/priced models based on the task (tiers).
- **Lifecycle Boundaries**: Request -> Tier selection -> Provider invocation -> Result.
- **Data/Contracts**: Model tiers (FAST, REASONING, CODING, etc.).
- **Closest MARK Equivalent**: `core/llm/router.py`, `core/llm/gateway.py`
- **Structural Concepts to Preserve**: Intent-based model selection, tiers over hardcoded models.
- **MARK Files to Extend**: `core/llm/registry.py`, `core/llm/router.py`
- **MARK Files to Create**: N/A
- **Implementation Strategy**: Add Tier definitions to MARK's LLM router. Map tasks to FAST, REASONING, CODING, etc. instead of directly to a model string.
- **Security Implications**: Provider API keys remain in existing MARK SecretStore.
- **Disposition**: EXTEND EXISTING MARK MODULE

## 5. Workflows / Task Execution Subsystem
- **Donor Source Paths**: `jarvis-main/src/workflows/runtime/cancellation.ts`, `jarvis-main/src/workflows/runtime/event-bus.ts`
- **Responsibilities**: Long-running asynchronous workflows, cancellation propagation, event broadcasting.
- **Lifecycle Boundaries**: Job submission -> Execution -> Cancellation/Timeout/Completion.
- **Data/Contracts**: Cancellation tokens, operational events.
- **Closest MARK Equivalent**: `core/agent/orchestrator.py`, `core/agent/task.py`
- **Structural Concepts to Preserve**: Eventual cancellation propagation, background task failure isolation.
- **MARK Files to Extend**: `core/agent/task.py`, `core/agent/orchestrator.py`
- **MARK Files to Create**: `core/runtime/events.py`
- **Implementation Strategy**: Enhance MARK's `Task` with cancellation tokens. Implement an operational event bus for task lifecycle (distinct from security audit). Handle background orchestrator failures cleanly.
- **Security Implications**: Failure propagation prevents hung states.
- **Disposition**: EXTEND EXISTING MARK MODULE

## 6. Vault / Memory Subsystem
- **Donor Source Paths**: `jarvis-main/src/vault/`
- **Responsibilities**: Storage of memory, state, keys.
- **Lifecycle Boundaries**: Persistent across sessions.
- **Data/Contracts**: DB schema.
- **Closest MARK Equivalent**: `core/memory/memory_manager.py`
- **Structural Concepts to Preserve**: Locality tracking.
- **MARK Files to Extend**: `core/memory/memory_manager.py` (for locality metadata)
- **MARK Files to Create**: N/A
- **Implementation Strategy**: Keep MARK MemoryService authoritative. Add locality concepts (local vs remote) to determine where data is stored when running in hybrid mode.
- **Security Implications**: Memory access control and storage location are critical for privacy.
- **Disposition**: KEEP MARK XLVIII

## 7. Proactive Modules (Awareness, Goals, Personality)
- **Donor Source Paths**: `jarvis-main/src/awareness/`, `jarvis-main/src/goals/`, `jarvis-main/src/personality/`
- **Responsibilities**: Scheduled, autonomous agent behaviors.
- **Closest MARK Equivalent**: None currently.
- **Implementation Strategy**: Defer to future phases to maintain focus on runtime foundations.
- **Disposition**: DEFER
