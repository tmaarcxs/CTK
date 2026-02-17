"""Output filtering and optimization for LLM token savings."""

import re
from difflib import SequenceMatcher


def preprocess_output(output: str) -> str:
    """Preprocess output to remove ANSI codes and normalize whitespace.

    This is the first pass that removes visual noise before category-specific filtering.
    """
    if not output:
        return output

    # Strip ANSI escape sequences (colors, cursor movement, etc.)
    output = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', output)
    # Strip ANSI private mode sequences (e.g., [?25h, [?25l)
    output = re.sub(r'\x1b\[\?[0-9;]*[a-zA-Z]', '', output)
    # Strip additional ANSI codes (OSC, etc.)
    output = re.sub(r'\x1b\][^\x07]*\x07', '', output)
    output = re.sub(r'\x1b[()][AB012]', '', output)

    # Remove Unicode box drawing characters
    box_chars = '┌┐└┘│─├┤┬┴┼╭╮╯╰═║╔╗╚╝╠╣╦╩╬'
    for char in box_chars:
        output = output.replace(char, '')

    # Normalize trailing whitespace on each line
    lines = [line.rstrip() for line in output.split('\n')]

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
                result.append('')
            prev_empty = True
        else:
            result.append(line)
            prev_empty = False

    # Remove leading/trailing empty lines
    while result and not result[0].strip():
        result.pop(0)
    while result and not result[-1].strip():
        result.pop()

    return '\n'.join(result)


