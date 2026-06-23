# Implementation Plan: Modular Architecture Refactor

**Branch**: `001-modular-arch-refactor` | **Date**: 2026-06-22 | **Spec**: specs/001-modular-arch-refactor/spec.md

**Input**: Feature specification from `specs/001-modular-arch-refactor/spec.md`

## Summary

Refactor the monolithic `anime_cli.py` into a clean modular architecture with four separated layers: sources (provider scraping/stream resolution), UI (CLI/TUI rendering), caching (stream URL storage and retrieval), and playback control (player discovery, launch, progress tracking). The database layer is treated as shared infrastructure. All existing CLI commands and output formats must remain identical.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: rich, httpx, playwright, beautifulsoup4, lxml, pycryptodome

**Storage**: SQLite via sqlite3 (stdlib) — existing schema remains unchanged

**Testing**: pytest with pytest-asyncio for async tests

**Target Platform**: Windows (primary), Linux, macOS

**Project Type**: CLI application with Rich-based TUI components

**Performance Goals**: Zero regression in search speed, stream resolution time, and player launch latency. Layer isolation must not add measurable overhead (<5% total).

**Constraints**: All existing CLI commands (search, play, favorites, settings, library) and their output formats (text + JSON) must remain byte-identical where applicable. No user data loss during transition.

**Scale/Scope**: ~4500 lines across 7 source files. Refactoring is purely internal — no new user-facing features.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Compliance | Notes |
|-----------|-----------|-------|
| I. CLI-First Architecture | ✅ Pass | Refactoring preserves all CLI commands and output formats unchanged |
| II. Modular Library Design | ✅ Pass (Mandated) | This refactoring is the direct implementation of this principle |
| III. Test-First (NON-NEGOTIABLE) | ⚠️ Must verify | Tests must be written per layer before extraction begins |
| IV. Cross-Platform & Integration Testing | ✅ Pass | Integration tests required for each extracted layer |
| V. Observability & Simplicity | ✅ Pass | Existing `print_*` helpers and error handling patterns preserved |

**Gate Evaluation**: No violations. Principle II mandates this refactoring. Principle III requires test-first approach during implementation.

## Project Structure

### Documentation (this feature)

```text
specs/001-modular-arch-refactor/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 research
├── data-model.md        # Phase 1 data model
├── quickstart.md        # Phase 1 validation guide
├── contracts/           # Phase 1 interface contracts
│   └── provider-interface.md
└── tasks.md             # Phase 2 tasks
```

### Source Code (repository root)

```text
# Refactored layer packages under src/
src/
├── providers/           # Source provider layer
│   ├── __init__.py      # Provider interface + registry
│   ├── anime3rb.py      # Extracted from scraping.py
│   ├── witanime.py      # Extracted from scraping.py
│   ├── anineko.py       # Extracted from scraping.py
│   ├── hianime.py       # Extracted from scraping.py
│   └── 9anime.py        # Extracted from scraping.py
├── ui/                  # UI layer
│   ├── __init__.py      # Public UI interface
│   ├── cli.py           # CLI entry points (extracted from anime_cli.py)
│   └── tui.py           # TUI components (extracted from anime_cli.py + tui_layout.py)
├── cache/               # Caching layer
│   ├── __init__.py      # Cache interface
│   └── stream_cache.py  # Extracted from db.py (stream_cache tables)
├── playback/            # Playback control layer
│   ├── __init__.py      # Playback interface
│   ├── discovery.py     # Player discovery (from player.py)
│   ├── launch.py        # Player launch (from player.py)
│   └── progress.py      # Progress polling (from player.py)
├── db/                  # Database infrastructure (shared)
│   ├── __init__.py      # DB interface
│   └── core.py          # Extracted from db.py (favorites, history, accounts)
├── config/              # Configuration (shared)
│   └── __init__.py      # Extracted from config.py
├── anime_cli.py         # Shrunk to thin orchestrator + CLI entry
├── config.py            # Legacy — delegates to config/
├── db.py                # Legacy — delegates to db/ + cache/
├── player.py            # Legacy — delegates to playback/
├── scraping.py          # Legacy — delegates to providers/
└── tui_layout.py       # Legacy — delegates to ui/tui.py

tests/
├── providers/
├── ui/
├── cache/
├── playback/
├── db/
└── integration/
```

**Structure Decision**: Package-per-layer structure under `src/` with backward-compatible shim modules at the root to maintain import compatibility during incremental migration.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations — this refactoring is mandated by Principle II.
