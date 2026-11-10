# Hermes Roadmap Implementation Foundations

This document captures the verified integration points, contracts, and reusable infrastructure
for the seven-phase roadmap. It is derived from the actual source code at commit `704a5cb0`
(master branch) and updated as each phase is implemented.

---

## Phase Status Summary

| Rank | Phase | Difficulty | Status |
|------|-------|------------|--------|
| 1 | Adaptive Personality — initial version | 2/5 | ✅ **IMPLEMENTED** |
| 2 | Saturnite Gateway Integration — narrow adapter | 3/5 | ⚠️ **PARTIAL** |
| 3 | Shared Inference Scheduler | 3.5/5 | 📐 Prepared |
| 4 | Structured Experience Collection | 4/5 | 📐 Prepared |
| 5 | CUA Interaction Learning | 4/5 | 📐 Prepared |
| 6 | Deep Dreaming and Overclock | 4.5/5 | 📐 Prepared |
| 7 | Evolutionary Optimization / NEAT | 5/5 | 📐 Prepared |

---

## 1. Adaptive Personality — IMPLEMENTED

### Implementation Summary

**Files Created/Modified:**

| File | Change |
|------|--------|
| `agent/adaptive_personality.py` | New module: `Preference` dataclass, `AdaptivePersonalityManager`, `build_personality_block_from_store()` |
| `agent/system_prompt.py` | Added personality block to `_memory_parts()` volatile tier |
| `agent/agent_init.py` | Initialize `_adaptive_personality` in `_init_memory()` |
| `tests/agent/test_adaptive_personality.py` | 37 behavior-contract tests |

### Architecture Decisions

1. **Storage**: Preferences stored as structured JSON entries in USER.md (existing built-in memory store), prefixed with `PREF:` for distinction from plain-text user facts.

2. **Prompt Integration**: Personality block rendered into volatile tier via `_memory_parts()`, after existing memory/user blocks. No cache invalidation on mid-session writes (snapshot-based).

3. **Session Initialization**: `AdaptivePersonalityManager` created in `_init_memory()` after `MemoryStore.load_from_disk()`, `load()` called immediately.

4. **Prompt Refresh**: Existing `prompt_refresh.py` mechanism reused — `rebuild_for_refresh()` calls `_build_system_prompt()` which includes `_memory_parts()`, so preference updates are adopted at the next permitted boundary.

5. **Profile Isolation**: Inherited from `MemoryStore` via `get_hermes_home()` — each profile has its own `memories/USER.md`.

6. **Approval Gates**: All writes go through `MemoryStore.add()/remove()` which enforce existing approval/destructive-operation gates.

### Test Coverage

- Preference serialization/deserialization (10 tests)
- Manager CRUD operations (13 tests)
- System prompt integration (4 tests)
- Profile isolation (1 test)
- Preference semantics (5 tests)
- Failure handling (3 tests)

### Unresolved / Future Work

- Automatic preference inference from conversation history (requires Experience Collection)
- Domain-scoped preferences beyond `domain:<name>` (awaiting Experience Collection)
---

## 3. Shared Inference Scheduler — Prepared

### Current Inference Paths (Verified)

| Path | Entry Point | Key Files |
|------|-------------|-----------|
| Foreground turn | `agent/conversation_loop.py::run_conversation` | `turn_api_request.py`, `turn_api_call.py` |
| Auxiliary | `agent/auxiliary_client.py::call_llm()` | `auxiliary_client.py`, `auxiliary_hooks.py` |
| MoA | `agent/moa_loop.py` | `moa_loop.py`, `moa_alternation.py` |
| Background review | `agent/background_review.py` | `background_review.py`, `review_idle_queue.py` |
| Codex continuation | `turn_response_intake.py` | `turn_response_intake.py` |

### Credential Pool & Cooldown (Verified)

**Files:**
- `agent/credential_pool.py` — pool management, rotation
- `agent/fallback_cooldown.py` — per-credential cooldown tracking
- `agent/credential_pool_model_cooldowns.py` — model-specific cooldowns
- `agent/retry_utils.py` — `jittered_backoff`, `classify_api_error`

### Scheduler Insertion Point

**Recommended boundary:** Read-only admission layer **above** credential pool, **below** `perform_api_call()` / `call_llm()`.

