<!-- SPECKIT START -->
Active plan: specs/001-modular-arch-refactor/plan.md
Feature: Modular Architecture Refactor
For context about technologies, project structure, shell commands,
and other important information, read the active plan file.

## Goal

Complete a two-phase UI redesign: (Phase 1) restructure layout, remove ASCII logo, center all content vertically/horizontally based on terminal size, fix sizing/render, center all screens; (Phase 2) add smooth scroll transitions via Live loop interpolation.

## Constraints & Preferences

- All panels must center vertically and horizontally based on terminal window dimensions (width × height).
- Current logo removed entirely; app version/info moved to Settings → About.
- Smooth transitions between screens — no instant jumps, but also no `time.sleep()` (input must never block).
- Layout must be dynamic — no fixed-size panels, everything adapts to terminal size.
- Press `d` to toggle right-side context panel instead of always showing it.
- Work in two ordered phases: layout restructuring first, transitions second.

## Progress

### Done

- **Phase 1.1**: `make_logo()`, `make_status_bar()`, `make_ui()`, `print_logo()` deleted. App version shown in title `[dim]` and Settings → About.
- **Phase 1.2**: Status bar merged into single-line panel subtitle (` | 🎬 MPV (path)`).
- **Phase 1.3**: Vertical centering via `Align(renderable, align="center", vertical="middle", height=term_lines)`. Content now centers in the **middle** of the terminal, not the top.
- **Phase 1.4**: `max_visible` updated to `max(5, min(20, term_height - 12))` (was `term_height - 14` for logo header).
- **Phase 1.5**: Consistent padding `(1, 2)` across all panels (was mixed `(1, 3)`, `(1, 1)`, `(0, 2)`, `(1, 4)`). Dynamic widths: single panel `min(100, width-4)`, split 40/60 when details shown.
- **Phase 1.6**: `_show_details` toggle (`d` key) replaces auto-show context panel. Works in both `interactive_select` and `interactive_checklist`.
- **Phase 1.7**: All `clear_screen()` removed from settings handlers (`_handle_settings`, `_settings_player`, `_settings_search_sources`, `_settings_data_sync`, `_settings_appearance`). No more flicker.
- **Phase 1.8**: Dead code `make_ui()` detected and removed.
- **Phase 1.9**: About panel in Settings (version, config path, DB path, player status, AniList/MAL links, platform, Python version).
- **Phase 1.10**: Color contrast improved — item numbers use `THEME['fg']` instead of `THEME['dim']`; subtitles use `fg` instead of `dim`.
- **Phase 2**: Terminal-native smooth scroll animation (300ms cubic ease-out, 20 FPS, no `time.sleep()`). State-based interpolation via Live refresh loop: `_anim_active` flag interpolates `render_scroll` between old and new `scroll_offset`. Applied to UP/DOWN, `[`/`]`, `g`/`G` in both widgets.
- **`detect_layout_mode`**: Simplified to return `"NORMAL"` or `"MINIMAL"` (was `FULL`/`COMPACT`/`MINIMAL`).
- **Live refresh rate**: Increased from 10 to 20 FPS for smoother interpolation.
- **Bug fix**: `Align(..., horizontal=…)` → `Align(..., align=…)` (Rich API).
- **Bug fix**: `Panel(box=None, height=…)` crashes Rich — use `Align(renderable, height=…)` directly.
- **Bug fix**: `link_anilist_flow()` / `link_myanimelist_flow()` `NameError` → guarded with `try/except` showing "not yet implemented" message.
- **`__init__.py` exports**: Removed `make_logo`, `make_status_bar`, `make_ui`, `print_logo` from imports and `__all__`. Added `_settings_about`.
- **`_centered_message()` helper**: Wraps message + "Press any key" footer in centered Panel with vertical padding. Clears screen, shows panel, waits for key.
- **`_centered_prompt()` helper**: Shows centered Panel with prompt text, then `console.input()`. Returns `""` on Enter, `None` on Ctrl+C. Replaces `clear_screen()` + instructions + `prompt_input()` patterns.
- **Replaced all `prompt_input()` calls outside Live contexts**: search queries (3 calls), URL input (1), URL search (1), player args (1), config dir (1), download remove (1) — all now use `_centered_prompt()`.
- **Replaced all `print_warn/info/fail/ok + read_key()` patterns** (23 locations) with `_centered_message()`: search results, episode fetching, URL validation/parsing, scraping errors, AniList/MAL linking, export results, download manager — all now show a clean centered panel instead of inline message at bottom of leftover terminal content.
- **`_centered_status()` context manager**: Shows spinner + message in a centered Panel via `Live(transient=True)`. Accepts `icon="search"` or `icon="watch"`. Replaces all 8 `console.status()` calls (searching, loading episodes, syncing cookies, fetching lists) with centered Live contexts.
- **`_show_track_selector()` centered**: Replaced `console.clear()` + `console.print(panel)` + `console.print(hotkeys)` with `Align(Group(panel, hotkeys), align="center", vertical="middle", height=h)`. No more top-of-screen layout.
- **Scraping table centered**: `scraping.py` `make_scraping_table()` return wrapped in `Align(..., vertical="middle", height=terminal_lines)` so the live scraping progress table is vertically centered.
- **`interactive_checklist` fix**: No-details return was missing `align="center"` on outer `Align` (line 1142). Added it for consistency with `interactive_select` and details path.
- **`interactive_checklist` + `interactive_select`**: Both now match — `Align(Align.center(left_panel), align="center", vertical="middle", height=...)`.
- **Rich imports**: Added `Spinner` from `rich.spinner` and `contextlib` for `_centered_status` context manager.

