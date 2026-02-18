"""Pattern detection and compression for maximum token savings."""

import re
from collections import defaultdict

from ctk.utils.symbols import (
    GIT_STATUS_SYMBOLS,
    has_errors,
    symbolize_docker_state,
)

# =============================================================================
# Git Pattern Compression
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


# =============================================================================
# Docker Pattern Compression
# =============================================================================


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


# =============================================================================
# Python/Pytest Pattern Compression
# =============================================================================


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
    failure_context: list[str] = []

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
            elif line.startswith(("E ", ">", "assert")):
                failure_context.append(line.strip())

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


# =============================================================================
# Node.js Pattern Compression
# =============================================================================


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


# =============================================================================
# Files Pattern Compression
# =============================================================================


def compress_ls_output(lines: list[str]) -> list[str]:
    """Compress ls -l output to minimal format.

    Converts:
        -rw-r--r--  1 user group  12345 Jan 15 10:30 file.txt

    To:
        -rw 12K file.txt
    """
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


def compress_grep_output(lines: list[str]) -> list[str]:
    """Compress grep output to minimal file:line format.

    Converts:
        src/app.ts:42:some text here

    To:
        src/app.ts:42
    """
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


def compress_find_output(lines: list[str]) -> list[str]:
    """Compress find output by shortening paths and grouping.

    Converts:
        ./src/components/Button/Button.tsx
        ./src/components/Button/Button.test.tsx
        ./src/components/Input/Input.tsx

    To:
        src/components/Button/Button.tsx
        src/components/Button/Button.test.tsx
        src/components/Input/Input.tsx
    """
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


def compress_files_output(lines: list[str]) -> list[str]:
    """Compress file command output based on content."""
    # Detect output type
    text = "\n".join(lines)

    # Check for ls -l format
    if re.search(r"^[d\-l][rwx\-]{9}\s", text, re.MULTILINE):
        return compress_ls_output(lines)

    # Check for grep format (file:line:content)
    if re.search(r"^[^:]+:\d+:", text, re.MULTILINE):
        return compress_grep_output(lines)

    # Check for find format (paths)
    if re.search(r"^(\./)?[\w/_.\-]+$", text, re.MULTILINE):
        return compress_find_output(lines)

    # Default - just limit output
    return lines[:50]


# =============================================================================
# Network Pattern Compression
# =============================================================================


def compress_curl_output(lines: list[str]) -> list[str]:
    """Compress curl output to essential info.

    Keeps:
        - HTTP status line
        - Response body (truncated if too long)
        - Error messages

    Removes:
        - Progress bars
        - SSL handshake details
        - Connection details
    """
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


def compress_wget_output(lines: list[str]) -> list[str]:
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


def compress_network_output(lines: list[str]) -> list[str]:
    """Compress network command output."""
    text = "\n".join(lines)

    # Detect curl vs wget by content
    if re.search(r"^(<|>|\*|%|Trying|Connected)", text, re.MULTILINE):
        return compress_curl_output(lines)

    if re.search(r"(Saving|Resolving|Connecting).*wget", text, re.IGNORECASE):
        return compress_wget_output(lines)

    # Default - just limit and clean
    return [line.rstrip() for line in lines if line.strip()][:20]


# =============================================================================
# Main Compression Function
# =============================================================================


def compress_patterns(lines: list[str], category: str) -> list[str]:
    """Apply pattern-based compression for maximum token savings.

    Args:
        lines: List of pre-filtered output lines
        category: Command category (git, docker, python, nodejs, files, network)

    Returns:
        Compressed lines
    """
    if not lines:
        return lines

    # Safety: Check for errors - if found, return with minimal processing
    if has_errors(lines):
        # Keep errors verbatim, just clean up whitespace
        return [line.rstrip() for line in lines if line.strip()]

    # Apply category-specific compression
    if category == "git":
        return compress_git_status(lines)
    elif category == "docker":
        return compress_docker_output(lines)
    elif category == "python":
        return compress_pytest_output(lines)
    elif category == "nodejs":
        return compress_nodejs_output(lines)
    elif category == "files":
        return compress_files_output(lines)
    elif category == "network":
        return compress_network_output(lines)

    # No compression for other categories - return as-is
    return lines


def matches_expected_format(lines: list[str], category: str) -> bool:
    """Check if output matches expected format for the category.

    Args:
        lines: Output lines to check
        category: Command category

    Returns:
        True if format is recognized
    """
    if not lines:
        return False

    text = "\n".join(lines)

    if category == "git":
        # Should have status keywords or branch info
        return bool(
            re.search(
                r"(modified|deleted|new file|On branch|Untracked)", text, re.IGNORECASE
            )
        )
    elif category == "docker":
        # Should have container-like output
        return bool(re.search(r"(CONTAINER ID|[a-f0-9]{12,}\s+\w+)", text))
    elif category == "python":
        # Should have pytest output
        return bool(
            re.search(
                r"(PASSED|FAILED|collected|test session|passed.*failed)",
                text,
                re.IGNORECASE,
            )
        )
    elif category == "nodejs":
        # Should have npm/pnpm output
        return bool(
            re.search(r"(added|removed|changed|packages|npm|pnpm)", text, re.IGNORECASE)
        )
    elif category == "files":
        # Should have file-related output
        return bool(
            re.search(r"([d\-l][rwx\-]{9}|^\.?/?[\w/_.\-]+$|:\d+:)", text, re.MULTILINE)
        )
    elif category == "network":
        # Should have HTTP/network output
        return bool(
            re.search(r"(HTTP|curl|wget|Connecting|Resolving)", text, re.IGNORECASE)
        )

    return True  # Assume valid for unknown categories
