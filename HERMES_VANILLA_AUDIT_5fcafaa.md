# Hermes Agent — Deep Source-Code Architecture Audit
**Commit**: 5fcafaaedae5ff677b9c66ae521d6d6e67182451 (master, clean tree)
**Generated**: 2026-11-06

---

## 1. Executive Summary

Hermes is a **multi-profile, multi-surface personal AI agent** with a narrow core and wide capability surface at the edges (plugins, skills, adapters). The architecture enforces two sacred invariants:
- **Prompt caching is sacrosanct** — the system prompt is byte-stable for a conversation's lifetime; only context compression may mutate it.
- **Core is a narrow waist** — new capabilities arrive as CLI commands + skills, service-gated tools, or plugins, not core tools.

This audit covers the vanilla implementation as the technical foundation for extending into a self-improving personal agent with Saturnite components.

---

## 2. Agent Execution Loop & Turn Lifecycle

### 2.1 Facade/Sibling Architecture
The agent follows a **facade + topic siblings** pattern where former god files are split:

| Facade | Siblings (key phases) |
|--------|----------------------|
| `run_agent.py` → `AIAgent` | `agent/turn_facade.py` (lease), `agent/turn_api_call.py`, `agent/turn_tool_round.py`, `agent/turn_context_compaction.py`, `agent/turn_recovery*.py`, `agent/turn_overflow.py`, `agent/turn_summary.py`, `agent/turn_liveness.py` |
| `agent/conversation_loop.py` | `turn_preflight*`, `turn_iteration_prep`, `turn_request_assembly`, `turn_response_intake`, `turn_empty_response`, `turn_tool_validation`, `turn_truncation`, `turn_scripted_prelude`, `turn_stop_gates`, `turn_usage`, `turn_final_response`, `turn_finalizer` |
| `model_tools.py` | `tools/registry.py`, `tools/delegate_tool.py`, `agent/inline_tool_executors.py`, `agent/tool_executor.py` |

**Construction**: `AIAgent.__init__` accepts ~60 parameters (credentials, routing, callbacks, session context, budget, credential pool). `init_agent()` in `agent/agent_init.py` runs phased initialization: routing → client → tools → session → compression.

### 2.2 Turn Loop (`agent/conversation_loop.py::run_conversation`)
```python
while (api_call_count < max_iterations and iteration_budget.remaining > 0) or _budget_grace_call:
    if interrupt_requested: break
    response = client.chat.completions.create(model=model, messages=messages, tools=tool_schemas)
    if response.tool_calls:
        for tc in response.tool_calls:
            messages.append(tool_result_message(handle_function_call(tc.name, tc.args, task_id)))
        api_call_count += 1
    else:
        return response.content
```

**Key phases** (each a separate sibling file):
- `turn_preflight` — budget, interrupt, MCP refresh
- `turn_api_call` — provider call with structured error classification
- `turn_tool_round` → `turn_tool_validation` — execute + validate
- `turn_context_compaction` — compression at 50%/85% thresholds
- `turn_overflow` / `turn_truncation` — provider overflow handling
- `turn_recovery` / `turn_recovery_autorecover` — wait-and-retry ladder
- `turn_final_response` / `turn_summary` — finalize

### 2.3 Message-Flow Invariants
| Invariant | Enforcement |
|-----------|-------------|
| **Prompt cache byte-stable** | System prompt never rebuilt mid-conversation; only compression mutates context; skill slash commands inject via user message |
| **Strict role alternation** | Never two same-role messages; `/steer` delivered as standalone user row after tool result |
| **Context files loaded once** | At startup from CWD only; capped by `CONTEXT_FILE_MAX_CHARS` / dynamic window cap |
| **Subdirectory hints** | Append to tool result (truncated at 32K); reject paths outside working dir |

### 2.4 Agent-Level Tools (Inline Executors)
Tools like `todo`, `memory`, `skill_manage` are intercepted by `agent/tool_executor.py` via `INLINE_TOOL_EXECUTORS` table in `agent/inline_tool_executors.py` — no `if name == ...` chains.

---

## 3. Prompt Assembly, Caching & Context Compression

### 3.1 Prompt Assembly (`agent/prompt_builder.py`)
- **System prompt**: Built once at session start — byte-stable for conversation lifetime
- **Context files**: Loaded from CWD at startup only (never mid-conversation)
- **Skills prompt**: Injected via `agent/skill_prompt.py` at initialization; skill changes defer to next session (unless `--now`)
- **Ephemeral additions**: Ride user messages or tool results, never system prompt

