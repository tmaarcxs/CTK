"""Output filtering and optimization for LLM token savings."""

import re
from difflib import SequenceMatcher

from ctk.utils.patterns import compress_patterns, matches_expected_format
from ctk.utils.symbols import has_errors


def preprocess_output(output: str) -> str:
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
    return collapse_empty_lines(lines)


def collapse_empty_lines(lines: list[str]) -> str:
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


def deduplicate_similar_lines(lines: list[str], threshold: float = 0.75) -> list[str]:
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


def compact_git_status(output: str) -> str:
    """Compact git status output to short format.

    Converts:
        modified:   src/app.ts  ->  M src/app.ts
        deleted:    src/old.ts  ->  D src/old.ts
        new file:   src/new.ts  ->  A src/new.ts
        ?? file.txt             ->  ? file.txt
    """
    lines = output.split("\n")
    result = []

    # Status mapping
    status_map = {
        "modified:": "M",
        "deleted:": "D",
        "new file:": "A",
        "renamed:": "R",
        "copied:": "C",
        "type changed:": "T",
    }

    in_untracked = False

    for line in lines:
        # First, strip usage hints from any line
        line = re.sub(r'\s*\(use "[^"]+"\s+[^)]+\)', "", line)
        line = re.sub(r'\s*\(use "[^"]+"\)', "", line)

        # Track sections
        if "Changes to be committed:" in line:
            continue
        if "Changes not staged for commit:" in line:
            continue
        if "Untracked files:" in line:
            in_untracked = True
            continue

        compacted = False

        # Try to compact status lines
        for status, code in status_map.items():
            if status in line.lower():
                # Extract file path (everything after the status keyword)
                match = re.search(rf"{re.escape(status)}\s+(.+)", line, re.IGNORECASE)
                if match:
                    file_path = match.group(1).strip()
                    result.append(f"{code} {file_path}")
                    compacted = True
                    break

        # Handle untracked files (indented lines in untracked section)
        if not compacted and in_untracked:
            match = re.match(r"^\s{2,}(\S.*)$", line)
            if match:
                file_path = match.group(1).strip()
                result.append(f"? {file_path}")
                compacted = True

        if not compacted:
            # Remove branch info noise
            line = re.sub(r"^\s*On branch \S+\s*$", "", line)
            line = re.sub(r"^\s*Your branch is [^.]+\.\s*$", "", line)
            line = re.sub(r"^\s*nothing to commit,?\s*", "", line)
            line = re.sub(r"^\s*working tree clean\s*$", "", line)
            line = re.sub(r"^\s*\(.*\)\s*$", "", line)  # Remove parenthetical hints
            if line.strip():
                result.append(line)

    return "\n".join(result)


def is_pytest_output(output: str) -> bool:
    """Check if output looks like pytest output."""
    # Check for pytest-specific patterns that are unlikely in other output
    output_lower = output.lower()

    # Strong indicators - these are unique to pytest
    strong_indicators = [
        "test session starts",
        "collected",
        ".py::",  # test file pattern (e.g., test_file.py::test_name)
        "short test summary",
        "platform linux",  # pytest header
        "rootdir:",  # pytest config
        "cachedir:",  # pytest cache
    ]
    for indicator in strong_indicators:
        if indicator in output_lower:
            return True

    # Check for uppercase PASSED/FAILED (pytest format) with brackets or line patterns
    if re.search(r"\bPASSED\b", output) or re.search(r"\bFAILED\b", output):
        return True

    # Check for pytest summary format: "3 passed, 2 failed" or "X failed, Y passed"
    if re.search(r"\d+\s+(passed|failed)", output_lower):
        return True

    # Check for pytest progress pattern: dots and F/E for failures
    if re.search(r"[.FE]{10,}", output):
        return True

    return False


