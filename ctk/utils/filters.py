"""Consolidated filtering module for CTK.

This module merges output_filter.py and patterns.py into a single cohesive
filtering pipeline with 4 phases: preprocess -> filter -> compress -> dedupe.
"""

import re
from collections import defaultdict
from difflib import SequenceMatcher

from ctk.utils.symbols import (
    GIT_STATUS_SYMBOLS,
    has_errors,
    symbolize_docker_state,
)

# =============================================================================
# Phase 1: Preprocessing
# =============================================================================


def preprocess(output: str) -> str:
    """Preprocess output to remove ANSI codes and normalize whitespace.

    This is the first pass that removes visual noise before category-specific filtering.
    """
    if not output:
        return output

    # Strip ANSI escape sequences (colors, cursor movement, etc.)
    output = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", output)
    # Strip ANSI private mode sequences (e.g., [?25h, [?25l)
    output = re.sub(r"\x1b\[\?[0-9;]*[a-zA-Z]", "", output)
    # Strip additional ANSI codes (OSC, etc.)
    output = re.sub(r"\x1b\][^\x07]*\x07", "", output)
    output = re.sub(r"\x1b[()][AB012]", "", output)
    # Strip spinner/progress characters
    output = re.sub(r"[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]", "", output)

    # Remove Unicode box drawing characters
    box_chars = "┌┐└┘│─├┤┬┴┼╭╮╯╰═║╔╗╚╝╠╣╦╩╬"
    for char in box_chars:
        output = output.replace(char, "")

    # Normalize trailing whitespace on each line
    lines = [line.rstrip() for line in output.split("\n")]

    # Collapse consecutive empty lines to single empty line
    return _collapse_empty_lines(lines)


def _collapse_empty_lines(lines: list[str]) -> str:
    """Collapse consecutive empty lines into a single empty line."""
    result = []
    prev_empty = False

    for line in lines:
        is_empty = not line.strip()
        if is_empty:
            if not prev_empty:
                result.append("")
            prev_empty = True
        else:
            result.append(line)
            prev_empty = False

    # Remove leading/trailing empty lines
    while result and not result[0].strip():
        result.pop(0)
    while result and not result[-1].strip():
        result.pop()

    return "\n".join(result)


# =============================================================================
# Phase 4: Deduplication
# =============================================================================


def _deduplicate_similar_lines(lines: list[str], threshold: float = 0.75) -> list[str]:
    """Deduplicate consecutive similar lines.

    Uses difflib to find lines that differ only slightly (timestamps, counters, etc.)
    and replaces runs of similar lines with a count.
    """
    if len(lines) <= 1:
        return lines

    result = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Skip empty lines
        if not line.strip():
            result.append(line)
            i += 1
            continue

        # Skip short lines (unlikely to be meaningful duplicates, avoid false positives)
        if len(line.strip()) < 15:
            result.append(line)
            i += 1
            continue

        # Find consecutive similar lines
        similar_group = [line]
        j = i + 1

        while j < len(lines):
            next_line = lines[j]
            if not next_line.strip():
                break
            if len(next_line.strip()) < 15:
                break

            # Calculate similarity
            ratio = SequenceMatcher(None, line, next_line).ratio()
            if ratio >= threshold:
                similar_group.append(next_line)
                j += 1
            else:
                break

        # If we found 3+ similar lines, compress them
        if len(similar_group) >= 3:
            # Output first line with count
            result.append(f"{line} [... {len(similar_group)} similar]")
            i = j
        else:
            # Output as-is
            result.extend(similar_group)
            i = j

    return result


# =============================================================================
# Phase 2: Skip Patterns
# =============================================================================