### 3.2 Prompt Caching — The Sacred Invariant
```python
# Only compression breaks the cache — sanctioned and controlled
# Never: reload memories, swap toolsets, rebuild system prompt mid-conversation
```

**Cache-scope parity for forks** (`agent/prompt_cache_scope.py`):
- Background review forks inherit parent's `_cached_system_prompt`, `session_start`
- `_inherited_cache_scope` resolves both Anthropic `prompt_cache_key` and xAI `conversation=` affinity
- `_prompt_cache_fork_tag = "review"` prevents fork's compression from evicting parent's server slot

### 3.3 Context Compression (`agent/compression_facade.py`, `conversation_compression.py`)
**Two layers**:
1. **Gateway session hygiene** — 85% threshold, compacts in-place
2. **Agent ContextCompressor** — 50% (configurable), per-model overrides, failure cooldown after provider-proven overflow

**Algorithm**: Prunes old tool results first (no LLM), picks boundaries, generates structured summary via auxiliary compression model. In-place compaction keeps stable session ID.

**Manual `/compress`** on all surfaces (CLI, gateway, TUI, ACP) → `agent/conversation_compression_manual.py::compress_now` (parser for `here [N]`, focus, `--preview`, `--aggressive`).

---

## 4. Tool Registry, Schema Rewrites & Dispatch

### 4.1 Central Registry (`tools/registry.py`)
- **AST-based discovery** of `@tool` functions from `tools/` and `toolsets.py`
- **Dynamic schema rewriters** — per-tool functions that mutate JSON schema at registration
- **`check_fn` gating** — cheap reachability/opt-in check (never per-session surface); cached per process
- **`enabled_toolsets` / `disabled_toolsets`** — session-scoped surface; every model tool sent on every API call

### 4.2 Toolsets (`toolsets.py`)
```python
TOOLSETS = {
    "hermes-cli": [...], "hermes-telegram": [...], "coding": [...],
    "computer_use": [...], "skills": [...], "memory": [...], "kanban": [...],
}
_HERMES_CORE_TOOLS = frozenset({...})  # always present
```

**Resolution**: `resolve_toolset_names()` expands aliases, validates against `CONFIGURABLE_TOOLSETS`. Platform adapters save selection per platform.

### 4.3 Dispatch & Delegation
- **`delegate_task`** tool → `tools/delegate_tool.py::_run_single_child()` saves/restores `_last_resolved_tool_names` around subagent execution
- **Subagent sessions** have own tool surface; parent's tools advertised for cache parity
- **`check_fn` caching** — process-global, re-evaluated on plugin load/enable/disable

---

## 5. Session Persistence & Profile-Aware Paths

### 5.1 SessionDB (`hermes_state.py` + siblings)
- **SQLite** per-profile at `~/.hermes/profiles/<name>/state.db`
- **Facade**: `hermes_state.py`; siblings: `hermes_state_sessions.py`, `hermes_state_messages.py`, `hermes_state_tools.py`, `hermes_state_usage.py`
- **Profile isolation**: `get_hermes_home()` returns active profile's home; all paths derived from it

### 5.2 Path Resolution (`hermes_constants.py`)
```python
def get_hermes_home() -> Path:  # profile-aware
    # Resolves: HERMES_HOME env > config.yaml profile > default ~/.hermes
    # ContextVar override for multi-profile multiplexing
```

**Critical**: Never hardcode `~/.hermes` (HX001). `_get_profiles_root()` is HOME-anchored on purpose.

### 5.3 Multi-Profile Support
**One process serves many profiles**. Code running outside a turn (boot probes, eviction, tickers, deferred callbacks, RPC, thread hops, child spawns) **must bind the owning profile scope explicitly**:
- `ContextVar HERMES_HOME` override per profile
- `os.environ`, module globals, import-time values hold launch profile's scope
- Binding points: `gateway/run.py::_cron_tick_profile_homes`, `cron/scheduler.py::_profile_cron_scope`, `agent/secret_scope.py`

---

## 6. Gateway Runtime & Platform Adapters

