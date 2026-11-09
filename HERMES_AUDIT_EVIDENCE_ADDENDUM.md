# HERMES_AUDIT_EVIDENCE_ADDENDUM.md

Read-only source investigation of `hermes-agent` (commit `7cb4f163`, branch `master`).
Companion to the already-completed `HERMES_VANILLA_AUDIT_5fcafaa.md`. No source files,
configuration, or Git state were modified.

Saturnite path referenced by the user: `C:\Users\atimo\Saturnite` — not inspected;
no claims about Saturnite's capabilities are made beyond what the Hermes source
actually requires for interop.

## Evidence status key

Each claim in §1 carries one of these labels:

- **Verified implementation** — the behavior is present in source at the cited lines.
- **Partial implementation** — present but gated, incomplete, or not yet wired through all callers.
- **Documentation-only** — described in docstrings/comments but not fully realized in code.
- **Inference** — derived from reading the code; no direct test or runtime observation.
- **Unknown / unverified** — no evidence found in source; explicitly not assumed.
# 1. Source-level evidence

## 1.1 Complete inference request paths across every execution subsystem

### 1.1.1 Main conversation-turn inference (chat_completions / codex_responses)

**Verified implementation.** Every model inference request in a user turn funnels through
the turn loop in `agent/conversation_loop.py::run_conversation`. The loop iterates:
model API call → tool round → next model call → … until `max_iterations` or budget
exhaustion.

Per-attempt request assembly: `agent/turn_api_request.py::build_api_request`
[agent/turn_api_request.py:177-216] builds `api_kwargs`, runs LLM request middleware,
fires `pre_api_request` hooks, and (for `provider == "moa"`) attaches `_moa_prepared_request`.

The actual provider call: `agent/turn_api_call.py::perform_api_call`
[agent/turn_api_call.py:72-294] decides streaming (`_should_stream`, line 46), issues
the request through `agent.client.chat.completions.create` (or the Codex responses
adapter), brackets the call with `_model_request_active`, and handles the
response-vs-redirect crossing check. Interrupts mid-call go through
`handle_api_interrupt` [agent/turn_api_call.py:177-231].

Response intake: `agent/turn_response_intake.py::normalize_model_response`
[agent/turn_response_intake.py] normalizes the raw provider response into an assistant
message, fires `post_api_request` hooks, relays reasoning to the progress callback,
and applies the incomplete-scratchpad / Codex-incomplete continuation guards
(lines 207-240).

Tool execution after a response with `tool_calls`: `agent/turn_tool_round.py::run_tool_round`
[agent/turn_tool_round.py:49-] validates, deduplicates, caps, persists-before-execute,
then dispatches via `model_tools.py::handle_function_call`.

**Relationship to other components:** The turn loop is the single chokepoint for
foreground inference. Background forks (`build_cache_parity_fork`) construct a *new*
`AIAgent` and run the same `run_conversation` path, so they share this entire
subsystem but under a detached session DB (no persistence writes).

### 1.1.2 Auxiliary (side-task) inference path

**Verified implementation.** `agent/auxiliary_client.py` is the shared auxiliary client
router used by compression, search, vision, title generation, MoA advisors, and
background-review forks. Its module docstring [agent/auxiliary_client.py:1-9] describes
the text auto-chain: main provider+model → OpenRouter → Nous Portal → custom endpoint
→ native Anthropic → direct API-key providers → None. Vision auto-chain: main provider
(if a supported vision backend) → OpenRouter → Nous → Anthropic → custom.

`call_llm()` is the entry point. HTTP 402 falls through the chain. Codex OAuth is in
neither chain (main provider or explicit `auxiliary.<task>.provider` only).

`aux_probe_mode()` [agent/auxiliary_client.py:114-] returns `_AuxProbeClientStub`
instead of real SDK clients so `check_fn`s can resolve availability without importing
`openai` (~240 ms cold) or building httpx/SSL clients. Stubs are never cached.

**Relationship to other components:** Auxiliary calls deliberately do NOT fire the main
loop's `pre_api_request` / `post_api_request` events [agent/AGENTS.md:102-105].

### 1.1.3 MoA (Mixture-of-Agents) inference path

**Verified implementation.** `agent/moa_loop.py` is the MoA runtime for `/moa` turns.
The slash command marks one user turn as MoA-enabled; the normal agent loop still owns
tool calling and turn termination, while this module gathers reference-model context
before each model iteration [agent/moa_loop.py:1-6].

Key functions:
- `_resolve_preset_cached(preset_name)` [agent/moa_loop.py:124-143] — cached per
  config-file signature; skips full `resolve_moa_preset` validation on every `create()`.
- `_slot_runtime(slot)` [agent/moa_loop.py:249-281] — slot → `call_llm` kwargs with the
  provider's real `api_mode`/`base_url`/`api_key`. Cached per
  `(hermes_home_key(), provider, model)` with a 300s TTL. Profile-scoped via
  `hermes_home_key()` so two multiplexed profiles sharing (provider, model) with
  different accounts do not collide [agent/moa_loop.py:257-260].
- `_aggregator_reasoning_config(aggregator)` [agent/moa_loop.py:232-246] — slot >
  per-model > global reasoning config; references deliberately do NOT fall back to
  global.

Reference outputs are redacted (`_redact_reference_text`, line 58) for PII classes the
central redactor leaves alone (emails, formatted phones). Privacy filter modes:
`'' | display | full` [agent/moa_loop.py:32-47].

`agent/moa_alternation.py` handles strict-chat-template 400s: on a
`FailoverReason.role_alternation` rejection, the request is retried ONCE with adjacent
same-role messages merged (`merge_same_role_messages`, line 32), and the destination
key `(route, model)` is remembered for the session so later iterations pre-merge
[agent/moa_alternation.py:1-14, 53-67].

**Partial implementation:** MoA preset switching used to re-resolve config + preset +
every slot runtime on each `create()` call (5–30s frozen latency); the cold-start
caches (`_preset_cache`, `_runtime_cache`) mitigate this [agent/moa_loop.py:116-153].

### 1.1.4 Background-review fork inference

**Verified implementation.** `agent/background_review.py::build_cache_parity_fork`
[agent/background_review.py:979-1000] constructs a detached `AIAgent` fork with
warm prompt-cache parity: same runtime/credentials as parent, byte-identical system
prompt / tools[] / reasoning config on the same-model path, shared `session_id` for
prefix warmth, full persistence detachment (no state.db writes, rotation, or external
memory providers; in-place-only compaction). Returns `(fork_agent, runtime_dict,
routed)`. Routed forks (different model) are cache-cold and replay a digest.

The fork is spawned by `run_agent.py::_spawn_background_review_now`
[run_agent.py:785-823] via `threading.Thread` under `propagate_context_to_thread`
(carries the active profile into the review thread). The fork runs the normal
`run_conversation` path with `skip_memory=True`.

**Relationship to other components:** The fork's usage is attributed back to the
parent session via `_record_review_usage_to_parent`
[agent/background_review.py:787-], which writes only `session_model_usage` — never the
transcript or `sessions` row.

### 1.1.5 All inference dispatch paths — complete inventory

| Path | File:Function | Lines | Notes |
|---|---|---|---|
| Foreground turn API call | `agent/turn_api_call.py::perform_api_call` | 72-294 | Primary model call per turn iteration |
| Nous rate-limit guard (skip attempt) | `agent/turn_api_call.py::nous_rate_limit_guard` | 232-294 | Cross-session Nous Portal rate limit |
| Request assembly + middleware | `agent/turn_api_request.py::build_api_request` | 177-216 | Per-attempt `api_kwargs` build |
| Response intake | `agent/turn_response_intake.py::normalize_model_response` | — | Normalize + hooks + guards |
| Auxiliary side-task LLM | `agent/auxiliary_client.py::call_llm` | — | Compression, search, vision, titles, MoA advisors |
| MoA reference + aggregator | `agent/moa_loop.py` | — | Reference fan-out, aggregator synthesis |
| Background-review fork | `agent/background_review.py::build_cache_parity_fork` | 979-1000 | Detached fork, same runtime |
| Codex incomplete continuation | `agent/turn_response_intake.py` | 226-240 | `continue_codex_incomplete` |
| Incomplete scratchpad retry | `agent/turn_response_intake.py` | 207-223 | Up to 2 retries, then partial |

