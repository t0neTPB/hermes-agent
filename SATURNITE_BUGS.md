# SATURNITE BUG REGISTRY

**Last Updated:** 2026-11-10
**Status:** Active investigation
**Context:** Discovered during Hermes Rank 2 (Saturnite Gateway Integration) implementation

---

## BUG CLASSIFICATION

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH | 4 |
| MEDIUM | 3 |
| LOW | 2 |

---

## CRITICAL BUGS

### BUG-001: Wrapper Metadata System Fundamentally Broken for Ecosystem Crates

**Title:** Wrapper metadata JSON files contain non-existent function names; most ecosystem crates lack C-ABI exports

**Discovered:** 2026-11-10 during Hermes Rank 2 implementation
**Affects:** All use rust: imports for ecosystem crates (tokio, serde, serde_json, anyhow, tracing, tungstenite, uuid, reqwest, tokio-tungstenite)
**Blocker:** Prevents building any Saturnite project that uses use rust: for real-world crates

**Root Cause:**
- Wrapper metadata JSON files were hand-written with invented function names that don't exist in actual crates
- Most Rust crates do not expose C-ABI functions - they use:
  - Macros (tracing::info!, anyhow!)
  - Traits (serde::Serialize, tokio::AsyncRead)
  - Generics (tokio::spawn<F, T>)
  - Async functions (async fn)
  - Feature-gated APIs (tokio::spawn requires rt feature)

**Evidence - Actual Compiler Errors:**

anyhow: 
  error[E0425]: cannot find function Result_ext_context in crate anyhow
  error[E0425]: cannot find function anyhow_macro in crate anyhow
  error[E0425]: cannot find function Error_new in crate anyhow
  error[E0425]: cannot find function Error_chain in crate anyhow

serde:
  error[E0425]: cannot find function ser_Serializer_new in crate serde
  error[E0425]: cannot find function de_Deserializer_new in crate serde

serde_json:
  error[E0425]: cannot find function Value_new_object in crate serde_json
  error[E0308]: mismatched types - expected &_, found *const i8
  error[E0308]: mismatched types - expected *const i8, found Result<String, Error>

tokio:
  error[E0425]: cannot find function runtime_Builder_new_multi_thread in crate tokio
  error[E0425]: cannot find function spawn in crate tokio (feature-gated behind rt)