```
[Turn Loop / Aux / MoA / Background]
            ↓
    [InferenceScheduler.admit(request)]
            ↓ (allowed)
    [CredentialPool.acquire()]
            ↓
    [perform_api_call() / call_llm()]
```

### Required Scheduler Capabilities

1. **Foreground vs background priority** — tag requests at call site
2. **Provider-specific pacing** — token-bucket per provider
3. **Cooldown & Retry-After handling** — extend `fallback_cooldown.py` logic
3. **Auxiliary-model scheduling** — separate queue with lower priority
4. **Multi-process coordination** — file-based lock or Redis (for gateway workers)

### Preserved Components

- `CredentialPool` — persistence format, rotation logic unchanged
- `fallback_cooldown.py` — per-credential cooldown state
- `retry_utils.py` — error classification, backoff

### Reusable Test Fixtures

- `tests/agent/test_credential_pool.py` — pool behavior
- `tests/agent/test_auxiliary_routing.py` — auxiliary path
- Mock provider fixtures for deterministic scheduling tests

### Unresolved Decisions

- Scheduler state persistence across restarts
- Cross-process lock implementation (file-based vs. external)
- Whether to batch auxiliary requests

---

## 4. Structured Experience Collection — Prepared

### Current Data Sources (Verified)

| Source | Location | Format |
|--------|----------|--------|
| User request | `conversation_loop.py` turn start | OpenAI message dict |
| Tool calls | `turn_tool_round.py` | `tool_call` dicts |
| Tool results | `turn_tool_round.py` → `model_tools.py` | JSON strings |
| Failures | `turn_response_check.py`, `turn_api_error.py` | Exception + context |
| Recovery | `turn_recovery.py` | Strategy + outcome |
| Model usage | `turn_usage.py` | Token counts, costs |
| Session context | `hermes_state.py` | SQLite sessions table |

### Storage Decision (Unresolved)

| Option | Pros | Cons |
|--------|------|------|
| Existing per-profile SQLite (`state.db`) | Already profile-isolated, WAL mode | Schema migrations needed |
| Separate append-only log | Immutable, easy replay, no migrations | Separate file management |
| Both (SQLite for queries, log for audit) | Best of both | More complex |

**Decision required before implementation.**

### Experience Record Schema (Proposed)

```python
@dataclass
class ExperienceRecord:
    id: str                    # ULID
    session_id: str            # Profile-scoped
    turn_number: int
    timestamp: datetime        # UTC
    user_request: str          # Sanitized
    tool_calls: list[ToolCall] # Name, args, result, duration
    outcome: str               # success / failure / partial
    recovery_strategy: str     # If applicable
    model_usage: ModelUsage    # Tokens, cost, provider
    profile_context: dict      # Active skills, memory size, etc.
    privacy_level: str         # public / private / sensitive
```

### Versioning Strategy

- Schema version in record header
- Migration scripts in `agent/experience_migrations.py`
- Backward-compatible reads: missing fields → `None`

### Reusable Infrastructure

- `tests/conftest.py` — `_isolate_hermes_home` fixture for temp homes
- `tests/tools/test_memory_target_contract.py` — pattern for profile-isolated storage tests
- `hermes_constants.get_hermes_home()` — profile-aware path resolution

### Unresolved Decisions

- Storage backend (SQLite vs. append-only log)
- Retention policy (configurable TTL per privacy level)
- PII redaction strategy (reuse `agent/redact.py`)
- Whether background-review forks write experience records
---

## 5. CUA Interaction Learning — Prepared

### Current CUA Interfaces (Verified)

**Files:**
- `tools/computer_use/computer_use_tool.py` — tool entry point
- `tools/computer_use/backend.py` — `ComputerUseBackend` ABC
- `tools/computer_use/tool.py` — `ActionResult`, `CaptureResult`, `UIElement`

### Key Signals for Learning (Verified)

| Signal | Source | Description |
|--------|--------|-------------|
| `ActionResult.verified` | `backend.py:120` | Whether action achieved expected effect |
| `ActionResult.effect` | `backend.py:115` | Observed state change |
| `ActionResult.escalation` | `backend.py:118` | Retry/fallback path taken |
| `ActionResult.path` | `backend.py:110` | Element interaction path |
| `UIElement.element_token` | `backend.py:45` | Stable accessibility identifier |
| `UIElement.role` / `label` | `backend.py:42` | Semantic element identity |

### Learning Identity Strategy