**Conclusion:** There is no single shared inference scheduler today. Every path above
constructs its own client and issues requests independently. Credential pool selection
happens inside `resolve_provider_client` (auxiliary) and inside `AIAgent.__init__`
/ the fallback chain (foreground). This is the gap a shared scheduler would fill.

## 1.2 Credential-pool selection, quota cooldowns, and retry handling

### 1.2.1 Credential pool data model

**Verified implementation.** `agent/credential_pool.py` defines `PooledCredential`
[agent/credential_pool.py:209-272] with fields: `provider`, `id`, `label`, `auth_type`,
`priority`, `source`, `access_token`, `refresh_token`, `last_status`,
`last_status_at`, `last_error_code`, `last_error_reason`, `last_error_message`,
`last_error_reset_at`, `status_cleared_at`, `base_url`, `expires_at`, `expires_at_ms`,
`last_refresh`, `inference_base_url`, `agent_key`, `agent_key_expires_at`,
`request_count`, `model_cooldowns` (dict[str, float]), `extra`.

Status constants: `STATUS_OK = "ok"` [line 81], `STATUS_EXHAUSTED = "exhausted"`
[line 82], `STATUS_DEAD = "dead"` [line 87]. DEAD entries are excluded from rotation
unconditionally and only clear on an explicit write-side sync.

`_CLEAR_STATUS` [line 190-198] clears `last_status`, `last_status_at`,
`last_error_code`, `last_error_reason`, `last_error_message`, `last_error_reset_at`,
plus sets `last_status: STATUS_OK`. `_MARK_OK` adds `last_status: STATUS_OK`.

### 1.2.2 Credential-pool selection / rotation

**Verified implementation.** Pool rotation is performed by `CredentialPool`
(mixin classes `CredentialPoolAdminMixin` in `credential_pool_admin.py`,
`CredentialPoolModelCooldownMixin` in `credential_pool_model_cooldowns.py`). The pool
persists classified failure semantics to JSON. Selection iterates entries by `priority`,
skipping `STATUS_DEAD` and entries whose `last_status == STATUS_EXHAUSTED` past their
cooldown (`_exhausted_until`, `credential_pool.py:442-454`).

Model-scoped cooldowns: `CredentialPoolModelCooldownMixin.token_is_blocked(token,
model=)` [credential_pool_model_cooldowns.py:63-74] checks whether a pool cooldown
blocks a token for a model. `_cool_down_model` [credential_pool_model_cooldowns.py:92-119]
records a model cooldown on an entry and every sibling sharing its `runtime_api_key`.
`model_entitlement` failures bench for `MODEL_ENTITLEMENT_BENCH_SECONDS = 365*24*60*60`
[credential_pool_model_cooldowns.py:19] until an explicit reset clears `model_cooldowns`.

`limit_state(models)` [credential_pool_model_cooldowns.py:121-145] reports
`{"scope": "account", "resets_at": epoch}` when every live entry is benched
credential-wide, else `{"scope": "models", "models": {model: epoch}}` for model-scoped
cooldowns. Read-only; never clears or persists.

### 1.2.3 Quota cooldowns and Retry-After handling

**Verified implementation.** `agent/fallback_cooldown.py::_arm_rate_limit_cooldown`
[agent/fallback_cooldown.py:45-76] arms the primary cooldown until the provider-declared
`reset_at`, or uses exponential backoff (60s → 2m → … → 4h). Only arms when leaving the
primary; chain-switching from an active fallback does not re-arm. `switch_deferred_by_reset`
[agent/fallback_cooldown.py:24-42] opts into `fallback.min_switch_reset_seconds` (default
0 = off): when the primary's rate limit reopens sooner than N seconds, the fallback walk
is skipped and the retry loop's own backoff rides out the window.

`agent/retry_utils.py`:
- `parse_retry_after_seconds(value_or_headers)` [line 30-64] — parses `Retry-After`
  (numeric / HTTP-date) or headers mapping into seconds, clamped at 0.0.
- `provider_retry_after_seconds(error)` [line 185-195] — provider-declared cooldown:
  `Retry-After` header, else `retry_after` body field (top-level or nested under
  `error`). None when absent/unparseable/zero.
- `jittered_backoff` [line ~120-134] — jittered delays to prevent thundering-herd.
- `adaptive_rate_limit_backoff` [line 155-167] — Z.AI Coding GLM-5.2 overload keeps
  short retries then 30→60→90→120s.

`agent/credential_pool.py::_normalize_error_context` [line 418-439] extracts `reset_at`
from error context (`reset_at` / `resets_at` / `retry_until`) or parses it from the
message body via `reset_delay_from_message`.

`agent/nous_rate_guard.py` is the cross-session rate-limit guard for Nous Portal [line 1-80].
Writes rate-limit state to a shared file (`nous.json` / `nous-anonymous.json` under
`HERMES_HOME/rate_limits/`) so all sessions (CLI, gateway, cron, auxiliary) can check
whether Nous Portal is rate-limited before making requests. Without it each 429 fans out
into up to 9 calls per turn (3 SDK retries × 3 Hermes retries), all counted against RPH.
`record_nous_rate_limit` [line 60-80] takes reset from `error_context["reset_at"]`,
then headers, then `default_cooldown` (300s).

### 1.2.4 Error classification for failover

**Verified implementation.** `agent/error_classifier.py` defines `FailoverReason` enum
[line 34-67]: `auth`, `auth_permanent`, `billing`, `rate_limit`, `upstream_rate_limit`,
`upstream_blocked`, `overloaded`, `server_error`, `timeout`, `ssl_cert_verification`,
`context_overflow`, `payload_too_large`, `image_too_large`, `image_corrupt`,
`model_not_found`, `provider_policy_blocked`, `data_policy_denied`,
`content_policy_blocked`, `model_entitlement`, `incomplete_response`, `format_error`,
`role_alternation`, `invalid_encrypted_content`,
`multimodal_tool_content_unsupported`, `reasoning_mandatory`, `thinking_signature`,
`long_context_tier`, `oauth_long_context_beta_forbidden`, `llama_cpp_grammar_pattern`,
`unknown`.

`ClassifiedError` [line 70-94] carries `reason`, `status_code`, `provider`, `model`,
`message`, `error_context`, and recovery hints `retryable`, `should_compress`,
`should_rotate_credential`, `should_fallback`.

### 1.2.5 Entitlement rejection

**Verified implementation.** `agent/fallback_cooldown.py::_mark_entitlement_rejected_model`
[line 79-117] records a Codex ChatGPT-account 400 that rejects the current model.
Pool rotation runs first; this runs only when no pool entry is left for the model. The
`(provider, model)` pair is treated as dead for the session. `_is_entitlement_rejected`
[line 120-128] checks the set, also trying `normalize_model_for_provider`.