### 6.1 Gateway Runner (`gateway/run.py` + `gateway/run_*.py`)
- **Agent caching** — reuses `AIAgent` across turns per session
- **Hygiene compaction** — 85% threshold triggers in-place compression
- **Session management** — per-profile session DB, platform message guards
- **Cron ticker** — runs every 60s from background thread per profile

### 6.2 Platform Adapters (`gateway/platforms/`)
| Adapter | Key Features |
|---------|-------------|
| **Telegram** | Long-poll/webhook, media groups, inline keyboards, bot API 7.x |
| **Discord** | Gateway + REST, slash commands, threads, ephemeral replies |
| **Slack** | Socket mode + Bolt, Block Kit, shortcuts, modals |
| **Mattermost**, **Matrix**, **IRC**, **Feishu**, **WhatsApp**, **LINE**, **Signal**, **Telegram Bot API**, ... | ~20 platforms |

**Base class** (`gateway/platforms/base.py::BasePlatformAdapter`):
- Media delivery safety (size limits, MIME validation)
- Docker path translation (host ↔ container)
- Token-lock and scoped-secret rules
- Streaming/chunked delivery with backpressure

### 6.3 Multi-Profile Gateway
- **Single process** ticks all profile homes (`run.py::_cron_tick_profile_homes`)
- **Per-home tick lock** `<home>/cron/.tick.lock` prevents duplicate ticks
- **Profile-scoped ticker** binds `_profile_cron_scope(home)` for entire tick (store, lock, env, job env, `on_session_end` flush)
- **Cron ownership** NOT gated on `gateway.multiplex_profiles` (that gates adapters only)

---

## 7. Memory & Skills Architecture

### 7.1 Memory Tool (`tools/memory_tool.py`)
**Two stores** with approval gates:
- `USER.md` — persona, preferences, communication style, personal details
- `MEMORY.md` — environment facts, tool quirks, project conventions, paths

**Operations**: `add`, `replace`, `patch`, `remove` (batched); background delete gating prevents unattended deletions.

**Approval gates**:
- Foreground: user approves each write
- Background review: `memory_notifications` mode controls surfacing
- External memory providers (`plugins/memory/`) implement `MemoryProvider` ABC

### 7.2 Skills System (`skills/`, `tools/skills_tool.py`)
**Frontmatter** (`SKILL.md`):
```yaml
---
name: skill-name
description: one-line trigger summary
version: 1
provenance: agent|user|bundled|hub
pinned: false
cron: false
references: [topic1, topic2]
---
```

**Curator** (`agent/curator.py` + `curator_backup.py`):
- Inactivity-triggered (no cron daemon)
- Automatic transitions: active → stale (14d) → archived (30d); pinned/cron-referenced protected
- LLM consolidation pass (opt-in): forks agent, builds umbrella skills, demotes to `references/`, `templates/`, `scripts/`
- **Never deletes** — only archives to `~/.hermes/skills/.archive/` (recoverable)
- Cron job skill references rewritten automatically on consolidation

**Skill Manager** (`tools/skill_manager_guards.py`):
- Read-before-write enforced: `skill_view` required before `skill_manage patch/write_file/remove_file`
- External/bundled/hub skills write-protected in background reviews
- Ledgered mutations for rollback (`hermes curator rollback`)

---

## 8. Computer Use (CUA) Architecture

### 8.1 Abstract Backend (`tools/computer_use/backend.py`)
```python
class ComputerUseBackend(ABC):
    capture(mode="som") → CaptureResult  # png_b64 + UIElement[] (SOM overlays)
    click/drag/scroll/type/key → ActionResult  # ok + structured verdict (verified, effect, escalation)
    list_apps/focus_app/set_value/wait
```

**Key types**:
- `UIElement` — 1-based SOM index, AX role, bounds, `element_token` (opaque stale-detection handle)
- `CaptureResult` — modes: `vision` (png only), `ax` (elements only), `som` (both)
- `ActionResult` — `verified` (AX read-back), `effect` (confirmed/unverifiable/suspected_noop), `escalation` (verify→escalate ladder)

### 8.2 CUA Driver Backend (`tools/computer_use/cua_backend.py`)
**MCP bridge to `cua-driver`** (Rust daemon over stdio):
- Embedded daemon management (spawn, health, restart)
- Session-per-conversation isolation
- Element token stale detection (prevents silent re-resolution)
- Delivery modes: `background` (default) | `foreground` with `bring_to_front`
- Action verification via AX read-back; escalation ladder (px → foreground → page)