# Universal skip patterns - boilerplate that wastes tokens
SKIP_PATTERNS = [
    r"^\s*$",  # Empty lines (handled by preprocess, but catch-all)
    r"^=+$",  # Separator lines
    r"^-+$",  # Separator lines
    r"^\++$",  # Separator lines
    r"^\*+$",  # Separator lines
    r"^~+$",  # Separator lines
    r"^#+$",  # Separator lines
    # Progress and status messages
    r"^\s*(Using|Fetching|Downloading|Installing|Building|Compiling|Processing|Analyzing|Checking|Validating|Verifying|Resolving|Preparing|Generating|Creating|Updating|Removing|Cleaning|Unpacking|Configuring|Setting up|Fetching|Linking|Unpacking)",
    r"^\s*\d+%\s*\|.*\|",  # Progress bars
    r"^\s*\d+%\s+complete",  # Progress percentage
    r"^\s*\[\d+/\d+\]",  # Progress counters
    r"^\s*>\s*\d+(/\d+)?",  # npm progress
    # Log levels (noise)
    r"^\s*WARN\b",  # Warnings (with or without colon)
    r"^\s*INFO\b",  # Info logs
    r"^\s*DEBUG\b",  # Debug logs
    r"^\s*TRACE\b",  # Trace logs
    r"^\s*notice\b",  # Notice logs
    r"^\s*verbose\b",  # Verbose logs
    # Timing info
    r"^\s*Done in\s+[\d.]+[smh]?",  # Timing with optional unit
    r"^\s*Completed in\s+[\d.]+",
    r"^\s*Finished in\s+[\d.]+",
    r"^\s*Took\s+[\d.]+",
    r"^\s*Time:\s+[\d.]+",
    r"^\s*Duration:\s+[\d.]+",
    r"^\s*real\s+\d+m\d+",
    r"^\s*user\s+\d+m\d+",
    r"^\s*sys\s+\d+m\d+",
    # UI noise
    r"^\s*\.{3,}$",  # Ellipsis lines
    r"^\s*please wait",  # Waiting messages
    r"^\s*loading",  # Loading messages
    r"^\s*spinning up",  # Startup messages
    r"^\s*starting\s+",  # Startup messages
    r"^\s*initializing",  # Init messages
    r"^\s*running\s+",  # Running messages (usually noise)
    # Package manager noise
    r"^npm warn",
    r"^npm notice",
    r"^yarn warn",
    r"^pnpm warn",
    r"^warning:",
    r"^deprecation",
    r"^deprecated",
    r"up to date",
    r"already installed",
    r"nothing to do",
    r"no changes",
    r"skipping",
    r"^\s*ok\s*$",
    r"^\s*success\s*$",
    r"^\s*pass\s*$",
    r"^\s*passed\s*$",
    r"^\s*fail\s*$",
    r"^\s*failed\s*$",
    r"^\s*error:\s*$",
    # npm/pnpm specific
    r"^\s*funding\s+message",
    r"^\s*audited\b",
    r"^\s*packages?\s*:\s*\d+",
    r"^\s*Lockfile\s+is\s+up",
    r"^added\s+\d+\s+packages",
    r"^removed\s+\d+\s+packages",
    r"^changed\s+\d+\s+packages",
    r"^\d+\s+packages\s+are\s+looking\s+for\s+funding",
    # Build/test noise
    r"Compiling\s+",
    r"Finished\s+dev",
    r"Running\s+unittests",
    r"^\s*test\s+result:\s+ok",
    r"^\s*\d+\s+passed",
    r"^\s*\d+\s+tests?\s+ran",
    # Hints
    r"^See \`",
    r"^Run \`",
    r"^Try \`",
]

# Patterns to skip EXCEPT for git category (where we need to compact status lines)
GIT_SENSITIVE_PATTERNS = [
    r"^\s*(created|deleted|modified|changed|added|removed|updated|copied|moved|renamed):",
]

# Category-specific patterns
CATEGORY_PATTERNS = {
    "docker": [
        r"^\s*CONTAINER ID",
        r"^\s*IMAGE\s+COMMAND",
        r"^\s*NAMESPACE",
        r"^\s*NETWORK ID",
        r"^\s*VOLUME NAME",
    ],
    "docker-compose": [
        r"^\s*NAME\s+COMMAND",
        r"Network\s+\S+\s+created",
        r"Container\s+\S+\s+(Started|Created)",
        r"^\s*Attaching to",
        r"^\s*Creating",
        r"^\s*Starting",
    ],
    "nodejs": [
        r"^\s*up to date",
        r"^\s*audited",
        r"^\s*funding",
        r"^added \d+ packages",
        r"^removed \d+ packages",
        r"^changed \d+ packages",
        r"^\s*packages:",
        r"^\s*auditing",
        r"^\s*WARN\s+\d+\s+deprecated",
        r"^Progress:\s+resolved",
        r"^Done in\s+[\d.]+s",
        r"dependencies:\s*$",
        r"devDependencies:\s*$",
        r"^\s*Lockfile",
    ],
    "python": [
        r"^\s*==",
        r"^\s*---",
        r"^collected \d+ items",
        r"^=\d+ passed",
        r"^=\d+ failed",
        r"^=\d+ skipped",
        r"^\s*PASSED\s*\[",
        r"^\s*passed\s*$",
    ],
    "git": [
        r"^\s*$",
        r"^\s*On branch",
        r"^\s*Your branch",
    ],
}


