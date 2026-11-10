# HERMES ROADMAP — RANKED EASIEST TO HARDEST

Source: ChatGPT export comparing Claude Code vs Hermes agent architecture and the Hermes self-improvement roadmap. This file contains the isolated Hermes roadmap, ranked by implementation difficulty (easiest first, hardest last), plus the Go/gateway speed-boost discussion.

---

## Roadmap Overview

Seven phases from the Hermes audit, reordered from easiest to hardest to implement. Difficulty ratings are engineering estimates (1 = easiest, 5 = hardest).

| Rank | Phase | Difficulty | Original Phase |
|------|-------|------------|----------------|
| 1 | Adaptive Personality — initial version | 2/5 | Original Phase 3 |
| 2 | Saturnite Gateway Integration — narrow adapter | 3/5 | Original Phase 6 |
| 3 | Shared Inference Scheduler | 3.5/5 | Original Phase 1 |
| 4 | Structured Experience Collection | 4/5 | Original Phase 2 |
| 5 | CUA Interaction Learning | 4/5 | Original Phase 4 |
| 6 | Deep Dreaming and Overclock | 4.5/5 | Original Phase 5 |
| 7 | Evolutionary Optimization / NEAT | 5/5 | Original Phase 7 |

---
## Rank 1 — Adaptive Personality — Initial Version (Easiest)

**Difficulty: 2/5** — Original Phase 3

Build a persistent preference profile that learns how the user likes the agent to communicate and work.

### Scope
- Explicit preference storage (user model)
- Preference retrieval at session startup
- Integration into the existing volatile prompt tier or memory-provider block
- Updates through the existing prompt-refresh mechanism

### Constraint
No rebuilding the system prompt halfway through a conversation (preserves the prompt-cache invariant). Automatic personality learning comes later, after experience collection.

## Rank 2 — Saturnite Gateway Integration — Narrow Adapter

**Difficulty: 3/5** — Original Phase 6

Implement the Hermes gateway adapter contract in Saturnite.

### Scope
- Connection lifecycle management
- Message serialization
- Session-keyed routing
- Inbound/outbound communication

### Constraint
Keep Python responsible for session management, profile isolation, and agent execution. Saturnite's own implementation has not been inspected as part of the audits, so the cross-language effort is still uncertain.

## Rank 3 — Shared Inference Scheduler

**Difficulty: 3.5/5** — Original Phase 1

A shared admission and scheduling mechanism for model requests.

### Scope
- Foreground versus background priority
- Provider-specific pacing
- Cooldown and Retry-After handling
- Auxiliary-model request scheduling
- Multi-process coordination

### Constraint
Preserve the existing credential pool and its persistence format. This is a read-only admission/decision layer above the credential pool and below `perform_api_call`/`call_llm`.
## Rank 4 — Structured Experience Collection

**Difficulty: 4/5** — Original Phase 2

Build the agent's actual experience dataset.

### Scope
- User requests
- Tool calls and results
- Failures and recovery strategies
- Successful outcomes
- Model and resource usage

### Decision needed
Whether to use SQLite or an append-only log, including profile isolation and privacy controls.

## Rank 5 — CUA Interaction Learning

**Difficulty: 4/5** — Original Phase 4

Turn computer-use experience into reusable navigation knowledge.

### Scope
- Learn from confirmed actions
- Record failed interactions
- Use accessibility element identities (element_token, role, label)
- Handle stale element tokens
- Avoid blindly trusting old screen coordinates

### Constraint
The existing CUA backend already exposes useful structured action and capture results. Do not replace `ComputerUseBackend` ABC.

## Rank 6 — Deep Dreaming and Overclock

**Difficulty: 4.5/5** — Original Phase 5

The agent starts doing more substantial autonomous analysis.

### Scope
- Background experience analysis
- Specialist model roles
- Skill and memory improvement proposals
- Independent evaluation
- Bounded compute budgets
- Explicit approval for consequential changes

### Constraint
Needs the experience infrastructure and scheduler first.

## Rank 7 — Evolutionary Optimization / NEAT (Hardest)

**Difficulty: 5/5** — Original Phase 7

Experimental optimization of the agent's operational decisions.

### Scope
- Evaluation harness
- Experience dataset
- Scoring and metrics
- Candidate policy generation
- Pareto-frontier tracking
- Safety gates and controlled promotion

### Constraint
This should be the last major project. NEAT without measurable outcomes would just be evolutionary guesswork. Distinguish operational optimization (routing policy) from language-model training (no weight updates).
---

## Dependency Order (Autonomous Learning Pipeline)

While the ranking above is by difficulty, the dependency order for the learning pipeline is:

```
Shared Inference Scheduler
          |
          v
Experience Collection
          |
          +----------+
          |          |
          v          v
   Personality    CUA Learning
    Adaptation
          |          |
          +----+-----+
               |
               v
       Deep Dreaming
               |
               v
       NEAT / Evolution
```

The narrow Saturnite adapter can progress independently.

---

## Go / Gateway Speed Boost

### Proposal
Add Go as a complementary runtime to speed up the gateway using goroutines.

### Why Go
- Lightweight goroutines for high-concurrency networking
- Efficient network concurrency and channels for worker communication
- Strong standard-library HTTP and networking support
- Compiled native executables with straightforward profiling and race detection

### Proposed Division of Responsibility

| Layer | Language | Responsibility |
|-------|----------|----------------|
| Data plane | Go | WebSocket connections, HTTP ingress/egress, event framing, streaming transport, connection management, high-throughput message fan-out, transport-level rate limiting |
| Control plane | Python | Session management, profile isolation, identity resolution, permissions/approvals, credential management, tool execution, model orchestration, memory/skills, agent lifecycle |

### Recommended Structure

```text
hermes-agent/
│
├── gateway/                 # Existing Python gateway (control plane)
├── tui_gateway/             # Existing Python RPC backend
├── go/
│   └── gateway-runtime/
│       ├── cmd/
│       │   └── hermes-gateway/
│       ├── internal/
│       │   ├── transport/
│       │   ├── connections/
│       │   ├── streaming/
│       │   ├── events/
│       │   └── health/
│       ├── protocol/
│       ├── go.mod
│       └── go.sum
│
└── tests/
```

### Important Caveats
- Goroutines cannot magically make Python's agent execution concurrent. The GIL and synchronous tool calls remain in Python.
- Moving the full gateway to Go would require moving actual work into Go — a much larger project.
- Go must be optional: Hermes should retain a functional Python-only gateway with clean fallback if the Go runtime is missing or fails.

### Before Implementing
Benchmark the Python gateway:
1 concurrent session → 10 → 50 → 100 sessions, measuring CPU, RAM, worker counts, event-loop latency, P50/P95/P99 transport latency, and message throughput. Then build a small Go transport prototype and run the same workload. Only promote Go into production if the measured improvement justifies the extra process, RPC protocol, and maintenance burden.

---

## Engineering Tracks

**Track A — Agent evolution:** Shared scheduler → Experience collection → Personality and CUA learning → Deep Dreaming → NEAT

**Track B — Systems engineering:** Baseline profiling → Go transport prototype → Benchmarks → Optional production integration

**Track C — Saturnite integration:** Adapter contract → Serialization → Gateway interoperability → Conformance testing

### Recommendation
Start with Track B's profiling investigation alongside the first small personality-profile milestone (Rank 1). This gives useful progress without prematurely introducing a second runtime.

---

*Compiled from ChatGPT export "Compare Coding Agents" — Hermes self-improvement roadmap section only. Noise (Claude Code comparison, OVHcloud/Kaggle discussion, model pricing, etc.) excluded.*