### 8.3 Provider Factory (`plugins/computer_use/`)
- `ComputerUseProvider` registered via `ctx.register_computer_use_provider`
- Directory name = `computer_use.backend` value (built-in: `plugins/computer_use/cua`)
- Model-facing tool schema identical for every backend; unsupported actions return `ok=False, code="unsupported_action"`

---

## 9. Multi-Model Routing & Provider System

### 9.1 Provider Registry (`providers/__init__.py`)
**Three-layer discovery** (bundled → user plugins → pip entry points):
```python
# plugins/model-providers/<name>/__init__.py calls:
providers.register_provider(ProviderProfile(...))  # last-writer-wins
```

**ProviderProfile** holds:
- `name`, `aliases`, `auth_type` (api_key|oauth), `api_key_env_vars`
- `inference_base_url`, `hostnames`, `metadata_hostnames`
- `live_context_length(model, api_key, base_url)` — account-specific catalog
- `classify_api_error(...)` — vendor-specific error classification
- `seed_pool_credentials()` — ambient/env token exchange

### 9.2 Credential Pool (`agent/credential_pool.py`)
**Persistent multi-credential pool** for same-provider failover:
- Strategies: `fill_first` (default), `round_robin`, `random`, `least_used`
- Status: `ok` → `exhausted` (TTL cooldown) → `dead` (terminal auth failure)
- **Single-use refresh tokens** (Anthropic, Codex, xAI): serialized under cross-process auth-store flock
- **Profile isolation**: Named profiles borrow from global root; write-through on rotation
- **Model-scoped cooldowns** — provider may rate-limit one model while credential usable for siblings

### 9.3 Auxiliary Client (`agent/auxiliary_client.py`)
**Side-LLM tasks** (compression, vision, search, title generation, curator, MoA):
- **Auto chain**: main provider → OpenRouter → Nous → custom → Anthropic → direct API-key
- `auxiliary.free_only` restricts OpenRouter to `:free` SKUs
- Each task can pin `provider/model/base_url/reasoning_effort` under `auxiliary:` in config
- **Interrupt protection** for atomic tasks (compression) — gateway interrupt cannot abort mid-flight
- **Fallback chains** at credential resolution AND mid-run

### 9.4 Model Metadata & Context Resolution (`agent/model_metadata.py`)
**Resolution order** (15 steps):
1. Config override (`model.context_length`)
2. MoA aggregator resolution
3. `model_overrides` / `custom_providers` per-model
4. Endpoint-scoped metadata (Kimi on `api.kimi.com/coding`, NVIDIA NIM)
5. Persistent cache (Nous, LM Studio, Codex routes bypass)
6. Bedrock static table + live probe
7. Novita explicit endpoint
8. Custom endpoints: `/models` → local probe → Ollama `/api/show` → catalog → 256K default
9. Codex Responses routes: OAuth table with opted-in `-900k` bump (live-verified 900K vs advertised 272K)
10. Anthropic `/v1/models` (API keys only)
11. Provider-aware: profile live catalog, Nous portal, Codex OAuth, GMI, Ollama, OpenRouter live, models.dev
12. OpenRouter metadata (unknown providers; 32K underreport guard)
13. Local server probe (vLLM/Ollama num_ctx)
14. Hardcoded `DEFAULT_CONTEXT_LENGTHS` (family catch-alls)
15. 256K fallback (warned)

---

## 10. Safety, Approvals & Rate Limiting

### 10.1 Approval System (`hermes_cli/approval_*.py`)
- **Modes**: `standard` | `bounded` | `unrestricted` (bypass)
- **Terminal tool** (`tools/terminal_tool.py`) — dangerous commands gated by approval callback
- **Background review** auto-denies (`_bg_review_auto_deny`) to avoid TUI deadlock
- **Secret capture** skipped in background (`_bg_review_skip_secret`)

### 10.2 Error Classification (`agent/error_classifier.py`)
**Structured pipeline** (priority order):
1. Plugin hooks (`get_plugin_error_classification`)
2. Provider profile `classify_api_error`
3. Provider special cases (Anthropic thinking, Nous welcome tier, Codex replay, Bedrock, etc.)
4. HTTP status handlers (400, 401, 402, 403, 404, 413, 422, 429, 5xx)
5. MoA shapes
6. Structured error codes
7. Message patterns (memory ceiling → payload → role alternation → image/tool → overflow → auth → policy → model_not_found → timeout)
8. SSL (cert verify → transient)
9. Disconnect + large session → context overflow (reasoning models exempted)
10. Transport types
11. Unknown (retryable with backoff)