**Recommended:** `(app, role, label, element_token)` — stable across sessions
**Avoid:** Screen coordinates (transient, resolution-dependent)

### Reusable Infrastructure

- `CaptureResult` normalization helpers (to be created in `agent/cua_learning/`)
- Test fixtures: `tests/tools/test_computer_use_tool.py` — mock backend patterns

### Constraints

- Do not replace `ComputerUseBackend` ABC
- Do not rewrite existing drivers
- Keep learned strategies separate from static coordinate recordings

### Unresolved Decisions

- Storage format for learned navigation strategies
- Whether to use experience collection (Phase 4) as backend
- Conflict resolution when multiple strategies exist for same element

---

## 6. Deep Dreaming and Overclock — Prepared

### Current Background Review (Verified)

**Files:**
- `agent/background_review.py` — main entry, fork creation, execution
- `agent/review_idle_queue.py` — idle-time job queue
- `agent/memory_manager.py` — provider hooks (`on_pre_compress`, `on_memory_write`)

### Reusable Mechanisms

| Mechanism | Location | Reusable? |
|-----------|----------|-----------|
| Fork creation with cache parity | `background_review.py:1000-1050` | ✅ Yes |
| Resource limits (turns, budget) | `background_review.py:1120-1140` | ✅ Yes |
| Model selection (auxiliary) | `auxiliary_client.py` | ✅ Yes |
| Cancellation | `review_idle_queue.py` | ✅ Yes |
| Proposal creation | `skill_manage` via `curator.py` | ✅ Yes |
| Human approval | `tools/write_approval.py` | ✅ Yes |

### Gaps to Address

- **Bounded compute budgets**: Current review uses agent's budget; need independent limit
- **Specialist model roles**: `auxiliary.<task>.provider` config exists but not used for review
- **Independent evaluation**: No mechanism to evaluate proposals without human
- **Consequential change gates**: Proposals can modify skills/memory; need explicit approval

### Constraints

- Do not create another daemon/background framework without evidence
- Reuse `background_review.py` and `review_idle_queue.py`
- Background process must not freely modify preferences/permissions

### Unresolved Decisions

- Whether to extend `review_idle_queue.py` or create new job type
- How to enforce compute budgets (token count vs. wall time)
- Evaluation criteria for autonomous proposals

---

## 7. Evolutionary Optimization / NEAT — Prepared

### Required Infrastructure (All Unimplemented)

| Component | Description |
|-----------|-------------|
| Experience dataset | Output of Phase 4 |
| Evaluation harness | Reproducible scoring of policies |
| Candidate policy representation | Routing rules, model selection, tool choice |
| Scoring metrics | Latency, cost, success rate, user satisfaction |
| Comparative evaluation | A/B or tournament |
| Pareto-frontier tracking | Multi-objective optimization |
| Safety gates | Rollback, canary, human approval |
| Controlled promotion | Gradual rollout |

### Critical Distinction

**Operational optimization** (this phase): Routing, model selection, tool-selection policy.
**NOT language-model weight training** — no gradient updates, no fine-tuning.

### Reusable Infrastructure

- Experience dataset schema (Phase 4)
- `agent/credential_pool.py` — routing policy hooks
- `agent/auxiliary_client.py` — model selection policy hooks
- `tools/registry.py` — tool availability/check_fn hooks

### Unresolved Decisions

- Policy representation format (rule-based vs. neural)
- Whether NEAT is appropriate or simpler bandit/RL
- Evaluation environment (production vs. shadow vs. synthetic)
- Safety criteria for automatic promotion
---

## Cross-Cutting Foundations

### Shared Test Helpers (Existing + Extended)

| Helper | Location | Extended For |
|--------|----------|--------------|
| `temp_hermes_home` | `tests/conftest.py` | All phases |
| `profile_env` | `tests/hermes_cli/test_profiles.py` | Phases 1, 2, 4 |
| `memory_store` | `tests/tools/test_memory_tool.py` | Phases 1, 4, 5 |
| `mock_agent` | `tests/agent/test_adaptive_personality.py` | Phases 1, 3, 4, 6 |

### Data Contracts (To Be Formalized)

| Contract | Consumers | Status |
|----------|-----------|--------|
| Preference entry format | Phase 1, 3, 6 | ✅ Defined in `adaptive_personality.py` |
| Experience record | Phase 4, 5, 6, 7 | 📐 Proposed |
| CUA learning signal | Phase 5 | 📐 Identified |
| Scheduler admission decision | Phase 3 | 📐 TBD |
| Dreaming proposal | Phase 6 | 📐 TBD |