# =============================================================================
# Phase 3: Category-Specific Compression
# =============================================================================


def compress_git_status(lines: list[str]) -> list[str]:
    """Compress git status output using symbol grouping.

    Groups files by status type:
        M:file1.ts,file2.ts,file3.ts
        A:file4.ts
        ?:untracked1,untracked2
    """
    result = []
    status_groups: dict[str, list[str]] = defaultdict(list)
    in_untracked = False

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue

        # Track sections
        if "Untracked files:" in line:
            in_untracked = True
            continue
        if (
            "Changes to be committed:" in line
            or "Changes not staged for commit:" in line
        ):
            in_untracked = False
            continue

        # Skip section headers and branch info
        if re.match(r"^(On branch|Your branch|nothing to|working tree)", line_stripped):
            continue

        # Remove usage hints
        line_clean = re.sub(r'\s*\(use "[^"]+".*\)', "", line_stripped)

        # Try to match status patterns
        matched = False
        for status, symbol in GIT_STATUS_SYMBOLS.items():
            if status in line_clean.lower():
                match = re.search(
                    rf"{re.escape(status)}\s+(.+)", line_clean, re.IGNORECASE
                )
                if match:
                    file_path = match.group(1).strip()
                    status_groups[symbol].append(file_path)
                    matched = True
                    break

        # Handle untracked files (indented lines in untracked section)
        if not matched and in_untracked:
            match = re.match(r"^\s{2,}(\S.*)$", line)
            if match:
                file_path = match.group(1).strip()
                status_groups["?"].append(file_path)

    # Format grouped output
    for symbol in ["M", "A", "D", "R", "C", "T", "?"]:
        if status_groups[symbol]:
            files = ",".join(status_groups[symbol])
            result.append(f"{symbol}:{files}")

    return result


def compress_git_log(lines: list[str]) -> list[str]:
    """Compress git log output to minimal format.

    Converts:
        abc1234567 Author Name <email@example.com> Date: 2024-01-15
            Commit message here that might be long

    To:
        abc1234 Author | Commit message here
    """
    result = []
    sha_pattern = re.compile(r"^([a-f0-9]{7,40})\s+(.+)$")

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue

        # Match commit lines: SHA + message
        match = sha_pattern.match(line_stripped)
        if match:
            sha = match.group(1)[:7]  # Truncate to 7 chars
            rest = match.group(2)

            # Remove author email if present
            rest = re.sub(r"<[^>]+>\s*", "", rest)

            # Remove Date: prefix
            rest = re.sub(r"Date:\s*[\d\-:]+\s*", "", rest)

            # Truncate long messages
            if len(rest) > 60:
                rest = rest[:57] + "..."

            result.append(f"{sha} {rest}")
            continue

        # Skip verbose headers
        if re.match(r"^(Author:|Date:|Merge:|Commit:)", line_stripped):
            continue

        # Keep other lines as-is (shortened)
        if line_stripped:
            result.append(line_stripped[:80])

    return result[:50]  # Limit output