**FailoverReason taxonomy** (33 reasons):
- `auth`, `auth_permanent`, `billing`, `rate_limit`, `upstream_rate_limit`, `upstream_blocked`
- `overloaded`, `server_error`, `timeout`, `ssl_cert_verification`
- `context_overflow`, `payload_too_large`, `image_too_large`, `image_corrupt`
- `model_not_found`, `provider_policy_blocked`, `data_policy_denied`
- `content_policy_blocked`, `model_entitlement`, `incomplete_response`
- `format_error`, `role_alternation`, `invalid_encrypted_content`
- `multimodal_tool_content_unsupported`, `reasoning_mandatory`
- Provider-specific: `thinking_signature`, `long_context_tier`, `oauth_long_context_beta_forbidden`, `llama_cpp_grammar_pattern`

### 10.3 Rate Limiting & Retry
- **Credential pool** handles 429/401/402 via rotation with TTL cooldowns
- **Sole credential** gets brief cooldown (60s) instead of hour
- **Billing unverified** (Anthropic "out of extra usage" ambiguity) → short cooldown
- **Codex quota** early reopen probe (`_codex_quota_restored_upstream`)
- **Auxiliary retry ladder** — same-provider transient retry + provider/model fallback chain

---

## 11. Background Review System

### 11.1 Architecture (`agent/background_review.py`)
**Daemon thread** forks `AIAgent` after each turn to evaluate: "should any skill/memory be saved?"

**Cache-parity fork** (`build_cache_parity_fork`):
- Same model → inherits parent's `_cached_system_prompt`, `session_start`, tools[], reasoning_config
- Shared `session_id` for prefix warmth; `_inherited_cache_scope` resolves both cache-identity resolvers
- `_prompt_cache_fork_tag = "review"` prevents fork's compression from evicting parent's server slot
- Routed (different model) → replays compact digest (last 24 messages + synthetic digest)

**Tool whitelist** (dispatch-side only, advertised tools[] unchanged):
- `skill_view`, `skills_list`, `read_file`, `search_files` (read-only)
- `skill_manage` (patch, create, write_file, remove_file, delete with `absorbed_into`)
- `memory` (when profile memory enabled + review_memory trigger)
- Configured `extra_tools` from `auxiliary.background_review.extra_tools`

### 11.2 Triggers & Prompts
| Trigger | Prompt | Tools |
|---------|--------|-------|
| Memory nudge | `_MEMORY_REVIEW_PROMPT` | `memory` |
| Skill nudge | `_SKILL_REVIEW_PROMPT` | `skills` |
| Combined | `_COMBINED_REVIEW_PROMPT` | `memory` + `skills` |
| `/refine` (explicit) | User focus appended | Full memory op set |

**Key prompt instructions**:
- Route facts to `USER.md` (who user is) vs `MEMORY.md` (environment facts) — never both
- Ground in conversation; never infer traits from topic/tone
- Class-level skills with `references/`/`templates/`/`scripts/` — not one-session micro-skills
- Read-before-write enforced by `skill_manage`
- Never capture environment-dependent failures, negative tool claims, transient errors, one-off narratives

### 11.3 Lifecycle & Cancellation
- `prepare_background_review_run` / `finish_background_review_run` — ABA-safe run tokens
- Live turn preempts review: `cancel_background_review_for_live_turn` (2s bounded wait)
- Usage attributed to parent session via `record_auxiliary_usage`
- Fork has `_session_db = None`, `_persist_disabled = True`, `_end_session_on_close = False`

---

## 12. Cron Scheduler & Kanban

### 12.1 Cron (`cron/jobs.py` + `cron/scheduler.py` + 40+ siblings)
**Per-profile by design**: Jobs live under `~/.hermes/profiles/<name>/cron/`

**Schedule types**: duration (`30m`), every phrase (`every 2h`), 5-field cron, ISO one-shot.

**Job fields**: `skills`, `model`/`provider` overrides, `script` (file under `HERMES_HOME/scripts/`, never command), `context_from`, `workdir`, `timezone`, `grace_minutes`, multi-platform delivery.

