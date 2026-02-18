# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.2] - 2026-02-18

### Fixed

- **Flag passthrough** for all docker and git subcommands
  - Fixed missing `context_settings` on 20 commands
  - Docker: ps, images, logs, exec, run, build, network, volume, system
  - Git: status, diff, log, add, commit, push, pull, branch, remote, stash, tag
  - Commands like `ctk docker compose exec -T backend python test.py` now work correctly

### Added

- Comprehensive flag passthrough tests (16 new test cases)

## [1.1.1] - 2026-02-18

### Changed

- **Auto-update**: Plugin now automatically updates CTK binary when version changes
- Session-start hook checks plugin vs installed version and runs `pip install` if needed
- Updating the plugin in Claude Code will now update the binary on next session

## [1.1.0] - 2026-02-18

### Added

- **Enhanced CLI output optimization** for additional 15-25% token savings
  - Strip ANSI escape sequences (colors, cursor codes)
  - Remove Unicode box drawing characters
  - Deduplicate similar consecutive lines
  - Category-specific compacting (git status, pytest, docker)
  - Git status compact format: `modified: file.ts` → `M file.ts`
  - Pytest: removes passing tests, keeps failures with context
  - Docker: truncates container IDs to 7 chars

- **New commands**
  - `ctk pwd` - Print working directory
  - `ctk sed` - Stream editor with flag passthrough
  - `ctk jq` - JSON processor with flag passthrough
  - `ctk apt` - Package manager with flag passthrough
  - `ctk sqlite3` - SQLite database CLI with flag passthrough

- **Flag passthrough support** for all commands with arguments
  - Commands like `ctk curl -s -X GET ...` now work correctly
  - All commands accept native flags without errors

### Changed

- Extracted output filtering logic to `ctk/utils/output_filter.py` module

### Removed

- `ctk kubectl` command (low usage)
- `ctk cargo` command (low usage)
- `ctk go` command (low usage)

## [1.0.0] - 2026-02-17

### Added

- Initial release
- Token-optimized CLI proxy achieving 60-90% savings
- Docker commands: `ps`, `images`, `logs`, `exec`, `run`, `build`, `compose`
- Git commands: `status`, `diff`, `log`, `add`, `commit`, `push`, `pull`
- Python commands: `pytest`, `ruff`, `pip`
- Node.js commands: `npm`, `pnpm`, `vitest`, `tsc`, `lint`, `prettier`
- System commands: `ps`, `free`, `date`, `df`, `uname`, `hostname`, `uptime`, `env`, `whoami`, `id`
- File commands: `ls`, `tree`, `read`, `cat`, `grep`, `find`, `du`, `tail`, `wc`, `stat`, `file`
- Network commands: `curl`, `wget`, `ip`, `ss`, `ping`
- Meta commands: `gain`, `discover`, `proxy`, `config`
- GitHub CLI integration: `gh`
- Metrics tracking and analytics
- Claude Code hook integration for automatic command rewriting
- Plugin support via marketplace.json
