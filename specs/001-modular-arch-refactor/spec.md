# Feature Specification: Modular Architecture Refactor

**Feature Branch**: `001-modular-arch-refactor`

**Created**: 2026-06-22

**Status**: Draft

**Input**: User description: "Refactor anime-cli into a modular architecture with separated layers for sources, UI, caching, and playback control"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Uninterrupted Experience During Refactoring (Priority: P1)

Existing users continue to use all CLI commands (search, play, favorites, history, settings) without any change in behavior, performance, or interface during and after the refactoring. The application structure is reorganized internally while the user-facing experience remains identical.

**Why this priority**: Maintaining trust and usability is the top priority. Any regression would break the core value proposition of the application.

**Independent Test**: Run all existing top-level CLI commands (search, direct play, library browsing, settings) and verify identical output and behavior compared to the pre-refactor version.

**Acceptance Scenarios**:

1. **Given** a user runs `pyanime search "One Piece"`, **When** the refactored code processes the search, **Then** results match pre-refactor output in both JSON and TUI modes.
2. **Given** a user plays an episode from search results, **When** the playback layer handles the request, **Then** the correct stream URL is resolved and the preferred player launches with the same arguments as before.
3. **Given** a user views their favorites list, **When** the UI layer fetches data from the cache and database layers, **Then** the same library entries and watch progress are displayed as pre-refactor.

---

### User Story 2 - Add New Streaming Source Without Touching Other Layers (Priority: P2)

A developer can add support for a new anime streaming website by implementing only the source provider interface, without modifying UI, caching, or playback code. The new source automatically appears in search results, episode listings, and stream resolution.

**Why this priority**: This is the primary motivation for the refactoring — reducing coupling so that each concern can evolve independently.

**Independent Test**: A developer implements a mock source provider that returns sample search results and stream URLs. Verify that the UI displays these results, the cache stores them, and playback can consume the URLs — all without changes outside the new source module.

**Acceptance Scenarios**:

1. **Given** a new source provider is registered through the defined interface, **When** the user performs a search, **Then** results from the new source appear alongside existing sources.
2. **Given** a user selects an episode from the new source, **When** the stream resolution workflow runs, **Then** the caching layer stores the resolved URL and playback control launches the player with it.

---

### User Story 3 - Isolated Layer Testing for Faster Debugging (Priority: P3)

Each architectural layer (sources, caching, playback) can be tested independently with minimal mocking, enabling developers to isolate and fix issues without running the full application.

**Why this priority**: Improves development velocity and reliability but is not immediately visible to end users.

**Independent Test**: Run the test suite for each layer independently (e.g., source provider tests, cache layer tests, playback controller tests) without starting the full CLI application.

**Acceptance Scenarios**:

1. **Given** a developer has identified a caching bug, **When** they run only the cache layer tests, **Then** the issue is reproduced and verified without needing to search or play media.
2. **Given** a playback control change is proposed, **When** playback tests pass in isolation, **Then** the developer has confidence the change is correct without manual end-to-end testing.

---

### Edge Cases

- What happens if a refactored source provider encounters a network error? The error must propagate to the UI layer in the same format as before, without crashing the application.
- How does the system handle cached data from the old monolithic code structure during the transition? A migration strategy must ensure no cached data is lost or corrupted.
- What happens if a third-party integration (AniList/MAL sync) relies on internal data formats that change during refactoring? Backward compatibility adapters must be provided.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a defined provider interface that all streaming source modules implement, enabling new sources to be added by writing only the provider module.
- **FR-002**: The system MUST separate user interface rendering (CLI/TUI output, input handling) from business logic (search orchestration, stream resolution, playback).
- **FR-003**: The caching layer MUST be independent from source providers and playback control, allowing cache strategy changes without affecting other layers.
- **FR-004**: The playback control layer MUST handle player discovery, launch, and progress tracking independently from UI rendering and source scraping.
- **FR-005**: All existing CLI commands and their output formats MUST remain unchanged after the refactoring.
- **FR-006**: Each architectural layer MUST have a well-defined public API surface documented in its module entry point.
- **FR-007**: Cross-layer communication MUST flow through defined interfaces only — no layer bypassing or direct imports across layer boundaries.
- **FR-008**: The database layer (favorites, watch history, progress, accounts) MUST be treated as a separate foundational layer with its own interface, accessible by but not owned by any single business layer.

### Key Entities *(include if feature involves data)*

- **Source Provider**: An abstraction for a streaming website that defines methods for search, episode listing, and stream URL resolution. Each provider implements this interface independently.
- **Layer Contract**: The formal interface (function signatures, data structures, error types) that defines how layers communicate. This includes the search result format, episode list format, stream URL format, and playback status format.
- **Cache Entry**: A stored mapping from (anime identifier + episode number) to resolved stream URL, with metadata about quality, provider, and timestamp.
- **Architecture Module**: A self-contained directory/package representing one architectural layer (sources, ui, cache, playback, db) with its own public API and internal implementation details.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All existing CLI commands produce identical output (text and JSON) compared to the pre-refactor version — verified by automated output comparison tests.
- **SC-002**: A new mock source provider can be added by a developer with no knowledge of UI, caching, or playback internals, following only the provider interface documentation — verified by a timed onboarding exercise.
- **SC-003**: Each layer's test suite runs independently and completes in under 30 seconds, with no dependency on other layers being present.
- **SC-004**: The number of circular dependency warnings in the codebase drops to zero after the refactoring.
- **SC-005**: No existing user data (favorites, watch history, account tokens, cache entries) is lost or corrupted during the refactoring transition.

## Assumptions

- The refactoring is purely internal — no new user-facing features are introduced as part of this work.
- The existing four architectural layers (sources, UI, caching, playback) align with the current `scraping.py`, `anime_cli.py` (UI/tui portions), `db.py` (stream cache), and `player.py` modules respectively.
- The database layer (`db.py`) is treated as infrastructure shared across layers and is not being fundamentally redesigned, only its interfaces are being formalized.
- The refactoring follows an incremental approach — each layer is extracted and tested individually before moving to the next, with the application remaining functional at each step.
- Existing configuration file format and database schema remain unchanged.