**Hardening invariants**:
- Inactivity watchdog (default 600s idle; `HERMES_CRON_TIMEOUT` overrides; 0 = unlimited)
- Catch-up window = half period (120s–2h clamp) or `grace_minutes` (0 = never catch up)
- Pinned timezone owns entire path (compute → next_run_at write → evaluation)
- Every recurring occurrence accounted: `tick()` advances `next_run_at` BEFORE dispatch (at-most-once)
- Per-home tick lock prevents duplicate ticks across processes
- Headless ticks **refuse** agent jobs (never spawn unmanaged daemon)
- Ticker binds each profile's scope for entire tick (store, lock, job env, flush)

**External worker**: Restart-safe boot pins checkout + committed generation's `site-packages` on `PYTHONPATH`; child activates PM lease before first third-party import.

### 12.2 Kanban (`plugins/kanban/`, `hermes_cli/kanban.py`, `tools/kanban_tools.py`)
**Durable SQLite-backed board** for multi-agent collaboration:
- Dispatcher: long-lived loop (60s default) reclaims stale claims, promotes ready tasks, atomically claims, spawns assigned profiles
- Runs inside gateway by default (`kanban.dispatch_in_gateway: true`)
- **Board** = hard boundary (workers get `HERMES_KANBAN_BOARD` pinned); **tenant** = soft namespace
- Failure limit (default 2) auto-blocks task; terminal provider exit (78) trips on first attempt
- Notifications leave through task's owning profile (never multiplexer's launch adapter)
- Prompt injection gates on **ownership** (via `owned_kanban_task()`), not tool access

---

## 13. Plugin System & Extension Points

### 13.1 Plugin Kinds
| Kind | Discovery | Contract |
|------|-----------|----------|
| General | `PluginManager` (later-wins) | `register(ctx)` — hooks, tools, CLI commands, locales |
| Memory provider | `plugins/memory/<name>/` (bundled-first) | `MemoryProvider` ABC — `sync_turn`, `prefetch`, `shutdown`, `post_setup` |
| Model provider | `plugins/model-providers/<name>/` (lazy, last-writer-wins) | `ProviderProfile` — live catalog, error classification, pool seeding |
| Context engine | `plugins/context_engine/` | `ContextEngine` ABC |
| Image gen | `plugins/image_gen/` | `ImageGenProvider` ABC |
| Delegation | `plugins/delegation/` | `DelegationProvider` ABC |
| Platform adapter | `plugins/platforms/<name>/adapter.py` | `BasePlatformAdapter` |

### 13.2 Plugin Catalog (`plugin-catalog/`)
**Only discovery system** for out-of-tree plugins:
- One YAML per entry, 40-hex SHA pin mandatory
- Human-merged via PR; `plugin-catalog-ci.yml` validates at pin
- `removed.yaml` kill list — every install path refuses matches
- Provenance in `.install-metadata.json` (never in tree)

### 13.3 Isolation Modes
- `in_process` (default) — imports user plugins into Hermes
- `host` — runs non-bundled plugins in per-profile host process (`plugin_host.py` + `plugin_host_child.py` + JSON-RPC wire)
- **HOST_UNSUPPORTED_CTX_METHODS** table defines what cannot cross (live gateway/adapter objects)

### 13.4 Compatibility Contract
- Hook payload data added as keyword fields; callbacks signature-inspected
- Never remove/rename `PluginContext` methods; new params optional
- Unknown manifest fields ignored
- New provider methods get defaults; optional callback kwargs signature-inspected
- Deprecations: once-per-process warning, ≥2 minor releases before removal

---

## 14. Testing Architecture

### 14.1 Test Organization
```
tests/
├── agent/           # Loop/phase tests (patch where production reads)
├── cron/            # Schedule parsing, catch-up (pure functions as data)
├── hermes_cli/      # CLI subcommands, kanban, config
├── plugins/         # Load through real discovery with temp HERMES_HOME
├── tools/           # Tool implementations, registry, kanban
└── gateway/         # Platform adapters, message guards
```

### 14.2 Test Principles
- **Behaviour contracts**, never change-detectors or source-reading tests
- Host-specific behaviour tested on that host with `@pytest.mark.platforms(...)` — never fake `sys.platform`
- Tests never write to `~/.hermes/`
- E2E with real imports against temp `HERMES_HOME` for resolution, config, security, I/O
- Time-based tests use loose bounds (≥2s) and event sync
- `python scripts/run_tests.sh` — never bare `pytest`