def deduplicate_similar_lines(lines: list[str], threshold: float = 0.8) -> list[str]:
    """Deduplicate consecutive similar lines.

    Uses difflib to find lines that differ only slightly (timestamps, counters, etc.)
    and replaces runs of similar lines with a count.
    """
    if len(lines) <= 2:
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

        # Find consecutive similar lines
        similar_group = [line]
        j = i + 1

        while j < len(lines):
            next_line = lines[j]
            if not next_line.strip():
                break

            # Calculate similarity
            ratio = SequenceMatcher(None, line, next_line).ratio()
            if ratio >= threshold:
                similar_group.append(next_line)
                j += 1
            else:
                break

        # If we found multiple similar lines, compress them
        if len(similar_group) > 3:
            # Output first line with count
            result.append(f"{line} [... {len(similar_group)} similar lines]")
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
    """
    lines = output.split('\n')
    result = []

    # Status mapping
    status_map = {
        'modified:': 'M',
        'deleted:': 'D',
        'new file:': 'A',
        'renamed:': 'R',
        'copied:': 'C',
        'type changed:': 'T',
    }

    for line in lines:
        # First, strip usage hints from any line
        line = re.sub(r'\s*\(use "[^"]+"\s+[^)]+\)', '', line)
        line = re.sub(r'\s*\(use "[^"]+"\)', '', line)

        compacted = False

        # Try to compact status lines
        for status, code in status_map.items():
            if status in line.lower():
                # Extract file path (everything after the status keyword)
                match = re.search(rf'{re.escape(status)}\s+(.+)', line, re.IGNORECASE)
                if match:
                    file_path = match.group(1).strip()
                    result.append(f'{code} {file_path}')
                    compacted = True
                    break

        if not compacted:
            # Remove branch info noise
            line = re.sub(r'^\s*On branch \S+\s*$', '', line)
            line = re.sub(r'^\s*Your branch is [^.]+\.\s*$', '', line)
            line = re.sub(r'^\s*nothing to commit,?\s*', '', line)
            line = re.sub(r'^\s*working tree clean\s*$', '', line)
            if line.strip():
                result.append(line)

    return '\n'.join(result)


def compact_pytest_output(output: str) -> str:
    """Compact pytest output - remove passing tests, keep failures and summary."""
    lines = output.split('\n')
    result = []
    in_failure = False
    failure_context = []

    for line in lines:
        # Always keep failures and errors
        if 'FAILED' in line or 'ERROR' in line or 'error:' in line.lower():
            in_failure = True
            failure_context = [line]
            result.append(line)
        elif in_failure:
            # Keep failure context (traceback, assertion details)
            failure_context.append(line)
            if line.strip() and not line.startswith(' '):
                # Non-indented line ends failure context
                in_failure = False
            if in_failure or line.startswith(('assert', 'E ', '>', 'FAILED', 'ERROR')):
                result.append(line)

        # Skip passing test lines
        elif 'PASSED' in line:
            continue
        # Skip progress lines
        elif re.match(r'^\s*[\w/_.]+\s+PASSED\s*\[', line):
            continue
        # Skip separator lines
        elif re.match(r'^=+$', line.strip()):
            continue
        # Skip collection lines
        elif line.strip().startswith('collected'):
            continue
        # Keep summary lines
        elif 'failed' in line.lower() or 'error' in line.lower() or 'passed' not in line.lower():
            if line.strip():
                result.append(line)

    return '\n'.join(result)


def compact_docker_output(output: str) -> str:
    """Compact docker output - truncate IDs, remove predictable headers."""
    lines = output.split('\n')
    result = []

    for line in lines:
        # Truncate container/image IDs to 7 chars (like git commits)
        line = re.sub(r'\b([a-f0-9]{12})\b', lambda m: m.group(1)[:7], line)

        # Remove predictable header lines
        if re.match(r'^\s*CONTAINER ID\s+IMAGE', line):
            continue
        if re.match(r'^\s*REPOSITORY\s+TAG', line):
            continue
        if re.match(r'^\s*NAMESPACE\s+NAME', line):
            continue

        # Remove "Created" timestamps, keep relative time
        line = re.sub(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', '', line)

        if line.strip():
            result.append(line)

    return '\n'.join(result)


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
    r"^\s*(Using|Fetching|Downloading|Installing|Building|Compiling|Processing|Analyzing|Checking|Validating|Verifying|Resolving|Preparing|Generating|Creating|Updating|Removing|Cleaning|Unpacking|Configuring|Setting up)",
    r"^\s*\d+%\s*\|.*\|",  # Progress bars
    r"^\s*\d+%\s+complete",  # Progress percentage
    r"^\s*\[\d+/\d+\]",  # Progress counters
    r"^\s*WARN\s*:",  # Warnings (usually noise)
    r"^\s*INFO\s*:",  # Info logs
    r"^\s*DEBUG\s*:",  # Debug logs
    r"^\s*TRACE\s*:",  # Trace logs
    r"^\s*notice\s*:",  # Notice logs
    r"^\s*verbose\s*:",  # Verbose logs
    r"^\s*Done in\s+\d+",  # Timing info
    r"^\s*Completed in\s+\d+",  # Timing info
    r"^\s*Finished in\s+\d+",  # Timing info
    r"^\s*Took\s+\d+",  # Timing info
    r"^\s*Time:\s+\d+",  # Timing info
    r"^\s*Duration:\s+\d+",  # Timing info
    r"^\s*real\s+\d+m\d+",  # Time output
    r"^\s*user\s+\d+m\d+",  # Time output
    r"^\s*sys\s+\d+m\d+",  # Time output
    r"^\s*\.{3,}$",  # Ellipsis lines
    r"^\s*please wait",  # Waiting messages
    r"^\s*loading",  # Loading messages
    r"^\s*spinning up",  # Startup messages
    r"^\s*starting",  # Startup messages
    r"^\s*initializing",  # Init messages
    r"^\s*running",  # Running messages (usually noise)
    r"^npm warn",  # npm warnings
    r"^npm notice",  # npm notices
    r"^yarn warn",  # yarn warnings
    r"^pnpm warn",  # pnpm warnings
    r"^warning:",  # Generic warnings
    r"^deprecation",  # Deprecation warnings
    r"^deprecated",  # Deprecated warnings
    r"up to date",  # Already updated messages
    r"already installed",  # Already installed
    r"nothing to do",  # Nothing to do
    r"no changes",  # No changes
    r"skipping",  # Skipping messages
    r"^\s*ok\s*$",  # Just "ok"
    r"^\s*success\s*$",  # Just "success"
    r"^\s*pass\s*$",  # Just "pass"
    r"^\s*passed\s*$",  # Just "passed"
    r"^\s*fail\s*$",  # Just "fail"
    r"^\s*failed\s*$",  # Just "failed"
    r"^\s*error:\s*$",  # Empty error lines
    r"^\s*funding\s+message",  # npm funding
    r"^\s*audited\b",  # npm audit summary
    r"Compiling\s+",  # Rust/cargo compilation
    r"Finished\s+dev",  # Rust build finished
    r"Running\s+unittests",  # Rust test runner
    r"^\s*test\s+result:\s+ok",  # Rust test summary (ok)
    r"^\s*\d+\s+passed",  # Generic passing test counts
    r"^\s*\d+\s+tests?\s+ran",  # Test summary
    r"^See \`",  # "See `command --help`" hints
    r"^Run \`",  # "Run `command`" hints
    r"^Try \`",  # "Try `command`" hints
]

# Patterns to skip EXCEPT for git category (where we need to compact status lines)
GIT_SENSITIVE_PATTERNS = [
    r"^\s*(created|deleted|modified|changed|added|removed|updated|copied|moved|renamed):",
]

# Category-specific patterns
CATEGORY_PATTERNS = {
    "docker": [
        r"^\s*CONTAINER ID",  # Header (we know the format)
        r"^\s*IMAGE\s+COMMAND",  # Header
        r"^\s*NAMESPACE",  # K8s header
    ],
    "docker-compose": [
        r"^\s*NAME\s+COMMAND",  # Header
        r"Network\s+\S+\s+created",  # Network creation
        r"Container\s+\S+\s+(Started|Created)",  # Container status
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
    ],
    "python": [
        r"^\s*==",
        r"^\s*---",
        r"^collected \d+ items",
        r"^=\d+ passed",
        r"^=\d+ failed",
        r"^=\d+ skipped",
        r"^\s*PASSED\s*\[",  # Pytest passing lines
        r"^\s*passed\s*$",  # Simple passed line
    ],
    "rust": [
        r"^\s*Compiling",
        r"^\s*Finished",
        r"^\s*Running\b",
        r"^\s*Downloading",
    ],
    "git": [
        r"^\s*$",
        r"^\s*On branch",  # Branch info (handled by postprocess)
        r"^\s*Your branch",  # Branch status (handled by postprocess)
    ],
}


def filter_output(output: str, category: str) -> str:
    """Apply aggressive output filtering based on category to maximize token savings.

    Processing pipeline:
    1. Preprocess: Strip ANSI codes, normalize whitespace
    2. Filter: Remove boilerplate lines based on category
    3. Deduplicate: Compress similar consecutive lines
    4. Postprocess: Category-specific compacting
    """
    if not output:
        return output

    # Phase 1: Preprocess
    output = preprocess_output(output)

    lines = output.split("\n")
    filtered_lines = []

    # Combine patterns
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

    # Phase 3: Deduplicate similar lines
    filtered_lines = deduplicate_similar_lines(filtered_lines)

    result = '\n'.join(filtered_lines)

    # Phase 4: Postprocess
    result = postprocess_output(result, category)

    # Final cleanup
    result = collapse_empty_lines(result.split('\n'))

    return result