def compress_git_diff(lines: list[str]) -> list[str]:
    """Compress git diff output to minimal format.

    Shows file changes as summary, keeps key hunks.
    """
    result = []
    file_summary: dict[str, dict[str, int]] = {}
    current_file = None
    in_hunk = False
    hunk_lines = 0

    for line in lines:
        # Track file changes
        if line.startswith("diff --git"):
            match = re.search(r"diff --git a/(.+?) b/(.+)$", line)
            if match:
                current_file = match.group(2)
                file_summary[current_file] = {"+": 0, "-": 0}
            continue

        if line.startswith("+++ b/") or line.startswith("--- a/"):
            continue

        # Count additions/deletions
        if current_file and current_file in file_summary:
            if line.startswith("+") and not line.startswith("+++"):
                file_summary[current_file]["+"] += 1
            elif line.startswith("-") and not line.startswith("---"):
                file_summary[current_file]["-"] += 1

        # Skip hunk headers but note we're in a hunk
        if line.startswith("@@"):
            in_hunk = True
            hunk_lines = 0
            continue

        # Limit hunk content shown
        if in_hunk:
            hunk_lines += 1
            if hunk_lines <= 3:  # Show first 3 lines of each hunk
                result.append(line.rstrip())
            continue

    # Build summary
    if file_summary:
        for file, stats in file_summary.items():
            plus = stats.get("+", 0)
            minus = stats.get("-", 0)
            result.insert(0, f"{file}: +{plus} -{minus}")

    return result[:30]  # Limit output


def compress_docker_output(lines: list[str]) -> list[str]:
    """Compress docker ps output to minimal format.

    Converts:
        abc123456789   nginx:latest   Up 2 hours   0.0.0.0:80->80/tcp   web-server

    To:
        abc1234 nginx U2h 80 web
    """
    result = []

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue

        # Skip headers
        if re.match(
            r"^\s*(CONTAINER ID|REPOSITORY|NETWORK ID|VOLUME NAME|IMAGE\s+COMMAND)",
            line_stripped,
        ):
            continue

        # Try to parse docker ps format
        parts = re.split(r"\s{2,}", line_stripped)

        if len(parts) >= 5:
            # Extract container ID (truncate to 7 chars)
            container_id = parts[0][:7] if len(parts[0]) >= 7 else parts[0]

            # Extract image (remove tag, truncate)
            image = parts[1].split(":")[0] if ":" in parts[1] else parts[1]
            if len(image) > 15:
                image = image[:12] + "..."

            # Extract status
            status_raw = parts[4] if len(parts) > 4 else ""
            status = symbolize_docker_state(status_raw)

            # Extract ports and name (last two columns typically)
            ports = ""
            name = parts[-1]

            if len(parts) >= 7:
                ports_raw = parts[-2]
                # Compact port format: 0.0.0.0:80->80/tcp -> 80
                port_match = re.search(r"0\.0\.0\.0:(\d+)->", ports_raw)
                if port_match:
                    ports = port_match.group(1)
                elif re.search(r"->", ports_raw):
                    # Other port format, extract host port
                    port_match = re.search(r":(\d+)->", ports_raw)
                    if port_match:
                        ports = port_match.group(1)

            # Build compressed line
            if ports and ports != name:
                result.append(f"{container_id} {image} {status} {ports} {name}")
            else:
                result.append(f"{container_id} {image} {status} {name}")
        else:
            # Non-standard format - just truncate IDs
            compressed = re.sub(
                r"\b([a-f0-9]{12,})\b", lambda m: m.group(1)[:7], line_stripped
            )
            if compressed:
                result.append(compressed)

    return result