---

## 15. Saturnite Integration Assessment

### 15.1 Current Extension Points for Saturnite

| Saturnite Capability | Hermes Integration Point | Effort |
|---------------------|-------------------------|--------|
| **Saturnite skills** (`.stn` files) | `plugins/skills/` or extend `tools/skills_tool.py` to compile `.stn` → `SKILL.md` | Medium |
| **Saturnite memory** (structured facts) | Extend `tools/memory_tool.py` with Saturnite backend; or `plugins/memory/saturnite/` | Medium |
| **Saturnite tools** (compiled WASM/native) | `tools/registry.py` dynamic schema rewriters + `check_fn` for Saturnite tool discovery | Low |
| **Saturnite workflows** (declarative pipelines) | `cron/jobs.py` script field + `plugins/cron_providers/saturnite/` | Medium |
| **Saturnite types** (shared schemas) | `agent/model_metadata.py` context resolution for Saturnite model IDs | Low |
| **Saturnite agent loops** | `agent/conversation_loop.py` phase siblings for Saturnite-specific turn phases | High |

### 15.2 Compatibility Gaps
| Gap | Impact | Mitigation |
|-----|--------|------------|
| No Saturnite parser in core | Cannot natively load `.stn` skills | Ship as plugin with `skill_manage` compilation step |
| No WASM runtime | Saturnite tools need native/WASM execution | Add `tools/environments/saturnite/` backend |
| Memory format mismatch | `MEMORY.md`/`USER.md` are Markdown | Saturnite memory provider writes both formats |
| Prompt cache invalidation | Saturnite skill compilation changes system prompt | Compile at skill install time (deferred to next session) |

---

## 16. Feature Compatibility Matrix

| Feature | CLI | Gateway | TUI | Desktop | Cron | Background Review |
|---------|-----|---------|-----|---------|------|-------------------|
| Prompt caching | ✅ | ✅ | ✅ | ✅ | N/A | ✅ (fork parity) |
| Multi-profile | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ (scope copied) |
| Memory tool | ✅ | ✅ | ✅ | ✅ | ❌ (skip_memory) | ✅ (triggered) |
| Skills | ✅ | ✅ | ✅ | ✅ | ✅ (per-job) | ✅ (triggered) |
| Computer use | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ (no tools) |
| Delegation | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Cron jobs | ✅ | ✅ (ticker) | ❌ | ✅ (backend) | ✅ | ❌ |
| Kanban | ✅ | ✅ (dispatcher) | ❌ | ✅ | ✅ | ❌ |
| Context compression | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Auxiliary models | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Plugin hot-reload | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## 17. Development Roadmap & Implementation Prompt Backlog

### Phase 1: Saturnite Skill Integration (2-3 weeks)
```markdown
1. Create `plugins/skills/saturnite/` with:
   - `saturnite_skill_provider.py` implementing skill compilation (.stn → SKILL.md + refs)
   - `register(ctx)` hook for `skill_manage action=compile_saturnite`
   - `.stn` file watcher for hot-reload (opt-in)

2. Extend `tools/skill_manager_guards.py`:
   - Recognize `.stn` source files in read-before-write
   - Compile on `skill_manage action=patch` for Saturnite skills

3. Add `hermes skill compile <name>` CLI command (skill mixin)
```

### Phase 2: Saturnite Memory Provider (2 weeks)
```markdown
1. Create `plugins/memory/saturnite/` implementing `MemoryProvider` ABC:
   - `sync_turn()` — extract structured facts via Saturnite schema
   - `prefetch()` — pre-load relevant facts for session
   - `shutdown()` — flush pending writes
   - `post_setup()` — create Saturnite DB at `HERMES_HOME/memory/saturnite.db`

2. Dual-write to `MEMORY.md`/`USER.md` for backward compatibility
3. Config: `memory.provider: saturnite` + `memory.saturnite.schema: <path>`
```