### In Progress

- (none - all polish items complete)

### Blocked

- (none)

## Key Decisions

- Remove ASCII logo entirely rather than shrinking it; app info moves to Settings → About.
- Status bar merged into panel subtitle as single line (saves 3 vertical lines).
- `_show_details` toggled via `d` key instead of auto-detection based on terminal width/height.
- Terminal-native animation via Live state interpolation (no `time.sleep()`) — input is never blocked during transitions.
- `Align(height=terminal_lines)` for vertical centering instead of `Panel(box=None, height=…)` (the latter crashes Rich).
- `link_anilist_flow` / `link_myanimelist_flow` guarded with `try/except` and "not yet implemented" message — the functions were never defined (pre-existing bug).
- `clear_screen()` retained in `run_app()` between state machine transitions (provides clean slate) and in `_show_track_selector` (self-contained widget); removed from all settings handlers and message prompts (replaced by `_centered_message` / `_centered_prompt` which internally clear).
- Dead `make_ui()` function (never called) removed.
- `_centered_message()` wraps content in `Panel(Group(icon + msg + spacer), padding=(1, 3))` with vertical padding calculated as `max(0, (h - 8) // 2)`.
- `_centered_prompt()` reuses same centered layout but calls `console.input()` instead of `read_key()`.
- `_centered_status()` uses `Live(transient=True)` so the centered status disappears cleanly after the operation, returning to the previous screen state.
- `make_scraping_table()` return wrapped in `Align(..., vertical="middle", height=h)` — vertical centering requires `shutil.get_terminal_size()` called inside the function closure (terminal may resize).
- `_show_track_selector()` uses `Align(Group(...), height=h, vertical="middle")` — the hotkey bar is part of the Group so it stays adjacent to the panel, centered together.

## Next Steps

1. Run full test suite after all changes.

## Critical Context

- `Align.__init__()` does **not** accept `horizontal=` — use `align=` instead.
- `Panel(box=None, height=N)` crashes Rich — use `Align(renderable, height=N)` directly.
- `_centered_message()` calls `console.clear()` internally, which is fine for standalone messages shown between state machine transitions.
- `_centered_prompt()` does NOT clear the screen after the user types (the next state's `console.clear()` in `run_app()` handles that).
- `_centered_message()` calls `console.clear()` internally, which is fine for standalone messages shown between state machine transitions.
- `_centered_prompt()` does NOT clear the screen after the user types (the next state's `console.clear()` in `run_app()` handles that).
- `clear_screen()` is kept in `run_app()` (between state transitions) and `_show_track_selector()` (self-contained widget). Removed from all settings handlers and message prompts.
- All 40 cache + playback tests pass consistently. Provider tests depend on network access.

## Relevant Files

- **`src/ui/tui.py`** (~2431 lines): Target of all changes. Contains `interactive_select()`, `interactive_checklist()`, all settings handlers, `_centered_message()`, `_centered_prompt()`, etc.
- **`src/ui/__init__.py`**: Updated exports (removed dead functions, added `_settings_about`).
- **`src/ui/cli.py`**: Contains `link_anilist_flow = None`, `link_myanimelist_flow = None` (stubs).
- **`src/config/__init__.py`**: Theme constants (`THEME['fg']`, `THEME['dim']`, `THEME['accent']`, etc.).
- **`src/db/__init__.py`**: `save_account_token()`, `get_account_token()`, `remove_account()` — used by accounts integration menus.

## Commands

- Run all tests:      `pytest tests/ -v`
- Provider tests:     `pytest tests/providers/ -v`
- Cache tests:        `pytest tests/cache/ -v`
- Playback tests:     `pytest tests/playback/ -v`
<!-- SPECKIT END -->
