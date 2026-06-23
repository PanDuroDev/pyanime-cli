---

description: "Task list for modular architecture refactor of anime-cli"
---

# Tasks: Modular Architecture Refactor

**Input**: Design documents from `specs/001-modular-arch-refactor/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/`, `tests/` at repository root
- All paths relative to repository root unless absolute

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create bare package structure and install dev tooling

- [ ] T001 Create `src/` package structure per implementation plan (src/providers/, src/ui/, src/cache/, src/playback/, src/db/, src/config/) with `__init__.py` files
- [ ] T002 [P] Add dev dependencies (pytest, pytest-asyncio, respx) to setup.py
- [ ] T003 [P] Create tests/conftest.py with shared fixtures for async testing and HTTPX mocking

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared infrastructure layers that all user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T004 Extract config module to `src/config/__init__.py` with backward-compatible shim in `config.py` (re-export all public names from src.config)
- [ ] T005 Extract DB infrastructure (favorites, watch history, accounts) to `src/db/core.py` and `src/db/__init__.py` with backward-compatible shim in `db.py` (re-export from src.db)

**Checkpoint**: Foundation ready — shared infra extracted, user story work can begin

---

## Phase 3: User Story 1 - Uninterrupted Experience During Refactoring (Priority: P1) 🎯 MVP

**Goal**: All existing CLI commands continue to work unchanged. Each layer is extracted incrementally with backward-compatible shims.

**Independent Test**: Run all top-level CLI commands (search, direct play, library, settings) and compare output against pre-refactor baseline — must be byte-identical.

- [ ] T006 [P] [US1] Extract provider layer: create `src/providers/__init__.py` with SourceProvider Protocol + registry, migrate `scraping.py` functions to `src/providers/anime3rb.py`, `src/providers/witanime.py`, `src/providers/anineko.py`, `src/providers/hianime.py`, `src/providers/9anime.py` — add backward-compatible shim in `scraping.py` (re-export from src.providers)
- [ ] T007 [P] [US1] Extract cache layer: create `src/cache/__init__.py` with StreamCache Protocol, migrate stream_cache functions from `db.py` to `src/cache/stream_cache.py` — update `db.py` shim to re-export from src.cache
- [ ] T008 [P] [US1] Extract playback layer: create `src/playback/__init__.py`, `src/playback/discovery.py`, `src/playback/launch.py`, `src/playback/progress.py` — migrate `player.py` functions — add backward-compatible shim in `player.py` (re-export from src.playback)
- [ ] T009 [US1] Extract UI layer: create `src/ui/__init__.py`, `src/ui/cli.py` (CLI entry points from anime_cli.py), `src/ui/tui.py` (TUI components from tui_layout.py + anime_cli.py) — add backward-compatible shim in `tui_layout.py`
- [ ] T010 [US1] Refactor `anime_cli.py` to thin orchestrator: delegate to src/ui/cli.py for entry point, src/providers/ for search/stream, src/cache/ for caching, src/playback/ for player launch — remove all extracted inline code
- [ ] T011 [US1] Run regression test: capture baseline output for all CLI commands (search, play, favorites, settings), run after extraction, diff against baseline — all outputs must be identical

**Checkpoint**: User Story 1 complete — all existing features work through new architecture, shims maintain backward compatibility

---

## Phase 4: User Story 2 - Add New Streaming Source Without Touching Other Layers (Priority: P2)

**Goal**: A developer can add a new source provider by implementing only the SourceProvider Protocol and registering it — no UI, cache, or playback changes needed.

**Independent Test**: Implement a mock provider that returns sample results. Verify search returns mock data, cache stores resolved URLs, playback launches from cached URLs — all without touching non-provider code.

- [ ] T012 [P] [US2] Formalize `SourceProvider` Protocol in `src/providers/__init__.py` with `search()`, `fetch_episodes()`, `resolve_stream()`, `resolve_stream_with_cookies()` methods
- [ ] T013 [P] [US2] Implement `ProviderRegistry` in `src/providers/__init__.py` with `register(provider)`, `get(provider_id)`, `get_all()` — populate registry at import time
- [ ] T014 [US2] Create mock provider at `tests/providers/test_mock_provider.py` that implements SourceProvider and registers via ProviderRegistry — verify it appears in search results
- [ ] T015 [US2] Update search orchestrator in `anime_cli.py` / `src/ui/cli.py` to use `ProviderRegistry.get_all()` instead of hardcoded async function calls