def compact_pytest_output(output: str) -> str:
    """Compact pytest output - remove passing tests, keep failures and summary.

    If output doesn't look like pytest, return it unchanged to preserve data.
    """
    # Safety: if this doesn't look like pytest output, return unchanged
    if not is_pytest_output(output):
        return output

    lines = output.split("\n")
    result = []
    in_failure = False
    failure_context = []
    has_failures = False

    for line in lines:
        # Always keep failures and errors
        if "FAILED" in line or "ERROR" in line or "error:" in line.lower():
            in_failure = True
            has_failures = True
            failure_context = [line]
            result.append(line)
        elif in_failure:
            # Keep failure context (traceback, assertion details)
            failure_context.append(line)
            if line.strip() and not line.startswith(" "):
                # Non-indented line ends failure context
                in_failure = False
            if in_failure or line.startswith(("assert", "E ", ">", "FAILED", "ERROR")):
                result.append(line)

        # Skip passing test lines
        elif "PASSED" in line:
            continue
        # Skip progress lines with dots
        elif re.match(r"^tests/[\w/_.]+\s*\.+\s*\[\s*\d+%", line):
            continue
        # Skip lines that are just dots and progress
        elif re.match(r"^[\w/_.\s]+\[\s*\d+%\s*\]", line):
            # Only keep if it has failures info
            if "FAILED" not in line and "ERROR" not in line:
                continue
        # Skip separator lines
        elif re.match(r"^=+$", line.strip()):
            continue
        # Skip collection lines
        elif line.strip().startswith("collected"):
            continue
        # Skip session start lines
        elif "test session starts" in line.lower():
            continue
        # Keep summary lines (only if failures exist or it's an error summary)
        elif has_failures or "failed" in line.lower() or "error" in line.lower():
            if line.strip() and "passed" not in line.lower():
                result.append(line)

    return "\n".join(result)


def compact_docker_output(output: str) -> str:
    """Compact docker output to essential info only.

    Converts verbose output like:
        abc123456789   nginx:latest   "/docker-entrypoint…"   2 hours ago   Up 2 hours   0.0.0.0:80->80/tcp   web-server

    To compact format:
        abc1234 nginx Up 2h 0.0.0.0:80 web-server
    """
    lines = output.split("\n")
    result = []

    for line in lines:
        # Skip headers
        if re.match(r"^\s*CONTAINER ID\s+IMAGE", line):
            continue
        if re.match(r"^\s*REPOSITORY\s+TAG", line):
            continue
        if re.match(r"^\s*NAMESPACE\s+NAME", line):
            continue
        if re.match(r"^\s*NETWORK ID\s+NAME", line):
            continue
        if re.match(r"^\s*VOLUME NAME\s+DRIVER", line):
            continue

        # Try to parse docker ps format
        # Format: ID IMAGE COMMAND CREATED STATUS PORTS NAMES
        # Use multiple spaces as column separator
        parts = re.split(r"\s{2,}", line.strip())

        if len(parts) >= 6:
            container_id = parts[0][:7] if len(parts[0]) >= 7 else parts[0]

            # Image: remove tag if present
            image = parts[1].split(":")[0] if ":" in parts[1] else parts[1]
            # Truncate long image names
            if len(image) > 20:
                image = image[:17] + "..."

            # parts[2] = COMMAND (skip)
            # parts[3] = CREATED (skip - relative time is usually obvious from status)
            # parts[4] = STATUS
            # parts[5] = PORTS (or -1 index if 6 parts)
            # parts[6] = NAMES (or -1 index)

            # Status: extract state and duration
            status = ""
            status_raw = parts[4] if len(parts) > 4 else ""
            status_match = re.match(
                r"(Up|Exited|Created|Restarting|Paused|Dead)\s*(.*)",
                status_raw,
                re.IGNORECASE,
            )
            if status_match:
                state = status_match.group(1)
                duration = (
                    status_match.group(2).strip() if status_match.group(2) else ""
                )
                # Compact duration
                duration = re.sub(
                    r"(\d+)\s*(hours?|hrs?|h)\b", r"\1h", duration, flags=re.IGNORECASE
                )
                duration = re.sub(
                    r"(\d+)\s*(days?|d)\b", r"\1d", duration, flags=re.IGNORECASE
                )
                duration = re.sub(
                    r"(\d+)\s*(minutes?|mins?|m)\b",
                    r"\1m",
                    duration,
                    flags=re.IGNORECASE,
                )
                duration = re.sub(
                    r"(\d+)\s*(seconds?|secs?|s)\b",
                    r"\1s",
                    duration,
                    flags=re.IGNORECASE,
                )
                duration = re.sub(r"\s*\(.*\)", "", duration)  # Remove health info
                duration = re.sub(r"\s*ago\s*", "", duration)
                status = f"{state} {duration}".strip()

            # Ports and names - last two columns
            ports = parts[-2] if len(parts) >= 7 else ""
            name = parts[-1]

            # Check if ports column looks like ports (contains -> or starts with digit)
            if (
                ports
                and not re.search(r"[0-9].*->|->.*[0-9]", ports)
                and not re.match(r"^[0-9]", ports)
            ):
                # Doesn't look like ports, probably no ports column
                ports = ""
                if len(parts) >= 6:
                    name = parts[-1]

            # Build compact line
            compact_parts = [container_id, image]
            if status:
                compact_parts.append(status)
            if ports and ports != name:
                # Compact port format: remove IPv6 bracket notation
                ports = re.sub(r",\s*\[::\].*?(?=\s|$)", "", ports)
                compact_parts.append(ports)
            if name:
                compact_parts.append(name)

            result.append(" ".join(compact_parts))
        elif line.strip():
            # For non-standard format, just truncate IDs
            line = re.sub(r"\b([a-f0-9]{12,})\b", lambda m: m.group(1)[:7], line)
            result.append(line)

    return "\n".join(result)