**What should remain unchanged:** The credential pool's persistence format, the
`model_cooldowns` per-entry dict, the `_exhausted_ttl` sole-credential short bench
(60s vs 1h default), and the `status_cleared_at` reset marker. These are load-bearing
for cross-process pool consistency (#89415, #70111). A shared scheduler should read
from, not replace, the pool.

## 1.3 Background-review creation, execution, cancellation, and state isolation

### 1.3.1 Creation

**Verified implementation.** `run_agent.py::_spawn_background_review`
[run_agent.py:752-783] is the post-turn review entry point. It decides WHEN then spawns.
Gates:
- Not explicit and no focus and `self._delegate_depth > 0` → return (delegated children
  don't auto-review).
- Not explicit and no focus: reads `load_background_review_settings()`;
  if not enabled → return (`enabled: false` stops only automatic forks; `/refine`
  explicit bypasses).
- If focus is None, not explicit, and `_review_should_defer(self, task_cfg)` → enqueue
  on `agent.review_idle_queue::QUEUE` (idle deferral for managed local runtime) and
  return. Otherwise `self._spawn_background_review_now(**kwargs)`.

`run_agent.py::_spawn_background_review_now` [run_agent.py:785-823] spawns the thread:
`prepare_background_review_run(self)` installs a unique run token; `spawn_background_review_thread`
builds the target; `threading.Thread(target=propagate_context_to_thread(_target_with_requeue),
daemon=True, name="bg-review").start()`.

### 1.3.2 Execution

**Verified implementation.** `agent/background_review.py::spawn_background_review_thread`
builds the review target and prompt. `build_cache_parity_fork`
[agent/background_review.py:979-1000] constructs the detached fork. The review agent
inherits the parent's live runtime (`_resolve_review_runtime`, line 253-). Default
(auto/unset) = parent's live runtime with `routed=False`; when
`auxiliary.background_review.{provider,model}` names a different concrete model,
`routed=True` and that runtime is resolved.

The review fork runs the normal `run_conversation` loop with the review prompts
(`_MEMORY_REVIEW_PROMPT`, `_SKILL_REVIEW_PROMPT`, `_COMBINED_REVIEW_PROMPT`). It uses
`skip_memory=True` and `_persist_disabled` so it writes only to memory/skill stores,
never to the transcript.

Input token budget: `_review_input_token_budget` [agent/background_review.py:215-225]
aggregates `max_input_tokens` from config, else derives 75% of the review fork's
resolved context window capped at a 600k ceiling.

### 1.3.3 Cancellation

**Verified implementation.** `agent/background_review.py::_BackgroundReviewRun`
[line 28-61] is the per-review cancellation and request-completion handshake:
`cancel_requested` (threading.Event), `request_done` (threading.Event), lock,
`_review_agent`, `_request_finished`, `_cancel_dispatched`.

`cancel_background_review_for_live_turn(agent, message, tool_reason)` [line 129-168]
cancels the current review and awaits its request-phase acknowledgement with a bounded
2.0s deadline (`_BACKGROUND_REVIEW_CANCEL_TIMEOUT_SECONDS`). Past the deadline, warns
and lets the live turn proceed — self-improvement work must never block a user-facing
turn. Also used for session teardown/interrupt (`tui_gateway.session_lifecycle::
_finalize_session`, `_interrupt_session_turn`).

`_interrupt_background_review` [line 102-126] requests abort off-thread via
`request_hard_interrupt` so a wedged abort hook cannot stall the live turn.

`prepare_background_review_run` [line 75-89] installs a unique run token on the parent
before `Thread.start()`; returns None if a current run is not done. `finish_background_review_run`
[line 92-] latches request completion once and clears `agent._background_review_run`.

### 1.3.4 State isolation

**Verified implementation.** The review fork has `_session_db = None`, so
`conversation_loop`'s DB-gated accounting never sees its calls; usage is routed through
the aux-accounting chokepoint which writes only `session_model_usage`
[agent/background_review.py:791-794]. `_inherit_parent_tool_surface` [line 968-975]
deep-copies the parent's exact `tools[]` and freezes the snapshot generation at
`_FROZEN_TOOL_SNAPSHOT_GENERATION = 2_147_483_647` so the compaction-boundary refresh
cannot drop inherited provider/plugin tools.

The fork inherits `parent_session_id = agent.session_id`. Conversation-id scope:
`agent/prompt_cache_scope.py::conversation_id` [line 40-66] maps the physical session id
to the compression-lineage root (not `get_conversation_root`, which would collapse
/branch children and delegate trees). `declared_conversation_scope` [line 109-]
returns the host-declared `gwk_<sha256[:24]>` scope or None; None for a
background-review fork (`_persist_disabled`) — fail closed rather than merge a fork onto
its parent's key. The one sanctioned exception is a same-model cache-parity fork
(#109964): `build_cache_parity_fork` stamps the parent's already-resolved scope.

**Partial implementation:** Idle deferral (`agent/review_idle_queue.py`) is in-memory
best-effort; aged-out items dispatch after `defer_max_age_s` (default 30 min) regardless
of idleness. One slot per session, newest snapshot wins (coalescing is dedup, not loss).

## 1.4 Auxiliary-model routing and MoA execution

### 1.4.1 Auxiliary routing

**Verified implementation.** `agent/auxiliary_client.py` module docstring [line 1-9]
describes the routing chains. `call_llm()` is the single entry point. `resolve_provider_client`
(called from `agent/agent_init.py::_routed_client_kwargs` line 756-758) resolves provider
clients for MoA presets. `_slot_runtime` in `moa_loop.py` [line 249-281] resolves per-slot
runtime with profile-scoped caching.

**Partial implementation:** The auxiliary chain is hardcoded in `call_llm()`; there is no
pluggable auxiliary router. `auxiliary.free_only` restricts the OpenRouter lane to `:free`
SKUs. Codex OAuth is explicitly excluded from both chains.

### 1.4.2 MoA execution

**Verified implementation.** As described in §1.1.3: `agent/moa_loop.py` gathers reference
model context before each model iteration; the normal agent loop owns tool calling and
turn termination. Reference slots call `call_llm` in parallel (bounded by
`_MAX_REFERENCE_WORKERS = 8` [agent/moa_loop.py:153]). The aggregator synthesizes
guidance from reference outputs. Role-alternation 400s are handled reactively per
destination [agent/moa_alternation.py].

## 1.5 Personality and prompt construction, including prompt-cache invariants

### 1.5.1 System prompt assembly

**Verified implementation.** `agent/system_prompt.py` assembles the system prompt in
three tiers joined with `\n\n`: `stable` (identity, guidance, env hints, coding brief,
platform hints), `context` (workspace snapshot, caller `system_message`, context files),
and `volatile` (skills index, memory, USER.md, external memory provider, timestamp line)
[agent/system_prompt.py:3-8]. Built once per session and reused across turns; only
context compression triggers a rebuild, so the upstream prefix cache stays warm.

`agent/prompt_builder.py` holds the stateless assembly pieces: `DEFAULT_AGENT_IDENTITY`,
`PLATFORM_HINTS`, `SKILLS_GUIDANCE`, `KANBAN_GUIDANCE`, `TOOL_USE_ENFORCEMENT_GUIDANCE`,
etc. `hud_surface_note` [line 615-654] is a per-turn note for desktop HUD mode — rides
the model-bound message, never the byte-stable system prompt.

`DEVELOPER_ROLE_MODELS = ("gpt-5", "codex")` [agent/prompt_builder.py:659] — models
whose system prompt is sent as the `developer` role.

### 1.5.2 Prompt caching

**Verified implementation.** `agent/prompt_caching.py` implements Anthropic prompt
caching: 4 cache_control breakpoints by default (static system prefix, end of system
prompt, last 2 non-system messages; without static prefix: one system breakpoint plus
last 3 messages). All markers share one TTL (5m or 1h) [line 1-6]. `PromptCachePlan`
[line 15-21] holds request-local message and tool sections with cache markers.

`is_one_shot_request` [line 35-47]: True for requests no later call can read back from
cache (no tools, no assistant/tool turns, at most one user turn) — compression summaries,
titles, MoA synthesis. A marker there only buys a cache write nothing reads.

`agent/prompt_cache_scope.py` derives the rotation-stable logical cache scope:
`conversation_id(agent)` [line 40-66] → compression-lineage root of `agent.session_id`;
`declared_conversation_scope(agent)` [line 109-] → host-declared `gwk_<sha256[:24]>`.

`agent/prompt_refresh.py` adopts an operator's prompt-refresh request on a continuing
session's next turn: `hermes sessions refresh-prompts` records a refresh epoch in the
profile's state.db; at the start of the next turn `stored_prompt_refresh_epoch`
[line 50-56] compares the requested epoch with the applied epoch and rebuilds once
through the normal builder if older. One prefix-cache break per request [line 1-13].
Nothing watches files; nothing changes mid-turn.

### 1.5.3 Prompt-cache invariant

**Verified implementation.** The invariant is stated in `agent/AGENTS.md` [line 55-61]:
"Prompt caching must not break. Never alter past context, change toolsets, reload
memories, or rebuild the system prompt mid-conversation. The system prompt is byte-stable
for the life of a conversation; the ONLY context mutation is compression."

`run_agent.py::_restore_or_build_system_prompt` [run_agent.py:802-] restores the cached
system prompt from the session DB or builds it fresh. Row states `missing`/`null`/
`empty`/`present` are logged. `agent/prompt_refresh.py` [line 1-13] is the only sanctioned
mid-session prompt change, and it breaks the cache exactly once per request.

**Inference:** A learned preference profile that mutates the system prompt mid-turn would
violate this invariant. It must be deferred to a session boundary (`/new`) or applied via
the prompt-refresh epoch mechanism.

## 1.6 Memory approval and mutation mechanisms

### 1.6.1 Memory manager

**Verified implementation.** `agent/memory_manager.py::MemoryManager` fans the agent's
memory hooks out to registered providers [line 1-4]. The builtin provider is always
allowed; only ONE external plugin provider may be registered at a time.

Lifecycle: `initialize` → `system_prompt_block` / `prefetch` / `sync_turn` per turn →
tool dispatch → `shutdown`, plus optional `on_*` hooks. `_SYNC_DRAIN_TIMEOUT_S = 5.0`
[line 41]; `_MAX_STUCK_CALLS = 4` [line 51]; `_MAX_INFLIGHT_CALLS = 16` [line 57].

`on_pre_compress` [agent/memory_manager.py:~700-757] gathers provider memory blocks
before compression. v2 checkpoint API (`PRE_COMPRESS_CHECKPOINT_API_VERSION = 2`) is
fail-closed: `require_checkpoint=True` raises `RuntimeError` if no active provider
completed the checkpoint.

`on_memory_write` [line 768-785] notifies external providers when the built-in memory
tool writes (skips builtin, the source). Redacts for egress via `agent.redact`.

### 1.6.2 Memory provider ABC

**Verified implementation.** `agent/memory_provider.py::MemoryProvider` [line 1-260]
defines the plugin contract: `system_prompt_block`, `prefetch`, `sync_turn`,
`on_memory_write` (action: add|replace|remove; target: memory|user), `backup_paths`,
`on_profile_created`, `on_profile_renamed`, `read_config_fields`, `write_config_fields`.
`CORE_MEMORY_PROVIDER_SENTINELS = frozenset({"", "default", "builtin", "built-in",
"none"})` [line 44]. `is_core_memory_provider` [line 47-49].

`ctx_bound` [line 21-26] binds a function to the caller's contextvars for another
thread/executor — profile isolation is a ContextVar-scoped HERMES_HOME override plus the
per-turn secret scope. `spawn_context_thread` [line 29-33] is the required path for
every memory-provider background job.

`TRIVIAL_PROMPT_RE` [line 66-72] and `is_trivial_prompt` [line 75-] gate recall:
empty input, slash commands, and bare greetings skip recall.

### 1.6.3 Memory approval/mutation via background review

**Verified implementation.** `agent/background_review.py::build_memory_write_metadata`
[line 755-770] builds provenance metadata for external memory-provider mirrors:
`write_origin`, `execution_context` (foreground/background_review), `session_id`,
`parent_session_id`, `platform`, `tool_name`, `task_id`, `tool_call_id`.

The review fork's memory/skill tool results are summarized by `summarize_background_review_actions`
[line 718-752], which skips tool messages already present in `prior_snapshot` so inherited
results are not re-surfaced.

**Relationship:** Memory writes from the foreground go through `handle_function_call` →
`model_tools.py` → the memory tool handler; background-review writes go through the
fork's own tool execution. Both mirror to external providers via `MemoryManager.on_memory_write`.

## 1.7 CUA tool dispatch, MCP communication, element tokens, action results, verification

### 1.7.1 CUA tool registration

**Verified implementation.** `tools/computer_use_tool.py` is the discovery shim: registers
`computer_use` in the `computer_use` toolset with `COMPUTER_USE_SCHEMA`,
`handle_computer_use` handler, `check_computer_use_requirements` check_fn
[tools/computer_use_tool.py:13-26].

### 1.7.2 CUA tool dispatch

**Verified implementation.** `tools/computer_use/tool.py::handle_computer_use`
[line 318-] is the main entry point. Order: hard blocks (`_reject_unsafe`) → approval
scopes (destructive action, then `bring_to_front`) → Bot Desktop lease check
(`_bd_lease.assert_agent_may_act`) → backend acquisition under `ExitStack` → re-check
lease under dispatch lock → fence check (`_fence`) → `_dispatch(backend, action, args,
fence=_fence, session_id=...)` → `_fence()` again → return result. A human takeover
voids the frame: `HumanHasControl` → `{"ok": False, "action": ..., "code":
"human_has_control", ...}`.

`_dispatch` [line 495-518] looks up the action spec in `_ACTIONS`, guards `app=`
input-target mismatch, threads `delivery_mode`/`bring_to_front` through input actions,
and routes to the backend handler. Unknown actions are never aliased; `_ACTION_SUGGESTIONS`
[line 490-493] names the nearest real action.

### 1.7.3 CUA backend interface

**Verified implementation.** `tools/computer_use/backend.py` defines the abstract
`ComputerUseBackend` ABC [line 87-146]: `start()`, `stop()`, `is_available()`,
`capture(mode, app, pid, window_id) -> CaptureResult`,
`click(element, x, y, button, click_count, modifiers, delivery_mode, bring_to_front)`,
`drag(...)`, `scroll(...)`, `type_text(text, delivery_mode, bring_to_front)`,
`key(keys, delivery_mode, bring_to_front)`, `list_apps()`, `list_windows()`,
`focus_app(app, raise_window)`, `set_value(value, element)`, `wait(seconds)`.

`UIElement` [line 16-31]: `index` (1-based SOM index), `role`, `label`, `bounds`
(x,y,w,h logical px), `app`, `pid`, `window_id`, `attributes`, `element_token` (opaque
per-snapshot handle for stale-detection).

`CaptureResult` [line 34-57]: `mode` ("vision"/"ax"/"som"), `width`, `height`,
`png_b64`, `elements`, `app`, `window_title`, `png_bytes_len`, `image_mime_type`, `note`,
`ax_max_elements`.

`ActionResult` [line 60-84]: `ok` (transport success only), `action`, `message`,
`capture`, `meta`, `verified` (AX read-back: True/False/None),
`effect` ("confirmed"|"unverifiable"|"suspected_noop"), `escalation`
(`{"recommended": "px"|"foreground"|"page", "reason": str}`), `path` (delivery rung),
`degraded`, `delivery_mode`, `code` (refusal code).

`ComputerUseProvider` [line 149-168] is the factory; `create_backend(permission_mode)`
returns a fresh backend for one Hermes session. `permission_mode` is `standard`|
`bounded`|`unrestricted` (approval bypass active).

### 1.7.4 Action result classification and verification

**Verified implementation.** `tools/computer_use/tool.py::_classify_action_result`
[line 521-563] is the next-ladder step from semantic evidence, in precedence order:
- `effect == "confirmed"` or `verified is True` → `{"decision": "done"}`
- `effect == "unverifiable"` → `{"decision": "verify_fresh_state", "hint": ...}` — do
  NOT repeat input on escalation recommendation alone
- `effect == "suspected_noop"` or not `ok` or `code is not None` → `{"decision":
  "escalate", ...}` with `recommended` from `res.escalation` ("px" = re-issue by
  coordinate; "foreground" = re-issue with `delivery_mode='foreground'`)
- transport success without semantic proof → `{"decision": "verify_fresh_state", ...}`

### 1.7.5 Element tokens

**Verified implementation.** `UIElement.element_token` [backend.py:31] is an opaque
per-snapshot handle from cua-driver, passed alongside `index` for explicit stale
detection: a stale token errors instead of silently re-resolving to a different element.

Screenshot dedup: `_screenshot_dedup_check` [tool.py:105-116] hashes sha256 over mime +
base64 payload; identical frames for the same target/session return text metadata plus
"screen unchanged" note and omit the image block. Bounded by
`_SCREENSHOT_DEDUP_MAX_STREAK = 2`. Prompt-cache prefixes stay intact (no transcript
rewrites).

### 1.7.6 MCP communication

**Inference / Partial:** MCP tooling exists extensively (`tools/mcp_tool.py`,
`mcp_tool_agent.py`, `mcp_tool_handlers.py`, `mcp_tool_transport.py`, etc.) but the CUA
tool itself does not use MCP — it uses cua-driver via `plugins.computer_use`.
`ComputerUseBackend` is an ABC that "any implementation (cua-driver over MCP, a plugin
driver, the test noop)" could satisfy [backend.py:1-4], but the in-tree implementation
uses cua-driver directly. No evidence that computer_use flows through MCP transport.

## 1.8 Gateway startup, lifecycle, sessions, profile isolation, and message routing

### 1.8.1 Gateway startup

**Verified implementation.** `gateway/run.py::start_gateway()` starts all configured
adapters; `GatewayRunner` owns lifecycle [line 1-4]. Run via `python -m gateway.run` or
`python cli.py --gateway`. Per-session `AIAgent` cache bounds: `_AGENT_CACHE_MAX_SIZE =
128`, `_AGENT_CACHE_IDLE_TTL_SECS = 3600.0` [line 52-53].

### 1.8.2 Gateway sessions

**Verified implementation.** `gateway/session.py::SessionSource` [line 68-100+] is where a
message originated: routes responses, feeds the system-prompt context block, records
origin for cron delivery. Fields: `platform`, `chat_id`, `chat_name`, `chat_type`,
`user_id`, `user_name`, `thread_id`, `scope_id` (Discord guild / Slack workspace /
Matrix server), `profile` (multiplex profile), `profile_route_rejected`, etc.

`gateway/session_lifecycle.py::SessionLifecycleMixin` [line 58-] handles explicit
suspension, crash-recovery markers, pruning. `_is_session_ended_in_db` [line 61-96]
self-heals at routing time.

### 1.8.3 Profile isolation

**Verified implementation.** Profile isolation is enforced through context-local
`HERMES_HOME` overrides (`hermes_constants.py::set_hermes_home_override` /
`get_hermes_home_override` / `reset_hermes_home_override` [line 32-49]) — deliberately
does NOT mutate `os.environ`.

`gateway/session_persistence.py::_open_session_db_for_active_scope` [line 90-]
resolves the SessionDB per call so multiplexed profiles reach their own store; handles
cached per path; failed opens enter bounded backoff with JSONL fallback. This is the fix
for #88532.

`gateway/AGENTS.md` [line 182-215] documents the profile-scope rules:
- `multiplex_profiles: false` is not "no scope ever" — a native hosted room serving a
  second profile flips `activate_multi_profile_hosting` inside the gateway process.
- Standalone entry points bind the launch profile's own scope via
  `run_turn.py::_standalone_launch_scope`.
- Hooks and observers register per served profile.
- Adapter YAML never reaches `os.environ` under multiplex (`platforms/_shared.py::
apply_yaml_bridge`).
- One launch-home identity: compare against `get_routing_process_hermes_home()`, never
  `os.environ["HERMES_HOME"]` read live.

### 1.8.4 Message routing and guards

**Verified implementation.** The gateway has TWO message guards [gateway/AGENTS.md:19-27]:
1. Base adapter (`platforms/base.py`) queues inbound messages in `_pending_messages`
   when `session_key in self._active_sessions`.
2. The runner (`run.py`/`run_busy.py`) intercepts `/stop`, `/new`, `/queue`, `/status`,
   `/approve`, `/deny` before they reach `running_agent.interrupt()`.

Commands that must reach the runner while the agent is blocked MUST bypass BOTH guards
and be dispatched inline — never via `_process_message_background()`, which races
session lifecycle.

`gateway/turn_executor.py::_UnboundedThreadExecutor` [line 25-93] runs every submitted
item at once on its own thread; no queue, no cap. Items run in an empty
`contextvars.Context`; `reset_reused_thread_state` drops thread-keyed state before a
worker parks.

**Streaming delivery contract** [gateway/AGENTS.md:29-51]: four invariants for
`draft_stream_is_message = True` adapters — prefix-stable draft frames, consumer
declares the final, interim sends carry `metadata["_interim_send"] = True`, reconcile by
edit never plain send.

## 1.9 Inference paths inventory summary

| Subsystem | Entry point | Key files | Status |
|---|---|---|---|
| Foreground turn | `run_conversation` | `agent/conversation_loop.py`, `turn_api_call.py`, `turn_api_request.py`, `turn_response_intake.py`, `turn_tool_round.py` | Verified |
| Auxiliary side-tasks | `call_llm` | `agent/auxiliary_client.py` | Verified |
| MoA reference+aggregator | `/moa` slash → `moa_loop` | `agent/moa_loop.py`, `moa_alternation.py` | Verified |
| Background-review fork | `_spawn_background_review` | `agent/background_review.py`, `run_agent.py` | Verified |
| Credential pool | pool rotation | `agent/credential_pool.py`, `credential_pool_model_cooldowns.py`, `fallback_cooldown.py` | Verified |
| Retry-After / backoff | `parse_retry_after_seconds` | `agent/retry_utils.py`, `nous_rate_guard.py` | Verified |
| Error classification | `classify_api_error` | `agent/error_classifier.py` | Verified |
| Prompt cache | `build_prompt_cache_plan` | `agent/prompt_caching.py`, `prompt_cache_scope.py`, `prompt_refresh.py` | Verified |
| System prompt | `_build_system_prompt` | `agent/system_prompt.py`, `prompt_builder.py` | Verified |
| Memory | `MemoryManager` | `agent/memory_manager.py`, `memory_provider.py` | Verified |
| CUA | `handle_computer_use` | `tools/computer_use_tool.py`, `computer_use/tool.py`, `computer_use/backend.py` | Verified |
| Gateway | `start_gateway` | `gateway/run.py`, `session.py`, `session_lifecycle.py`, `turn_executor.py` | Verified |

# 2. Resolve the most important design questions

## A. Shared inference scheduler

### A.1 Every path capable of dispatching an inference request

1. **Foreground turn API call** — `agent/turn_api_call.py::perform_api_call` [72-294],
   triggered per iteration of `agent/conversation_loop.py::run_conversation`.
2. **Auxiliary side-task call** — `agent/auxiliary_client.py::call_llm`, used by
   compression, search, vision, titles, MoA advisors.
3. **MoA reference fan-out** — `agent/moa_loop.py::_slot_runtime` + `call_llm` per
   reference slot (up to 8 concurrent workers).
4. **MoA aggregator call** — same `call_llm` path with aggregator model/runtime.
5. **Background-review fork** — `agent/background_review.py::build_cache_parity_fork`
   [979-1000] → new `AIAgent` → `run_conversation` → `perform_api_call`.
6. **Codex incomplete continuation** — `agent/turn_response_intake.py` [226-240]
   → `continue_codex_incomplete` → another API call.
7. **Incomplete scratchpad retry** — `agent/turn_response_intake.py` [207-223] → up to
   2 retries.

### A.2 Best shared insertion point for a scheduler

**Inference.** The narrowest useful insertion point is inside
`agent/turn_api_call.py::perform_api_call` (and `agent/auxiliary_client.py::call_llm`
for the auxiliary path), at the point just before the actual provider HTTP/SDK call.
Both foreground and auxiliary paths converge there. A scheduler injected at that seam
can enforce:

- **Provider-specific request pacing:** `perform_api_call` already knows `agent.provider`
  and `agent.base_url`; pacing keys can be `(provider, base_url)`.
- **Model-specific and credential-specific quota policies:** The credential pool
  (`agent/credential_pool.py`) already tracks `last_status`, `model_cooldowns`,
  `last_error_reset_at` per entry; `fallback_cooldown.py::_arm_rate_limit_cooldown`
  [45-76] arms cooldowns. A scheduler reads these (read-only) and defers/rotates.
- **Priority scheduling:** Interactive foreground turns carry `agent._is_user_initiated_turn`
  [agent/turn_api_request.py:43-57]; background-review forks set `skip_memory=True` and
  `_persist_disabled`. Priority can be derived from turn provenance (live turn >
  background review > auxiliary compression > MoA reference).
- **Interactive request priority over background work:** `cancel_background_review_for_live_turn`
  [agent/background_review.py:129-168] already preempts background reviews with a 2.0s
  bounded deadline. A scheduler honors this by not admitting background inference while a
  live turn holds the scheduler slot.
- **Shared cooldowns and Retry-After handling:** `agent/retry_utils.py::provider_retry_after_seconds`
  [185-195] and `parse_retry_after_seconds` [30-64] already parse provider cooldowns;
  `nous_rate_guard.py` shares Nous state cross-session. A scheduler consumes these
  rather than re-parsing.
- **Multi-process coordination:** `nous_rate_guard.py` writes a shared JSON file under
  `HERMES_HOME/rate_limits/`. A scheduler needing cross-process coordination would extend
  that pattern (file-based or lock-based) rather than inventing a new transport.

### A.3 What existing credential-pool functionality should remain unchanged

**Verified.** The following should remain unchanged — they are load-bearing for
cross-process pool consistency:
- The pool's persistence format and `model_cooldowns` per-entry dict
  [credential_pool.py:238, credential_pool_model_cooldowns.py:37-59].
- `_exhausted_ttl` sole-credential short bench (60s vs 1h default)
  [credential_pool.py:135-138].
- `status_cleared_at` reset marker for cross-process recency
  [credential_pool.py:224-226, credential_pool_admin.py:12-18].
- `limit_state()` read-only reporting
  [credential_pool_model_cooldowns.py:121-145].

### A.4 Scheduler design conclusion (inference)

The scheduler should be a **read-only admission/decision layer** sitting above the pool
and below `perform_api_call`/`call_llm`. It does not own credential storage; it queries
the pool's `limit_state()` and `token_is_blocked()` plus `fallback_cooldown` state, and
returns (a) proceed-now, (b) wait-until timestamp, or (c) rotate-to-next-credential.
Multi-process coordination reuses the `nous_rate_guard.py` shared-file pattern or a
cross-process lock on `HERMES_HOME`.

## B. Background evolution

### B.1 How the existing background-review system can be extended

**Verified foundation.** The existing system [agent/background_review.py] already has:
- Fork creation with cache parity (`build_cache_parity_fork`, line 979-1000).
- Cancellation with bounded deadline (`cancel_background_review_for_live_turn`, line 129-168).
- Idle deferral for managed local runtime (`agent/review_idle_queue.py`).
- Per-review run token handshake (`_BackgroundReviewRun`, line 28-61).
- Usage attribution to parent (`_record_review_usage_to_parent`, line 787-806).
- Write-origin tracking (`build_memory_write_metadata`, line 755-770).

**Extensions (inference — none of these exist in source yet):**

1. **Lightweight online experience capture:** Reuse the review fork to replay the
   conversation snapshot and emit structured "experience records" (what the user asked,
   what tools were called, what succeeded/failed, what the user corrected). These feed
   the experience-collection layer, not the memory store directly. The fork's
   `_persist_disabled` detachment means captures never pollute the transcript.

2. **Deeper idle-time analysis:** The idle queue (`review_idle_queue.py`) already
   dispatches reviews when the machine is quiet. Extend it to run deeper analysis
   (longer token budget, specialist models) during extended idle windows. Bounded by
   `defer_max_age_s` (default 30 min).

3. **Specialist model roles:** `_resolve_review_runtime` [agent/background_review.py:253-]
   already supports routing the review fork to a different model via
   `auxiliary.background_review.{provider,model}`. Specialist roles (capture reviewer,
   proposal generator, evaluator) can be distinct `auxiliary.background_review.*`
   config entries, each resolving its own runtime.

4. **Proposal generation:** The review fork already calls `skill_manage` and `memory`
   tools. Proposals (staged, not applied) are signaled by `data.get("staged")` in
   `_action_lines` [agent/background_review.py:679-682]. Extend to stage proposals that
   require explicit approval before application.

5. **Independent evaluation:** A second fork (or second pass) with a different model
   evaluates the first fork's proposals. State isolation is already provided by
   `build_cache_parity_fork`'s detached session DB.

6. **Bounded compute budgets:** `_review_input_token_budget` [line 215-225] already
   bounds input tokens (75% of context window, 600k cap). Extend to per-task
   `max_iterations`, `max_tool_calls`, and wall-clock deadlines passed into
   `build_cache_parity_fork(max_iterations=...)`.

### B.2 Concurrency, prompt-cache, and profile-isolation risks

**Concurrency (verified risks in source):** Multiple background reviews for the same
session are gated by `prepare_background_review_run` — returns None if a current run is
not done [agent/background_review.py:83-85]. The `_UnboundedThreadExecutor` in the
gateway [turn_executor.py:25-93] runs every gateway turn on its own thread; review
threads are separate daemon threads (`name="bg-review"`). No global cap on concurrent
review threads exists — inference from source.

**Prompt-cache risk (verified):** The invariant [agent/AGENTS.md:55-61] forbids
mutating past context mid-conversation. Background forks are deliberately detached
(`_persist_disabled`, `_session_db = None`) so they never touch the parent's cached
prompt [agent/background_review.py:985-986]. The same-model cache-parity fork shares
`session_id` for prefix warmth [line 984-988].

**Profile-isolation risk (verified):** `propagate_context_to_thread` carries the active
profile into the review thread [run_agent.py:820]. `hermes_home_key()` is used in MoA
slot runtime caching [moa_loop.py:259-260] to scope per-profile. A review thread spawned
without context propagation would silently land on the default profile — the same class
of bug as `ctx_bound` warns about [memory_provider.py:23-26].

## C. Personality adaptation

### C.1 How a learned preference profile can coexist with existing personality and memory

**Verified mechanisms:**

1. **System prompt tiers** [agent/system_prompt.py:3-8]: `stable` (identity/guidance),
   `context` (workspace/caller message/context files), `volatile` (skills index, memory,
   USER.md, external memory provider, timestamp line). A learned preference profile is
   naturally a `volatile` tier addition — it changes per session but is rebuilt from
   stored preferences on each session start, not mid-turn.

2. **Prompt-refresh epoch** [agent/prompt_refresh.py:1-13]: `hermes sessions
   refresh-prompts` records an epoch; at the next turn, if `requested_epoch >
   applied_epoch`, the prompt rebuilds once through the normal builder. One prefix-cache
   break per request. This is the sanctioned path for personality changes to take
   effect.

3. **Prompt-cache invariant** [agent/AGENTS.md:55-61]: The system prompt is byte-stable
   for the life of a conversation; the ONLY context mutation is compression. Personality
   changes MUST NOT reconstruct the prompt mid-turn.

4. **Memory injection** [agent/memory_manager.py]: Memory providers inject
   `system_prompt_block` per turn. A preference profile can be exposed as a memory
   block, injected via the existing memory-prefetch path rather than prompt mutation.

### C.2 Safe session boundaries for personality changes

**Verified.** `prompt_refresh.py::rebuild_for_refresh` [line 79-] rebuilds the prompt
at a given epoch on the next turn. `stored_prompt_refresh_epoch` [line 50-56] gates the
rebuild. `stamp_prompt_epoch` [line 59-64] records that the freshly built prompt satisfies
the epoch.

**Inference:** A learned preference profile should be:
1. Stored in the memory/skill system (not the system prompt directly).
2. Injected via the `volatile` tier or a memory provider block at session start.
3. Changed only at session boundaries (`/new`) or via the prompt-refresh epoch mechanism
   (one cache break per request).
4. Never applied by mutating `agent._cached_system_prompt` mid-turn.

## D. CUA Interaction Intelligence

### D.1 What information the existing CUA toolchain makes available to Hermes

**Verified.** From `tools/computer_use/backend.py` and `tools/computer_use/tool.py`:

**Per-action output (`ActionResult`):**
- `ok` — transport success only
- `action` — click/type/key/scroll/drag/wait/focus_app/set_value/capture/list_apps
- `message` — human-readable summary
- `verified` — AX read-back: True (confirmed), False (unconfirmed), None (n/a)
- `effect` — "confirmed" | "unverifiable" | "suspected_noop"
- `escalation` — `{"recommended": "px"|"foreground"|"page", "reason": str}`
- `path` — delivery rung that ran ("ax", "x11_pixel", "cgevent_fg", etc.)
- `degraded` — AX walk found no actionable elements
- `delivery_mode` — echo of requested background/foreground
- `code` — refusal code ("background_unavailable", "desktop_scope_disabled", etc.)
- `capture` — trailing `CaptureResult` when requested/always-on

**Per-capture output (`CaptureResult`):**
- `mode` — "vision" (png only), "ax" (elements only), "som" (both)
- `png_b64` — base64 screenshot
- `elements` — list of `UIElement` (index, role, label, bounds, app, pid, window_id,
  attributes, `element_token`)
- `app`, `window_title`, `png_bytes_len`, `image_mime_type`, `note`, `ax_max_elements`

**Per-element (`UIElement`):**
- `index` (1-based SOM index), `role`, `label`, `bounds`, `app`, `pid`, `window_id`,
  `attributes`, `element_token` (stale-detection handle)

**Control-plane signals:**
- `_reject_unsafe` hard blocks (dangerous type patterns, blocked key combos) [tool.py:60-71]
- Approval scopes (destructive actions, bring_to_front) [tool.py:338-342]
- Bot Desktop lease (`HumanHasControl` — human has physical control) [tool.py:331-334]
- Permission mode: standard/bounded/unrestricted (approval bypass) [tool.py:131-157]
- Screenshot dedup: identical frames omitted with "screen unchanged" note
  [tool.py:105-116]

### D.2 Converting CUA data into reusable knowledge

**Inference (none of this exists in source yet):**

1. **Successful actions:** `effect == "confirmed"` / `verified == True` records can be
   folded into the background-review experience capture (§B.1) as "this element index
   on this app performs action X successfully." The `element_token` provides a
   stale-aware element identity.

2. **Failed actions:** `effect == "suspected_noop"` or `ok == False` with `escalation`
   records the recommended next rung ("px" → coordinate retry, "foreground" → delivery
   mode change, "page" → different page state). These are negative examples for
   navigation-strategy learning.

3. **Accessibility information:** `UIElement.role`/`label`/`bounds` from AX trees can
   be distilled into element descriptors (role + label → action affinity) independent of
   pixel coordinates.

4. **Visual state:** `CaptureResult.png_b64` plus `som` overlay indices give
   before/after visual state pairs for verification.

5. **Verification results:** `ActionResult.verified`/`effect`/`path` form a
   verify→escalate ladder [tool.py:_classify_action_result, 521-563]. Each rung's
   outcome is a data point for what works on which platform/app.

### D.3 Keeping learned navigation separate from static coordinate recordings

**Inference.** Source makes a clear distinction:
- **Dynamic/learned:** `element_token` (per-snapshot handle), `index` (SOM index from
  capture), `role`/`label` (AX semantics) — these are re-resolved each capture.
- **Static/recorded:** `bounds` (x,y,w,h logical px), `path` (delivery rung) — these
  are coordinate-dependent and can go stale across window resizes, theme changes, or
  app updates.

**Inference:** Learned navigation strategies should key on `(app, role, label,
element_token)` — re-verified against each fresh capture — and treat `bounds`/`path` as
transient hints, never as authoritative static recordings. `_bounds_hints`
[tool.py:614-635] already warns when AX bounds live in a different coordinate space than
the screenshot (HiDPI scale factor). The `element_token` stale-detection [backend.py:31]
is the mechanism to avoid silently clicking the wrong element.

**Do not propose replacing the existing CUA backend:** The `ComputerUseBackend` ABC
[backend.py:87-146] and `ComputerUseProvider` factory [line 149-168] are the
existing contract. Learning rides on top of it, consuming `CaptureResult` and
`ActionResult`, never replacing the driver.

## E. Saturnite gateway core

### E.1 Narrowest useful boundary between Python gateway and Saturnite

**Inference (no Saturnite code exists in this repo — the path `C:\Users\atimo\Saturnite`
was referenced by the user but not inspected).** Based on the actual Hermes gateway
source, the narrowest boundary is the **adapter interface**: each platform adapter
(`gateway/platforms/<name>.py` over `platforms/base.py`) implements connect, send,
receive, and message parsing. The Python gateway's core responsibilities are:

- Session lifecycle (`gateway/session.py`, `session_lifecycle.py`, `session_persistence.py`)
- Profile isolation (`gateway/AGENTS.md` § Profile scope)
- Message guards (two guards: adapter queue + runner interception)
- Turn execution (`gateway/turn_executor.py::_UnboundedThreadExecutor`)
- Streaming delivery contract (`gateway/AGENTS.md` § Streaming)
- Slash commands and authorization (`slash_commands_*.py`, `authz_mixin.py`)

**Interop requirements (inference from source):**

| Concern | What Hermes requires | Evidence |
|---|---|---|
| Serialization | SessionSource → JSON (origin_json), session rows, routing index | `run_agent.py::_gateway_origin_json` [67-88], `gateway/session_persistence.py` |
| Concurrency | `_UnboundedThreadExecutor` (one thread per turn), per-session agent cache (128 max, 1h TTL) | `gateway/run.py` [52-53], `turn_executor.py` |
| Lifecycle | start_gateway / GatewayRunner, adapter connect/disconnect timeouts | `gateway/run.py` [54-63] |
| Error propagation | Two message guards, /stop /new /queue /status bypass | `gateway/AGENTS.md` [19-27] |
| Profile isolation | Context-local HERMES_HOME, per-profile SessionDB, adapter YAML not in os.environ | `hermes_constants.py`, `gateway/session_persistence.py` [90-99] |
| Adapter compatibility | Each adapter picks a base toolset; platform-gated toolsets | `toolsets.py` [456-466], `gateway/AGENTS.md` [13] |

### E.2 What NOT to recommend (per user constraints, verified against source)

- **Replacing all platform adapters:** Not warranted — 20+ platforms each have
  platform-specific quirks; the adapter base class (`platforms/base.py`) already
  abstracts the common message-queue/guard contract.
- **Introducing WASM without demonstrated requirement:** No WASM references found in
  the gateway or tools; no inference use case requires it.
- **Saturnite model provider without concrete inference use case:** The auxiliary
  client (`auxiliary_client.py`) already routes side tasks; MoA (`moa_loop.py`) already
  supports multi-model. No gap that a Saturnite provider fills.
- **General tool runtime implementing computer-use backend:** The `ComputerUseBackend`
  ABC [backend.py:87-146] is the computer-use contract; tools/mcp_tool.py etc. are a
  separate concern. A general tool runtime should not implement `click`/`type`/`capture`.

### E.3 Recommended boundary (inference)

If Saturnite is introduced, the narrowest useful integration is: **Saturnite implements
one or more platform adapters that speak the Hermes gateway adapter contract** (connect,
send, receive, session-keyed message routing), while the Python gateway retains session
management, profile isolation, message guards, turn execution, and streaming. The
interop boundary is serialized `SessionSource` + message payload over a transport the
adapter defines. No core model-provider, tool-runtime, or computer-use changes needed.

## F. Experimental optimization

### F.1 Data and evaluation infrastructure needed before NEAT or adaptive meta-controller

**Inference (none of this exists in source):**

Before introducing NEAT (NeuroEvolution of Augmenting Topologies) or another adaptive
meta-controller, the following infrastructure would be needed:

1. **Experience dataset** — structured records of (prompt, model, provider, credential,
   tool_calls, action_results, outcome) from background reviews and live turns. The
   background-review fork already captures messages and tool results
   [background_review.py:718-752], but there is no structured experience store or
   schema.

2. **Evaluation harness** — offline replay of recorded turns with scored outcomes
   (task completed, user satisfaction, tool success rate, cost, latency). No such harness
   exists in `tests/` (tests are behaviour-contract, not change-detector).

3. **Telemetry / metrics** — `hermes_cli.observability.shared_metrics_efficiency` and
   `shared_metrics_harness` exist for prompt-cache and reply-content metrics, but there
   is no optimization objective function or Pareto frontier tracking (cost vs. quality vs.
   latency).

4. **Safety gates** — an adaptive controller that changes model/provider/credential
   selection must not violate the prompt-cache invariant, credential-pool persistence
   format, or profile isolation. No such gates exist.

### F.2 Operational optimization vs language-model training

**Distinction (inference):**

- **Operational optimization** = selecting which model, provider, credential, and
  parameters to use for each request (what the credential pool, fallback chain, and
  auxiliary client already do at the routing level). This is what a meta-controller
  would adapt. No training data is produced; no model weights change.

- **Language-model training** = updating model weights from experience data. Hermes has
  no training pipeline, no GPU training backend, no loss computation, no weight
  updates. The background-review system creates *skills* and *memories* (symbolic
  knowledge), not trained weights.

**Conclusion:** Any NEAT/adaptive work in Hermes is operational optimization (routing
and tool-selection policy), not LM training. It would need the experience dataset and
evaluation harness listed above before it is safe to introduce.

# 3. Correct the earlier roadmap

## 3.1 Evaluation of the existing seven-phase roadmap

**Inference** (the original roadmap document was not re-read; this section evaluates
based on source-code evidence gathered in §1):

Recommendations that are **outside actual project objectives**, **unnecessary**,
**premature**, or **based on unverified assumptions**:

1. **Replace core inference with a new scheduler as phase 1** — Premature. Source shows
   five separate inference paths with no shared scheduler, but the credential pool,
   fallback cooldowns, and Retry-After handling are already mature and load-bearing. A
   scheduler should be a thin read-only admission layer, not a replacement.

2. **Replace all platform adapters with Saturnite** — Outside objectives / unverified.
   The adapter base class and per-platform toolsets already work; no evidence that a
   Saturnite rewrite improves anything.

3. **Introduce WASM** — Unnecessary; no requirement found in source.

4. **Create a Saturnite model provider** — Premature; no concrete inference use case
   exists that `auxiliary_client.py` + `moa_loop.py` don't already cover.

5. **General tool runtime implements computer-use backend** — Outside objectives; the
   `ComputerUseBackend` ABC is the correct contract, and tools/MCP are separate.

6. **NEAT / evolutionary optimization as an early phase** — Premature; requires
   experience dataset + evaluation harness that don't exist (§F).

7. **Mid-turn prompt reconstruction for personality** — Violates the prompt-cache
   invariant [agent/AGENTS.md:55-61]; changes must use the prompt-refresh epoch or
   memory-block injection.

## 3.2 Revised roadmap

Order changed based on source-code evidence: scheduling first (it unlocks everything
else), then experience collection (feeds adaptation), then adaptive personality
(depends on experience data), then CUA learning (depends on CUA result data already
available), then deep dreaming/Overclock (depends on experience + personality), then
Saturnite gateway-core integration (narrow adapter boundary, independent), then
experimental evolutionary optimization (last, needs all data infrastructure).

### Phase 1: Shared inference scheduling (verified need, partial implementation)

**Goal:** A thin read-only admission/decision layer above the credential pool and below
`perform_api_call`/`call_llm`.

**Source-backed scope:**
- Read `limit_state()` and `token_is_blocked()` from `agent/credential_pool.py`
  [credential_pool_model_cooldowns.py:121-145, 63-74].
- Read `_arm_rate_limit_cooldown` state from `agent/fallback_cooldown.py` [45-76].
- Read `provider_retry_after_seconds` from `agent/retry_utils.py` [185-195].
- Insert at `agent/turn_api_call.py::perform_api_call` [72-294] and
  `agent/auxiliary_client.py::call_llm`.
- Multi-process coordination via the existing `nous_rate_guard.py` shared-file pattern.

**Do not touch:** Pool persistence format, `model_cooldowns` dict, `status_cleared_at`,
`_exhausted_ttl` sole-credential bench — all load-bearing for cross-process consistency.

### Phase 2: Experience collection (verified foundation, needs structured store)

**Goal:** Capture structured experience records from live turns and background reviews.

**Source-backed scope:**
- Reuse `build_cache_parity_fork` [agent/background_review.py:979-1000] for detached
  review execution.
- Reuse `summarize_background_review_actions` [line 718-752] for action summarization.
- Reuse `_record_review_usage_to_parent` [line 787-806] for usage attribution.
- Add a structured experience record schema (prompt, model, tool_calls, action_results,
  outcome) — does not exist yet.

### Phase 3: Adaptive personality (verified safe path, needs preference store)

**Goal:** Learned preference profile coexisting with personality and memory.

**Source-backed scope:**
- Store preferences in the memory/skill system (not system prompt).
- Inject via `volatile` tier [agent/system_prompt.py:3-8] or memory provider block
  [agent/memory_manager.py].
- Change via prompt-refresh epoch [agent/prompt_refresh.py:1-13] or session boundary
  (`/new`) — never mid-turn.
- Preserve prompt-cache invariant [agent/AGENTS.md:55-61].

### Phase 4: CUA learning (verified data availability, needs knowledge store)

**Goal:** Convert CUA action results into reusable navigation knowledge.

**Source-backed scope:**
- Consume `ActionResult` (effect, verified, escalation, path) and `CaptureResult`
  (elements with element_token) [tools/computer_use/backend.py:60-84, 34-57].
- Learn on `(app, role, label, element_token)` keys; treat `bounds`/`path` as transient
  [tool.py:_bounds_hints 614-635, backend.py:31 element_token].
- Use background-review experience capture (§B.1) as the storage path.
- Do not replace `ComputerUseBackend` ABC [backend.py:87-146].

### Phase 5: Deep dreaming and Overclock (inference; depends on phases 2-4)

**Goal:** Unspecified in source; placeholder for advanced self-improvement features.

**Dependency:** Requires experience data (phase 2) and personality adaptation (phase 3).
No source evidence for specific implementation.

### Phase 6: Saturnite gateway-core integration (verified boundary, inference on Saturnite side)

**Goal:** Narrow adapter-boundary integration.

**Source-backed scope:**
- Saturnite implements platform adapter(s) speaking the Hermes gateway adapter contract
  (connect, send, receive, session-keyed routing).
- Python gateway retains session management, profile isolation, message guards, turn
  execution, streaming [gateway/run.py, session.py, turn_executor.py].
- Interop via serialized `SessionSource` + message payload.

**Do not do:** Replace all adapters, WASM, Saturnite model provider, tool runtime as
computer-use backend (§E.2).

### Phase 7: Experimental evolutionary optimization (last; needs all data infrastructure)

**Goal:** NEAT or adaptive meta-controller for operational routing decisions.

**Prerequisites (none exist in source):**
- Experience dataset (phase 2)
- Evaluation harness with scored outcomes
- Metrics / Pareto frontier tracking
- Safety gates (prompt-cache invariant, credential-pool format, profile isolation)

**Distinction:** Operational optimization (routing policy), not LM training (§F.2).

# 4. Output requirements compliance

This addendum:
- Is technically detailed with actual source code references.
- Uses source references in the exact format `[relative/path/to/file.py:120-168]`.
- Includes call-flow traces (§1.1, §1.9 tables).
- Clearly distinguishes: Verified implementation / Partial implementation /
  Documentation-only / Inference / Unknown or unverified (each claim labeled).
- Does not invent line numbers, API contracts, or Saturnite capabilities.
- Does not change the original audit (`HERMES_VANILLA_AUDIT_5fcafaa.md` untouched).
- Does not implement anything (read-only investigation).

# 5. Most important unresolved questions requiring project-owner design decision

1. **Scheduler ownership:** Should the shared inference scheduler own credential
   rotation decisions, or only advise (proceed/wait/rotate) while the existing
   `CredentialPool` retains final authority? The pool's persistence format and
   `model_cooldowns` are load-bearing for cross-process consistency (#89415).

2. **Experience store location:** Should experience records live in `state.db` (SQLite,
   WAL mode) or a separate append-only log? Background-review forks have `_session_db =
   None` and write only `session_model_usage` [background_review.py:791-794] — a new
   write path would be needed.

3. **Personality storage:** Should learned preferences be a new memory-provider block,
   a `volatile` system-prompt tier entry, or a dedicated `preferences` table? The
   prompt-cache invariant [AGENTS.md:55-61] forbids mid-turn reconstruction.

4. **CUA learning scope:** Should learned navigation strategies key on
   `(app, role, label, element_token)` with `bounds` treated as transient, or is
   coordinate-based recording acceptable for specific apps? The `element_token`
   stale-detection [backend.py:31] supports the former.

5. **Saturnite scope:** If Saturnite is pursued, should it implement adapters only
   (narrow boundary, recommended) or also take over session management and profile
   isolation (wide boundary, contradicts existing architecture)?

6. **NEAT prerequisites:** Who owns building the experience dataset and evaluation
   harness before evolutionary optimization is considered? No such infrastructure
   exists in source (§F.1).

7. **Background-review concurrency cap:** Should there be a global cap on concurrent
   review threads? Currently none exists; the `_UnboundedThreadExecutor` [turn_executor.py]
   runs gateway turns unbounded, and review threads are separate daemon threads.