def compress_pytest_output(lines: list[str]) -> list[str]:
    """Compress pytest output to failures and summary only.

    Converts verbose output to:
        FAIL:test_file.py::test_name
        FAIL:test_file.py::test_other
        48p 2f | 3.42s
    """
    result = []
    failures = []
    summary = {"passed": 0, "failed": 0, "error": 0, "skipped": 0, "duration": ""}
    in_failure = False

    for line in lines:
        # Detect failures
        if "FAILED" in line or "ERROR" in line:
            in_failure = True
            # Extract test name from FAILED line
            match = re.search(r"(tests?[/\w_.]+\.py)::(\w+)", line)
            if match:
                file_path = match.group(1)
                test_name = match.group(2)
                failures.append(f"FAIL:{file_path}::{test_name}")
            else:
                failures.append(line.strip())
            continue

        # Collect failure context (tracebacks, assertions)
        if in_failure:
            if line.strip() and not line.startswith(" "):
                in_failure = False

        # Skip passing tests and progress
        if "PASSED" in line:
            continue
        if re.match(r"^tests?[/\w_.]+\s*\.+\s*\[", line):
            continue
        if re.match(r"^[\w/_.\s]+\[\s*\d+%", line):
            continue

        # Extract summary info
        if "passed" in line.lower():
            match = re.search(r"(\d+)\s+passed", line)
            if match:
                summary["passed"] = int(match.group(1))
        if "failed" in line.lower():
            match = re.search(r"(\d+)\s+failed", line)
            if match:
                summary["failed"] = int(match.group(1))
        if "error" in line.lower():
            match = re.search(r"(\d+)\s+error", line)
            if match:
                summary["error"] = int(match.group(1))
        if "skipped" in line.lower():
            match = re.search(r"(\d+)\s+skipped", line)
            if match:
                summary["skipped"] = int(match.group(1))
        if re.search(r"in\s+[\d.]+s", line):
            match = re.search(r"in\s+([\d.]+)s", line)
            if match:
                summary["duration"] = match.group(1)

    # Build output
    result.extend(failures)

    # Add summary line if we have results
    if summary["passed"] or summary["failed"]:
        parts = []
        if summary["passed"]:
            parts.append(f"{summary['passed']}p")
        if summary["failed"]:
            parts.append(f"{summary['failed']}f")
        if summary["error"]:
            parts.append(f"{summary['error']}e")
        if summary["skipped"]:
            parts.append(f"{summary['skipped']}s")

        summary_line = " ".join(parts)
        if summary["duration"]:
            summary_line += f" | {summary['duration']}s"
        result.append(summary_line)

    return result


def compress_nodejs_output(lines: list[str]) -> list[str]:
    """Compress npm/pnpm output to minimal format.

    Converts:
        added 25 packages, removed 3 packages, changed 12 packages in 5.2s

    To:
        +25 -3 ~12 | 5.2s
    """
    result = []
    package_lines: list[str] = []
    summary = {"added": 0, "removed": 0, "changed": 0, "duration": ""}

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue

        # Extract package change counts from summary line
        if re.search(r"added\s+\d+", line_stripped, re.IGNORECASE):
            match = re.search(r"added\s+(\d+)", line_stripped, re.IGNORECASE)
            if match:
                summary["added"] = int(match.group(1))
        if re.search(r"removed\s+\d+", line_stripped, re.IGNORECASE):
            match = re.search(r"removed\s+(\d+)", line_stripped, re.IGNORECASE)
            if match:
                summary["removed"] = int(match.group(1))
        if re.search(r"changed\s+\d+", line_stripped, re.IGNORECASE):
            match = re.search(r"changed\s+(\d+)", line_stripped, re.IGNORECASE)
            if match:
                summary["changed"] = int(match.group(1))

        # Extract duration
        if re.search(r"in\s+[\d.]+s?", line_stripped):
            match = re.search(r"in\s+([\d.]+)s?", line_stripped)
            if match:
                summary["duration"] = match.group(1)

        # Collect individual package lines
        if re.match(r"^\s*[+\-~]\s+@?[\w/-]+\s*[\d.]+", line_stripped):
            package_lines.append(line_stripped)
            continue

        # Skip noise
        if re.match(
            r"^\s*(Progress:|packages:|audited|auditing|WARN|Done in)",
            line_stripped,
            re.IGNORECASE,
        ):
            continue
        if re.match(
            r"^\s*(dependencies|devDependencies):", line_stripped, re.IGNORECASE
        ):
            continue

    # Build output
    if summary["added"] or summary["removed"] or summary["changed"]:
        parts = []
        if summary["added"]:
            parts.append(f"+{summary['added']}")
        if summary["removed"]:
            parts.append(f"-{summary['removed']}")
        if summary["changed"]:
            parts.append(f"~{summary['changed']}")

        summary_line = " ".join(parts)
        if summary["duration"]:
            summary_line += f" | {summary['duration']}s"
        result.append(summary_line)

    # Add first few package lines if many packages changed
    if package_lines and len(package_lines) <= 3:
        result.extend(package_lines)
    elif package_lines:
        result.append(package_lines[0])
        result.append(f"... {len(package_lines) - 1} more")

    return result


# Additional compression functions for files and network categories