### Phase 3: Saturnite Tool Runtime (3-4 weeks)
```markdown
1. Create `tools/environments/saturnite/` backend:
   - `SaturniteBackend` implementing `ComputerUseBackend` for Saturnite-driven automation
   - WASM runtime for portable tool execution
   - Schema-driven tool discovery from Saturnite modules

2. Extend `tools/registry.py`:
   - Saturnite tool schema rewriter (generates JSON Schema from Saturnite types)
   - `check_fn` for Saturnite tool availability (WASM runtime present)

3. Toolset: `saturnite` in `toolsets.py` + platform enablement
```

### Phase 4: Saturnite Cron Provider (1-2 weeks)
```markdown
1. Create `plugins/cron_providers/saturnite/`:
   - `SaturniteCronProvider` — jobs defined as Saturnite workflows
   - `verify.py` — schema validation at job creation
   - Execution via Saturnite runtime (not shell)

2. Job field: `saturnite_workflow: <path>` instead of `script`
```

### Phase 5: Saturnite Model Provider (2 weeks)
```markdown
1. Create `plugins/model-providers/saturnite/`:
   - `ProviderProfile` for Saturnite-compiled models (local inference)
   - `live_context_length()` — reads from compiled model metadata
   - `seed_pool_credentials()` — none (local)
   - `classify_api_error()` — Saturnite-specific error shapes

2. Model ID format: `saturnite:<module>::<model>`
```

### Phase 6: Self-Improving Agent Loop (4-6 weeks)
```markdown
1. Extend `agent/background_review.py`:
   - Saturnite skill synthesis prompt (generate `.stn` from conversation)
   - `skill_manage action=create_saturnite` for new compiled skills

2. Extend `agent/curator.py`:
   - Saturnite-aware consolidation (merge `.stn` modules, not just Markdown)
   - Type-safe reference migration

3. Add `auxiliary.saturnite_synthesis` task for dedicated model
```

### Phase 7: Saturnite Dashboard & TUI (3-4 weeks)
```markdown
1. `plugins/dashboard/saturnite/` — skill graph visualization, memory explorer
2. `ui-tui/src/components/SaturniteSkillBrowser.tsx` — interactive .stn browser
3. `apps/desktop/src/components/SaturniteWorkflowBuilder.tsx` — visual cron builder
```

---

## 18. Critical Invariants for Saturnite Integration

| Invariant | Current Enforcement | Saturnite Requirement |
|-----------|-------------------|----------------------|
| Prompt cache byte-stable | System prompt never rebuilt mid-conversation | Compile `.stn` at install time; defer to next session |
| Profile isolation | `get_hermes_home()` + ContextVar binding | Saturnite DB per-profile at `HERMES_HOME/memory/` |
| No core tool bloat | Footprint ladder: CLI+skill → service tool → plugin → MCP → core | Saturnite tools as plugin + toolset, not core |
| Write-path ledgering | `skill_manage` enforces read-before-write + ledger | Saturnite compilation must be ledgered |
| Background fork cache parity | `_cached_system_prompt` + `_inherited_cache_scope` inherited | Saturnite fork must inherit same compiled artifacts |
| Single-use token safety | Cross-process flock for Anthropic/Codex/xAI | Saturnite local models exempt; remote endpoints use pool |

---

## 19. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Saturnite compilation breaks prompt cache | Medium | High | Compile at skill install (`--now` opt-in); never mid-conversation |
| Saturnite DB schema migration | High | Medium | Versioned migrations in `post_setup()`; backward-compatible reads |
| WASM runtime not available on all platforms | Medium | Medium | Graceful degradation: `check_fn` returns false; toolset disabled |
| Background review generates invalid `.stn` | Medium | High | Schema validation in `skill_manage create_saturnite`; dry-run first |
| Profile leakage via Saturnite shared state | Low | Critical | All Saturnite paths use `get_hermes_home()`; no global singletons |

---

## 20. Conclusion

The Hermes vanilla architecture provides a **solid, well-factored foundation** for Saturnite integration. Its facade/sibling pattern, strict prompt-caching invariants, profile-aware multiplexing, and plugin/skill extension points align well with Saturnite's compilation model and type-safe workflows.

**Recommended approach**: Integrate Saturnite at the **edges** (plugins, toolsets, skills) rather than the core, respecting the narrow-waist philosophy. The background review system and curator provide natural entry points for Saturnite's self-improving capabilities.

**Next step**: Begin with Phase 1 (Saturnite Skill Provider plugin) to establish the `.stn` → `SKILL.md` compilation pipeline without touching core files.