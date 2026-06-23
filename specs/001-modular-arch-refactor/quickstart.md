# Quickstart: Modular Architecture Refactor Validation

## Prerequisites

- Python 3.11+
- Dependencies installed: `pip install rich httpx playwright beautifulsoup4 lxml pycryptodome pytest pytest-asyncio respx`
- Playwright browsers: `playwright install chromium`

## Validation Scenarios

### Scenario 1: No Regressions in CLI Commands

```bash
# Capture pre-refactor output (baseline)
pyanime search "One Piece" --json > baseline_search.json
pyanime --help > baseline_help.txt

# After each layer extraction, compare output
pyanime search "One Piece" --json > refactored_search.json
diff baseline_search.json refactored_search.json
# Expected: no differences

pyanime --help > refactored_help.txt
diff baseline_help.txt refactored_help.txt
# Expected: no differences
```

### Scenario 2: Provider Interface Works

```bash
# Run existing provider tests
pytest tests/providers/ -v
# Expected: all existing search + episode tests pass
```

### Scenario 3: New Provider via Interface

```bash
# Simulate adding a provider via the registry
pytest tests/integration/test_provider_registry.py -v
# Expected: mock provider registered and discoverable
```

### Scenario 4: Layer Isolation

```bash
# Test each layer independently
pytest tests/providers/ -v           # Only provider tests
pytest tests/cache/ -v               # Only cache tests
pytest tests/playback/ -v            # Only playback tests
pytest tests/db/ -v                  # Only DB layer tests
# Expected: each suite passes independently with minimal mocking
```

### Scenario 5: Backward-Compatible Shims

```python
# In Python shell or test:
from scraping import search_anime3rb_async  # Old import path
from src.providers.anime3rb import search_anime3rb_async  # New import path
# Both import the same function — no importer changes needed
```

## Expected Outcomes

| Scenario | Pass Condition |
|----------|---------------|
| No regressions | All CLI commands produce identical output to baseline |
| Provider interface | Existing scraping functionality preserved |
| New provider | Registry discovers and routes to new provider |
| Layer isolation | Each test suite passes independently |
| Backward compat | Old import paths continue to work |