### Profile Isolation Invariants (Verified)

1. All storage uses `get_hermes_home()` — never hardcoded paths
2. ContextVar `_HERMES_HOME_OVERRIDE` binds per-profile scope
3. Background forks inherit context via `contextvars.copy_context()`
4. Module globals never hold profile-specific state

### Prompt-Cache Invariant (Verified)

1. System prompt built once per session (`_cached_system_prompt`)
2. Only context compression triggers rebuild (`invalidate_system_prompt()`)
3. Prompt refresh uses epoch mechanism (`prompt_refresh.py`)
4. **No mid-conversation prompt mutation** — adaptive personality respects this via snapshot-based rendering

---

## Separate Track: Go Gateway Investigation

### Benchmark Protocol (Documented, Not Implemented)

| Concurrency | Metrics |
|-------------|---------|
| 1 session | CPU, RAM, P50/P95/P99 latency, throughput |
| 10 sessions | Same + worker counts, event-loop latency |
| 50 sessions | Same + error rates |
| 100 sessions | Same + memory growth |

### Proposed Division (Not Implemented)

| Layer | Language | Responsibility |
|-------|----------|----------------|
| Data plane | Go | WebSocket, HTTP, streaming, connection mgmt |
| Control plane | Python | Sessions, profiles, auth, tools, memory, agent |

### Constraints

- Go must remain optional (Python-only fallback)
- Goroutines don't make Python agent execution concurrent
- Only promote if benchmarks justify added complexity

---

## Implementation Order (Dependency-Aware)

```
Phase 1: Adaptive Personality      ✅ DONE
    ↓
Phase 3: Shared Inference Scheduler    (enables priority for Phase 2, 4)
    ↓
Phase 4: Structured Experience Collection   (feeds Phase 5, 6, 7)
    ↓
Phase 2: Saturnite Adapter    (independent, can parallelize)
Phase 5: CUA Learning         (needs Phase 4)
    ↓
Phase 6: Deep Dreaming        (needs Phase 4, 5)
    ↓
Phase 7: NEAT                 (needs Phase 4, 6)
```

### Next Logical Implementation

**Phase 3 (Shared Inference Scheduler)** — enables foreground priority over background work, which is prerequisite for bounded compute budgets in Phase 6 and fair scheduling in Phase 4.

---

## Non-Goals (Explicitly Excluded)

- ❌ Replacing all platform adapters with Saturnite
- ❌ Introducing WASM without demonstrated requirement
- ❌ Creating Saturnite model provider without concrete inference use case
- ❌ Making general tool runtime implement computer-use backend
- ❌ Language-model weight training (NEAT is operational only)
- ❌ New core tools when CLI+skill or existing tool suffices
- ❌ New `HERMES_*` env vars for non-secret config
- ❌ Outbound telemetry without opt-in gate

---

## Validation Checklist

### Phase 1 (Adaptive Personality) — COMPLETE

- [x] Persistent preference profile exists
- [x] Preferences load at correct session initialization point
- [x] Preferences influence agent behavior (prompt integration)
- [x] Preference updates work (add/replace/remove)
- [x] Preferences can be inspected
- [x] Individual preferences can be removed
- [x] Reset follows existing approval rules
- [x] Explicit corrections work
- [x] Current-task instructions not silently persisted
- [x] Profile isolation tested
- [x] Memory/provider failure doesn't break agent init
- [x] Prompt-cache invariant preserved
- [x] Existing prompt-refresh mechanism used correctly
- [x] CLI and gateway paths covered
- [x] No automatic preference inference introduced
- [x] 37 behavior-contract tests passing

### Phases 2-7 — Prepared (Not Implemented)

- [x] Integration points verified against current source
- [x] Exact difficulty ranking preserved
- [x] Dependency order documented separately
- [x] Shared test helpers identified/extended
- [x] Concrete implementation blueprints for each phase
- [x] Unresolved design decisions explicitly recorded
- [x] No future phase accidentally implemented
- [x] No unused speculative frameworks introduced
- [x] Go benchmarking track documented separately

---

*Last updated: Commit `704a5cb0` (master)*
*Generated during Adaptive Personality implementation*
- Migration path for schema version changes (currently v1, no migrations needed)