**Checkpoint**: User Story 2 complete — new source providers can be added by writing one module and registering it

---

## Phase 5: User Story 3 - Isolated Layer Testing for Faster Debugging (Priority: P3)

**Goal**: Each architectural layer has an independent test suite that can run in isolation with minimal mocking.

**Independent Test**: Run each layer's test suite independently (`pytest tests/providers/`, `pytest tests/cache/`, etc.) — all must pass without cross-layer dependencies.

- [ ] T016 [P] [US3] Create provider layer test suite in `tests/providers/` using respx to mock HTTPX transport — test search, episode fetch, and stream resolution for each provider
- [ ] T017 [P] [US3] Create cache layer test suite in `tests/cache/` using in-memory SQLite — test get/set/invalidate/prune operations
- [ ] T018 [P] [US3] Create playback layer test suite in `tests/playback/` using `unittest.mock.patch` for subprocess — test player discovery, launch, and progress tracking
- [ ] T019 [US3] Verify each test suite runs independently: `pytest tests/providers/ -v` (no cache/playback deps), `pytest tests/cache/ -v` (no provider/playback deps), `pytest tests/playback/ -v` (no provider/cache deps)

**Checkpoint**: User Story 3 complete — each layer testable in isolation, all under 30 seconds

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Cleanup, documentation, and final validation

- [ ] T020 [P] Add `PendingDeprecationWarning` to all backward-compatible shim modules (config.py, db.py, player.py, scraping.py, tui_layout.py) — warn on import, point consumers to new `src/` package paths
- [ ] T021 Run quickstart.md validation scenarios end-to-end — verify no regressions, provider interface works, layer isolation confirmed
- [ ] T022 Update AGENTS.md with final architecture reference and remove plan TODOs

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational — no dependencies on other stories
- **User Story 2 (Phase 4)**: Depends on Foundational + US1 (providers must be extracted before interface is formalized)
- **User Story 3 (Phase 5)**: Depends on Foundational + US1 (layers must exist before their tests)
- **Polish (Phase 6)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational — No dependencies on other stories
- **User Story 2 (P2)**: Depends on US1 — providers must be extracted before the interface can be formalized and registry added
- **User Story 3 (P3)**: Depends on US1 — layers must be extracted before isolation tests can be written

### Within Each User Story

- [P] tasks can run in parallel
- Implementation before integration verification
- Story complete before moving to next priority

### Parallel Opportunities

- T002 and T003 can run in parallel (Setup phase)
- T006, T007, T008 can run in parallel (US1 — provider, cache, playback are independent extractions)
- T012 and T013 can run in parallel (US2 — Protocol and Registry are independent)
- T016, T017, T018 can run in parallel (US3 — each test suite targets a different layer)

---

## Parallel Example: User Story 1

```bash
# Launch all layer extractions together (different files, no overlapping changes):
Task: "T006 Extract provider layer in src/providers/ + scraping.py shim"
Task: "T007 Extract cache layer in src/cache/ + update db.py shim"
Task: "T008 Extract playback layer in src/playback/ + player.py shim"

# After parallel extractions complete (sequential dependency):
Task: "T009 Extract UI layer in src/ui/ + tui_layout.py shim"
Task: "T010 Refactor anime_cli.py to thin orchestrator"
Task: "T011 Run regression test against baseline"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1 (extract all layers, maintain backward compatibility)
4. **STOP and VALIDATE**: Run regression test against baseline (T011)
5. Deploy/demo if ready — application behaves identically but is now modular

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 (all layers extracted, shims in place) → Regression pass → Deploy (MVP)
3. Add User Story 2 (provider interface + registry) → Mock provider works → Deploy
4. Add User Story 3 (isolated test suites) → All layer tests independent → Deploy
5. Polish → Deprecation warnings, documentation, final validation

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: T006, T009, T010 (provider + UI + orchestrator)
   - Developer B: T007, T012, T013 (cache + provider interface)
   - Developer C: T008, T014, T015 (playback + registry integration)
3. After US1 complete:
   - Developer A: Continue to US3 (test suites)
   - Developer B: Continue to US2 completion
4. Team completes Polish phase together

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Follow Red-Green-Refactor per constitution Principle III: write failing test first, implement, refactor
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
- All shim modules must re-export every public name from their new `src/` package to maintain `from module import fn` compatibility