tracing:
  error[E0423]: cannot find function info in crate tracing (it's a macro!)
  error[E0423]: cannot find function warn in crate tracing (it's a macro!)

tungstenite:
  error[E0425]: cannot find function Message_new_text in crate tungstenite
  error[E0277]: trait bound *const i8: AsyncRead not satisfied

uuid:
  error[E0425]: cannot find function Uuid_new_v4 in crate uuid

Impact:
- Complete blocker for any Saturnite project using use rust: with real crates
- The example_crate fixture works ONLY because it has hand-written C-ABI shims
- No real-world crate works without hand-written wrapper metadata

Proposed Fixes:
1. Automated wrapper-gen - Generate metadata from actual crate APIs using rustdoc --format json
2. Crate categorization - Only wrap crates with actual C-ABI exports; use native Saturnite stdlib for rest
3. Wrapper metadata validation - Validate metadata against actual crate at build time
4. Native stdlib - Implement json, uuid, error, time, log, http, websocket natively in Saturnite

Status: CRITICAL - BLOCKS ALL RUST INTEROP

---

## HIGH BUGS

### BUG-002: Wrapper Crate Workspace Detection Failure

Title: Generated wrapper crates incorrectly detected as part of parent Cargo workspace

Error:
error: current package believes it's in a workspace when it's not:
current:   .../hermes-transport/target/saturnite/wrappers/anyhow_wrapper/Cargo.toml
workspace: .../Saturnite/Cargo.toml

Fix Applied: Added [workspace] table to generated Cargo.toml in rust_wrapper.rs::generate_cargo_toml()

Status: HIGH - PARTIALLY FIXED (needs verification after wrapper rebuild)

### BUG-003: Wrapper Metadata Naming Mismatch

Title: Metadata file names don't match crate names (underscores vs hyphens)

Examples:
- tokio_tungstenite_saturnite.json vs crate tokio-tungstenite
- tracing_subscriber_saturnite.json vs crate tracing-subscriber

Fix Applied: Renamed files to match crate names exactly (tokio-tungstenite_saturnite.json, tracing-subscriber_saturnite.json)

Status: HIGH - FIXED (needs verification)

### BUG-004: Missing Wrapper Metadata for Some Crates

Title: Two crates had no metadata files at all

Missing:
- tokio-tungstenite_saturnite.json (was named tokio_tungstenite_saturnite.json)
- tracing-subscriber_saturnite.json (was named tracing_subscriber_saturnite.json)

Fix Applied: Created missing files with corrected names

Status: HIGH - FIXED (but metadata content still wrong - see BUG-001)

### BUG-005: Workspace Exclude Pattern Not Working

Title: Glob pattern hermes-transport/target/saturnite/wrappers/*_wrapper in workspace.exclude doesn't work

Fix Applied: Changed to explicit list of all 9 wrapper directories in Cargo.toml workspace.exclude

Status: HIGH - FIXED (needs verification after rebuild)

---

## MEDIUM BUGS

### BUG-006: No Automated Wrapper Metadata Generation

Title: No tool to generate wrapper metadata from actual crate APIs

Current: Manual JSON authoring required for each crate
Needed: saturn wrapper-gen command using rustdoc --format json

Status: MEDIUM - NOT STARTED

### BUG-007: No Wrapper Metadata Validation

Title: No validation that wrapper metadata matches actual crate exports

Needed: Build-time validation that all declared functions exist in crate

Status: MEDIUM - NOT STARTED

### BUG-008: No Crate Categorization for FFI Compatibility

Title: No system to categorize crates by FFI compatibility

Needed: Automatic classification:
- native - Has C-ABI exports (wrap directly)
- wrap_needed - Pure Rust but can write hand-written wrapper
- native_saturnite - Use native Saturnite stdlib instead
- unsupported - Async/macro/generic heavy (use native Rust)

Status: MEDIUM - NOT STARTED

---

## LOW BUGS

### BUG-009: No Wrapper Build Caching

Title: Wrapper crates rebuilt from scratch on every saturn install

Needed: Cache built staticlibs in target/saturnite/wrappers/<crate>/

Status: LOW - NOT STARTED

### BUG-010: No Wrapper Build Parallelization

Title: Wrapper crates built sequentially

Needed: Parallel builds with proper dependency ordering

Status: LOW - NOT STARTED

---

## FIX PRIORITY ORDER

### Phase 1: Unblock Development (Week 1)
1. BUG-001 - Write correct wrapper metadata for 3-4 core crates (anyhow, uuid, serde_json subset)
2. BUG-006 - Implement saturn wrapper-gen prototype using cargo doc --format json
3. BUG-006 - Add wrapper metadata validation at build time

### Phase 2: Architecture Fix (Week 2)
1. BUG-001 - Implement crate categorization system
2. BUG-001 - Start native Saturnite stdlib (json, uuid, error)
2. BUG-001 - Document don't wrap these crates list

### Phase 3: Tooling (Week 3)
1. BUG-009 - Wrapper build caching
2. BUG-010 - Parallel wrapper builds
3. BUG-007 - Metadata validation at build time

---

## CURRENT STATUS SUMMARY

| Bug | Status | Priority |
|-----|--------|----------|
| BUG-001: Wrapper metadata fundamentally wrong | CRITICAL - OPEN | 1 |
| BUG-002: Workspace detection | HIGH - Fixed (needs verify) | 2 |
| BUG-003: Naming mismatch | HIGH - Fixed (needs verify) | 2 |
| BUG-004: Missing metadata | HIGH - Fixed (content still wrong) | 2 |
| BUG-005: Workspace exclude glob | HIGH - Fixed (needs verify) | 2 |
| BUG-006: No auto wrapper-gen | MEDIUM - OPEN | 3 |
| BUG-007: No validation | MEDIUM - OPEN | 3 |
| BUG-008: No categorization | MEDIUM - OPEN | 3 |
| BUG-009: No caching | LOW - OPEN | 4 |
| BUG-010: No parallelization | LOW - OPEN | 4 |

---

## NEXT ACTIONS

1. Immediate: Mark BUG-001 as CRITICAL in tracking
2. This Week: Implement correct metadata for 3-4 core crates to unblock
2. This Week: Prototype saturn wrapper-gen prototype using cargo doc --format json
3. Before ChatGPT: Prepare summary of BUG-001 with concrete examples
3. Architecture Decision: Adopt hybrid approach (native Rust transport + Saturnite stdlib)

---

## FILES TO FIX FOR BUG-001 (Priority Order)

| Crate | Metadata File | Status |
|-------|--------------|--------|
| anyhow | anyhow_saturnite.json | Wrong functions |
| uuid | uuid_saturnite.json | Wrong functions |
| serde_json | serde_json_saturnite.json | Wrong functions + type mismatches |
| serde | serde_saturnite.json | Wrong functions |
| reqwest | reqwest_saturnite.json | Not tested |
| tokio | tokio_saturnite.json | Wrong functions + feature-gated |
| tokio-tungstenite | tokio-tungstenite_saturnite.json | Wrong functions + async bounds |
| tungstenite | tungstenite_saturnite.json | Wrong functions + async bounds |
| tracing | tracing_saturnite.json | Macros not functions |
| tracing-subscriber | tracing-subscriber_saturnite.json | Wrong functions |

---

## ARCHITECTURE DECISION NEEDED

Decision: Adopt hybrid approach for Hermes integration:
- Native Rust transport server (tokio + tungstenite + reqwest) - compiles today
2. Hermes adapter (Python) - already complete, WebSocket protocol
3. Saturnite stdlib - implement json, uuid, error, log natively
4. Wrapper system - only for C-libraries and simple crates with C-API

This is the only scalable path forward.

---

Document generated during Hermes Rank 2 implementation. Update as bugs are fixed.