def compact_nodejs_output(output: str) -> str:
    """Compact npm/pnpm output - compress package lists and remove verbose output."""
    lines = output.split("\n")
    result = []
    package_lines = []
    in_package_list = False

    for line in lines:
        # Detect package list start
        if re.match(
            r"^\s*(added|removed|changed|updated)\s+\d+\s+packages?",
            line,
            re.IGNORECASE,
        ):
            # Don't skip - keep summary but compact it
            compacted = re.sub(r"in\s+[\d.]+[smh]", "", line).strip()
            if compacted:
                result.append(compacted)
            continue

        # Skip these entirely
        if re.match(r"^\s*(Progress:|packages:|audited|auditing)", line, re.IGNORECASE):
            continue
        if re.match(
            r"^\s*(dependencies|devDependencies|peerDependencies):\s*$",
            line,
            re.IGNORECASE,
        ):
            continue
        if re.match(r"^\s*Done in\s+[\d.]+[smh]?", line, re.IGNORECASE):
            continue
        if re.match(r"^\s*WARN\s+", line, re.IGNORECASE):
            continue

        # Collect package lines
        if re.match(r"^\s*[+-]\s+@?[\w/-]+\s*[\d.]+", line):
            package_lines.append(line.strip())
            in_package_list = True
            continue

        # Flush package list if we hit non-package line
        if in_package_list and package_lines:
            if len(package_lines) > 3:
                result.append(package_lines[0])
                result.append(f"... {len(package_lines) - 1} more packages")
            else:
                result.extend(package_lines)
            package_lines = []
            in_package_list = False

        if line.strip():
            result.append(line)

    # Handle remaining packages
    if package_lines:
        if len(package_lines) > 3:
            result.append(package_lines[0])
            result.append(f"... {len(package_lines) - 1} more packages")
        else:
            result.extend(package_lines)

    return "\n".join(result)


def postprocess_output(output: str, category: str) -> str:
    """Apply category-specific post-processing for maximum token savings."""
    if not output:
        return output

    if category == "git":
        return compact_git_status(output)
    elif category == "python":
        return compact_pytest_output(output)
    elif category in ("docker", "docker-compose"):
        return compact_docker_output(output)
    elif category == "nodejs":
        return compact_nodejs_output(output)

    return output


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


def filter_output(output: str, category: str) -> str:
    """Apply aggressive output filtering based on category to maximize token savings.

    Processing pipeline:
    1. Preprocess: Strip ANSI codes, normalize whitespace
    2. Filter: Remove boilerplate lines based on category
    3. Symbolize & Pattern Compress: Apply symbol substitution and pattern compression
    4. Deduplicate: Compress similar consecutive lines
    5. Postprocess: Category-specific compacting (fallback)
    """
    if not output:
        return output

    # Phase 1: Preprocess
    output = preprocess_output(output)

    lines = output.split("\n")

    # Safety: Check for errors - if found, use light filtering only
    if has_errors(lines):
        return light_filter(lines, category)

    filtered_lines = []

    # Combine patterns for Phase 2
    patterns = SKIP_PATTERNS + CATEGORY_PATTERNS.get(category, [])

    # For git category, don't use git_sensitive_patterns (we need to compact those lines)
    if category != "git":
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
    if category in ("git", "docker", "python", "nodejs", "files", "network"):
        if matches_expected_format(filtered_lines, category):
            compressed = compress_patterns(filtered_lines, category)
            # Verify we got meaningful output
            if compressed:
                result = "\n".join(compressed)
                result = collapse_empty_lines(result.split("\n"))
                return result

    # Phase 4: Deduplicate similar lines (fallback path)
    filtered_lines = deduplicate_similar_lines(filtered_lines)

    result = "\n".join(filtered_lines)

    # Phase 5: Postprocess (fallback)
    result = postprocess_output(result, category)

    # Final cleanup
    result = collapse_empty_lines(result.split("\n"))

    return result


def light_filter(lines: list[str], _category: str) -> str:
    """Light filtering for error output - preserves all error information.

    Args:
        lines: Output lines to filter
        _category: Command category (unused, kept for API consistency)

    Returns:
        Lightly filtered output string
    """
    result = []

    for line in lines:
        line_stripped = line.rstrip()
        if line_stripped:
            result.append(line_stripped)

    return "\n".join(result)
