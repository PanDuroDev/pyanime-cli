# Research: Modular Architecture Refactor

## 1. Layered Architecture Pattern for Python CLI Applications

### Decision
Use a **layered architecture** with four horizontal layers (providers, cache, playback, UI) plus shared infrastructure (db, config). Each layer exposes a public interface via Python `Protocol` classes. Layers communicate through defined contracts — never by importing internal implementation details.

### Rationale
- This matches the existing conceptual split (scraping, db, player, tui) while formalizing boundaries
- Protocol-based interfaces allow runtime substitutability without inheritance hierarchies
- Decouples layer internals from consumers — only the Protocol signature is the contract
- Enables isolated testing by mocking at the Protocol boundary

### Alternatives Considered
- **Hexagonal (ports-and-adapters)**: Over-engineered for a CLI tool with no external adapters beyond the existing providers
- **Microservices**: Completely inappropriate — single-user CLI application
- **Keep monolithic with better file splitting**: Doesn't enforce boundaries at the import level

## 2. Provider Interface Design

### Decision
Define a `SourceProvider` Protocol with methods: `search(query)`, `fetch_episodes(url)`, `resolve_stream(episode_info)`. Each provider is a stateless module implementing this interface. Provider registration is explicit — a registry dict maps provider IDs to provider instances.

### Rationale
- Stateless providers are simpler to test and compose
- Protocol (structural subtyping) avoids forcing an inheritance hierarchy
- Registry pattern allows dynamic discovery and addition of new providers
- Async methods throughout since all scraping is inherently async

### Alternatives Considered
- **Abstract base class (ABC)**: More rigid, enforces inheritance. Protocol is preferred for Python 3.11+.
- **Plugin-based discovery (entry_points)**: Over-engineered for a fixed set of providers. Can be added later if needed.

## 3. Backward-Compatible Shim Strategy

### Decision
Each refactored root-level module (`scraping.py`, `player.py`, `db.py`, `config.py`, `tui_layout.py`) becomes a thin shim that imports from the new package and re-exports all public names. This allows incremental refactoring — importers continue to work without changes until all are migrated.

### Rationale
- `from scraping import search_anime3rb_async` continues to work even after the implementation moves to `src/providers/anime3rb.py`
- Enables one-layer-at-a-time extraction without a big-bang rewrite
- Shims are temporary — they emit a `PendingDeprecationWarning` after all internal migrations are complete

### Alternatives Considered
- **Big-bang rewrite**: High risk of extended breakage; unacceptable per P1 requirement
- **Feature branches per layer**: More coordination overhead; shim approach is simpler

## 4. Async Testing Strategy

### Decision
Use `pytest-asyncio` for async test support. For provider tests, use `httpx`'s `AsyncClient` with `respx` (HTTP mock library) to test provider parsing logic without live network calls. Cache and DB tests use in-memory SQLite. Playback tests mock subprocess calls.

### Rationale
- `respx` intercepts HTTPX requests at the transport layer, making provider tests fast and deterministic
- In-memory SQLite (`:memory:`) allows cache/DB tests to run without filesystem state
- Subprocess mocking via `unittest.mock.patch` avoids actual player launches in tests
- All layer tests can run independently without integration dependencies

### Alternatives Considered
- **VCR.py for recording HTTP interactions**: Useful for integration tests but adds complexity for unit tests
- **Live network tests**: Too slow and unreliable for the red-green-refactor cycle