def _compress_ls_output(lines: list[str]) -> list[str]:
    """Compress ls -l output to minimal format."""
    result = []

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue

        # Skip total line
        if line_stripped.startswith("total "):
            continue

        # Try to parse ls -l format (permissions, links, owner, group, size, date, name)
        parts = line_stripped.split()
        if len(parts) >= 6:
            perms = parts[0]
            # Compact permissions: -rw-r--r-- -> -rw
            compact_perms = perms[0] + perms[1:3] if len(perms) >= 4 else perms

            # Size is typically at index 4
            size = parts[4] if len(parts) > 4 else ""

            # Compact size
            try:
                size_int = int(size)
                if size_int >= 1024 * 1024:
                    size = f"{size_int / (1024 * 1024):.0f}M"
                elif size_int >= 1024:
                    size = f"{size_int / 1024:.0f}K"
            except ValueError:
                pass

            # Name is the last part
            name = parts[-1] if parts else ""

            result.append(f"{compact_perms} {size} {name}")
        else:
            # Short format - just keep filename
            if line_stripped:
                result.append(line_stripped)

    return result


def _compress_grep_output(lines: list[str]) -> list[str]:
    """Compress grep output to minimal file:line format."""
    result = []
    file_counts: dict[str, int] = {}

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue

        # Match grep output: file:line:content or file:content
        match = re.match(r"^([^:]+):(\d+)?(:|$)", line_stripped)
        if match:
            file_path = match.group(1)
            line_num = match.group(2)

            if line_num:
                # Track file occurrences
                file_counts[file_path] = file_counts.get(file_path, 0) + 1
                result.append(f"{file_path}:{line_num}")
            else:
                result.append(file_path)
        else:
            result.append(line_stripped)

    # If many matches in same file, aggregate
    if file_counts:
        max_count = max(file_counts.values())
        if max_count > 5:
            # Summarize by file
            summarized = []
            for file_path, count in file_counts.items():
                if count > 1:
                    summarized.append(f"{file_path}:[{count} matches]")
                else:
                    summarized.append(file_path)
            return summarized[:10]  # Limit output

    return result[:50]  # Limit output


def _compress_find_output(lines: list[str]) -> list[str]:
    """Compress find output by shortening paths and grouping."""
    result = []
    dir_counts: dict[str, int] = {}

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue

        # Remove leading ./
        path = re.sub(r"^\./", "", line_stripped)

        # Track directory for potential aggregation
        dir_name = "/".join(path.split("/")[:-1]) if "/" in path else ""
        if dir_name:
            dir_counts[dir_name] = dir_counts.get(dir_name, 0) + 1

        result.append(path)

    # If many files in same directory, aggregate
    if dir_counts:
        max_count = max(dir_counts.values())
        if max_count > 10:
            # Show directory with count instead of individual files
            aggregated = []
            shown_dirs: set[str] = set()
            for path in result:
                dir_name = "/".join(path.split("/")[:-1]) if "/" in path else ""
                if dir_name in dir_counts and dir_counts[dir_name] > 10:
                    if dir_name not in shown_dirs:
                        aggregated.append(
                            f"{dir_name}/ [...{dir_counts[dir_name]} files]"
                        )
                        shown_dirs.add(dir_name)
                else:
                    aggregated.append(path)
            return aggregated[:20]

    return result[:50]  # Limit output


def _compress_files_output(lines: list[str]) -> list[str]:
    """Compress file command output based on content."""
    # Detect output type
    text = "\n".join(lines)

    # Check for ls -l format
    if re.search(r"^[d\-l][rwx\-]{9}\s", text, re.MULTILINE):
        return _compress_ls_output(lines)

    # Check for grep format (file:line:content)
    if re.search(r"^[^:]+:\d+:", text, re.MULTILINE):
        return _compress_grep_output(lines)

    # Check for find format (paths)
    if re.search(r"^(\./)?[\w/_.\-]+$", text, re.MULTILINE):
        return _compress_find_output(lines)

    # Default - just limit output
    return lines[:50]


