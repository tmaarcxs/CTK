# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CTK (Claude Token Killer) is a CLI proxy that filters and compacts command output to save tokens (60-90% savings). It works as a Claude Code plugin via hooks that rewrite commands (e.g., `git status` → `ctk git status`).

## Development Commands

```bash
# Install in editable mode
pip install -e .

# Run all tests
python3 -m pytest tests/ -v

# Run specific test file
python3 -m pytest tests/test_cli.py -v

# Run specific test class
python3 -m pytest tests/test_cli.py::TestFlagPassthrough -v

# Lint
python3 -m ruff check ctk/ tests/

# Format
python3 -m black ctk/ tests/

# Version check
python3 -m ctk --version
```

## Architecture

```
ctk/
├── cli.py              # Click CLI with all commands (~900 lines)
├── core/
│   ├── config.py       # YAML configuration management
│   ├── metrics.py      # SQLite metrics tracking (commands, tokens saved)
│   └── rewriter.py     # Command pattern matching and rewriting engine
├── utils/
│   ├── output_filter.py # 4-phase filtering: preprocess → skip patterns → compact → dedupe
│   └── tokenizer.py    # Token estimation for savings calculation
hooks/
├── hooks.json          # Claude Code hook registration (PreToolUse, SessionStart)
├── ctk-rewrite.sh      # Bash hook that rewrites commands before execution
└── session-start.sh    # Auto-updates CTK binary when plugin version differs
```

## Key Patterns

**Output Filtering Pipeline** (`output_filter.py`):
1. Preprocess: Strip ANSI codes, Unicode box chars, normalize whitespace
2. Skip patterns: Category-specific regex patterns to remove noise
3. Compact: Category-specific compacting (git status → `M file.ts`, pytest → failures only)
4. Dedupe: Similar consecutive lines replaced with counts

**Command Rewriting** (`rewriter.py`):
- `CommandCategory` dataclass defines patterns for each command type
- `should_rewrite_command()` checks if a command should be proxied through CTK
- Subcommand extractors handle complex commands like `docker compose exec`

**Metrics** (`metrics.py`):
- SQLite database at `~/.local/share/ctk/metrics.db`
- Tracks original tokens, filtered tokens, savings per command
- `ctk gain` command reads from this database

## Version Updates

When releasing a new version, update these files:
1. `ctk/cli.py` - `@click.version_option(version="X.Y.Z")`
2. `ctk/__init__.py` - `__version__ = "X.Y.Z"`
3. `pyproject.toml` - `version = "X.Y.Z"`
4. `.claude-plugin/plugin.json` - `"version": "X.Y.Z"`
5. `.claude-plugin/marketplace.json` - `"version": "X.Y.Z"`
6. `CHANGELOG.md` - Add new version section

Then: `git tag vX.Y.Z && git push origin main --tags`

## Flag Passthrough

All commands that accept arguments must have `context_settings=CONTEXT_SETTINGS` to pass flags through to the underlying command. See `CONTEXT_SETTINGS` in cli.py.