def _compress_curl_output(lines: list[str]) -> list[str]:
    """Compress curl output to essential info."""
    result = []
    body_lines: list[str] = []

    for line in lines:
        line_stripped = line.strip()

        # Skip progress/curl verbose output
        if re.match(r"^\s*[%*]\s+", line):
            continue
        if re.match(r"^\s*\d+\s+\d+\s+\d+", line):
            continue
        if re.match(r"^\s*0\s+0\s+0", line):
            continue
        if re.match(r"^\s*(Trying|Connected|TLS|SSL|ALPN)", line):
            continue
        if re.match(r"^>\s+(Host|User-Agent|Accept|Content-Type)", line):
            continue
        if re.match(r"^<\s+(Date|Server|Content-Type|Transfer-Encoding)", line):
            continue

        # Keep HTTP status line
        if re.match(r"^<\s+HTTP", line):
            # Extract status code
            match = re.search(r"HTTP/[\d.]+\s+(\d+)", line)
            if match:
                result.append(f"HTTP:{match.group(1)}")
            continue

        # Collect body (non-header lines)
        if line_stripped and not line.startswith("<") and not line.startswith(">"):
            body_lines.append(line_stripped)

    # Add truncated body
    if body_lines:
        if len(body_lines) > 10:
            result.extend(body_lines[:5])
            result.append(f"... [{len(body_lines) - 5} more lines]")
        else:
            result.extend(body_lines)

    return result


def _compress_wget_output(lines: list[str]) -> list[str]:
    """Compress wget output to essential info."""
    result = []

    for line in lines:
        line_stripped = line.strip()

        # Skip progress
        if re.match(r"^\s*\d+\s+\d+", line):
            continue
        if re.match(r"^\s*%.*%", line):
            continue
        if re.match(r"^\s*(Saving|Resolving|Connecting|HTTP)", line):
            # Extract key info
            match = re.search(r"HTTP/\S+\s+(\d+)", line)
            if match:
                result.append(f"HTTP:{match.group(1)}")
            continue

        # Keep saved message
        if "saved" in line_stripped.lower():
            match = re.search(
                r"saved\s+\[.*\]\s*(.+\.?\s*)?", line_stripped, re.IGNORECASE
            )
            if match:
                result.append(f"saved:{match.group(1) or 'done'}")
            continue

        if line_stripped:
            result.append(line_stripped)

    return result[:10]


def _compress_network_output(lines: list[str]) -> list[str]:
    """Compress network command output."""
    text = "\n".join(lines)

    # Detect curl vs wget by content
    if re.search(r"^(<|>|\*|%|Trying|Connected)", text, re.MULTILINE):
        return _compress_curl_output(lines)

    if re.search(r"(Saving|Resolving|Connecting).*wget", text, re.IGNORECASE):
        return _compress_wget_output(lines)

    # Default - just limit and clean
    return [line.rstrip() for line in lines if line.strip()][:20]


# Compressor registry
_COMPRESSORS = {
    "git": compress_git_status,
    "git-log": compress_git_log,
    "git-diff": compress_git_diff,
    "docker": compress_docker_output,
    "python": compress_pytest_output,
    "nodejs": compress_nodejs_output,
    "files": _compress_files_output,
    "network": _compress_network_output,
}


def _matches_expected_format(lines: list[str], category: str) -> bool:
    """Check if output matches expected format for the category."""
    if not lines:
        return False

    text = "\n".join(lines)

    if category == "git":
        return bool(
            re.search(
                r"(modified|deleted|new file|On branch|Untracked)", text, re.IGNORECASE
            )
        )
    elif category == "git-log":
        return bool(re.search(r"^[a-f0-9]{7,40}\s+", text, re.MULTILINE))
    elif category == "git-diff":
        return bool(re.search(r"^(diff --git|@@|[\+\-]{3})", text, re.MULTILINE))
    elif category == "docker":
        return bool(re.search(r"(CONTAINER ID|[a-f0-9]{12,}\s+\w+)", text))
    elif category == "python":
        return bool(
            re.search(
                r"(PASSED|FAILED|collected|test session|passed.*failed)",
                text,
                re.IGNORECASE,
            )
        )
    elif category == "nodejs":
        return bool(
            re.search(r"(added|removed|changed|packages|npm|pnpm)", text, re.IGNORECASE)
        )
    elif category == "files":
        return bool(
            re.search(r"([d\-l][rwx\-]{9}|^\.?/?[\w/_.\-]+$|:\d+:)", text, re.MULTILINE)
        )
    elif category == "network":
        return bool(
            re.search(r"(HTTP|curl|wget|Connecting|Resolving)", text, re.IGNORECASE)
        )

    return True  # Assume valid for unknown categories


def _compress_patterns(lines: list[str], category: str) -> list[str]:
    """Apply pattern-based compression for maximum token savings."""
    if not lines:
        return lines

    # Safety: Check for errors - if found, return with minimal processing
    if has_errors(lines):
        # Keep errors verbatim, just clean up whitespace
        return [line.rstrip() for line in lines if line.strip()]

    # Apply category-specific compression
    compressor = _COMPRESSORS.get(category)
    if compressor:
        return compressor(lines)

    # No compression for other categories - return as-is
    return lines


# =============================================================================
# Light Filter for Error Output
# =============================================================================


def _light_filter(lines: list[str], _category: str) -> str:
    """Light filtering for error output - preserves all error information."""
    result = []

    for line in lines:
        line_stripped = line.rstrip()
        if line_stripped:
            result.append(line_stripped)

    return "\n".join(result)


# =============================================================================
# Nested Category Detection
# =============================================================================


def _detect_nested_category(output: str, primary_category: str) -> str:
    """Detect if output matches a different category than the command.

    Used for compound commands like 'docker compose exec ... npm run build'
    where the output is actually npm/vitest output, not docker output.
    """
    if not output:
        return primary_category

    text = output[:2000]  # Check first 2000 chars only

    # Vitest/Jest test output patterns
    if re.search(r"(PASS|FAIL)\s+[\w/]+\.test\.(ts|js|vue)", text):
        return "vitest"
    if re.search(r"Test Files:\s+\d+", text):
        return "vitest"

    # npm/pnpm build output
    if re.search(r"(webpack|vite|esbuild).*building", text, re.IGNORECASE):
        return "nodejs"
    if re.search(r"built in [\d.]+(ms|s)", text, re.IGNORECASE):
        return "nodejs"

    # Python/pytest output inside docker
    if re.search(r"(PASSED|FAILED|test session)", text):
        return "python"
    if re.search(r"pytest", text, re.IGNORECASE):
        return "python"

    # Alembic migration output
    if re.search(r"INFO\s+\[alembic", text):
        return "alembic"

    return primary_category


# =============================================================================
# Main Filter Pipeline
# =============================================================================


def filter_output(output: str, category: str) -> str:
    """Apply aggressive output filtering based on category to maximize token savings.

    Processing pipeline:
    1. Preprocess: Strip ANSI codes, normalize whitespace
    2. Filter: Remove boilerplate lines based on category
    3. Symbolize & Pattern Compress: Apply symbol substitution and pattern compression
    4. Deduplicate: Compress similar consecutive lines
    """
    if not output:
        return output

    # Phase 1: Preprocess
    output = preprocess(output)

    lines = output.split("\n")

    # Safety: Check for errors - if found, use light filtering only
    if has_errors(lines):
        return _light_filter(lines, category)

    # Detect nested category for compound commands (e.g., docker compose exec ... npm)
    effective_category = _detect_nested_category(output, category)

    filtered_lines = []

    # Combine patterns for Phase 2 - use effective_category
    patterns = SKIP_PATTERNS + CATEGORY_PATTERNS.get(effective_category, [])

    # For git category, don't use git_sensitive_patterns (we need to compact those lines)
    if effective_category != "git":
        patterns = patterns + GIT_SENSITIVE_PATTERNS

    for line in lines:
        skip = False
        for pattern in patterns:
            if re.search(pattern, line, re.IGNORECASE):
                skip = True
                break
        if not skip:
            filtered_lines.append(line)

    # Phase 3: Symbolize & Pattern Compress (for supported categories)
    if effective_category in _COMPRESSORS:
        if _matches_expected_format(filtered_lines, effective_category):
            compressed = _compress_patterns(filtered_lines, effective_category)
            # Verify we got meaningful output
            if compressed:
                result = "\n".join(compressed)
                result = _collapse_empty_lines(result.split("\n"))
                return result

    # Phase 4: Deduplicate similar lines (fallback path)
    filtered_lines = _deduplicate_similar_lines(filtered_lines)

    result = "\n".join(filtered_lines)

    # Final cleanup
    result = _collapse_empty_lines(result.split("\n"))

    return result
