"""Symbol dictionaries for aggressive token compression."""

import re
from typing import Any

# =============================================================================
# Git Status Symbols
# =============================================================================

GIT_STATUS_SYMBOLS = {
    # Status type mappings (verbose keyword -> symbol)
    "modified:": "M",
    "deleted:": "D",
    "new file:": "A",
    "renamed:": "R",
    "copied:": "C",
    "type changed:": "T",
}

# Reverse mapping for debugging
GIT_SYMBOL_TO_STATUS = {v: k.rstrip(":") for k, v in GIT_STATUS_SYMBOLS.items()}

# Git status line patterns
GIT_STATUS_PATTERNS = {
    "staged": r"Changes to be committed:",
    "unstaged": r"Changes not staged for commit:",
    "untracked": r"Untracked files:",
    "branch": r"On branch (\S+)",
    "ahead": r"Your branch is ahead of",
    "behind": r"Your branch is behind",
    "up_to_date": r"Your branch is up to date",
}


# =============================================================================
# Docker State Symbols
# =============================================================================

DOCKER_STATE_SYMBOLS = {
    "Up": "U",
    "Exited": "X",
    "Created": "C",
    "Restarting": "R",
    "Paused": "P",
    "Dead": "D",
    "Running": "U",  # Alias
}

# Docker health status
DOCKER_HEALTH_SYMBOLS = {
    "healthy": "H",
    "unhealthy": "UH",
    "starting": "S",
    "": "",  # No health status
}

# Docker header patterns to remove
DOCKER_HEADERS = [
    r"CONTAINER ID",
    r"REPOSITORY\s+TAG",
    r"NETWORK ID",
    r"VOLUME NAME",
    r"IMAGE\s+COMMAND",
]


# =============================================================================
# Python/Pytest Symbols
# =============================================================================

PYTEST_RESULT_SYMBOLS = {
    "PASSED": ".",
    "FAILED": "F",
    "ERROR": "E",
    "SKIPPED": "S",
    "XFAILED": "x",
    "XPASSED": "X",
    "WARNING": "W",
}

# Pytest output patterns
PYTEST_PATTERNS = {
    "collected": r"collected (\d+) items?",
    "passed": r"(\d+) passed",
    "failed": r"(\d+) failed",
    "error": r"(\d+) error",
    "skipped": r"(\d+) skipped",
    "duration": r"in ([\d.]+)s",
}


# =============================================================================
# Node.js/npm/pnpm Symbols
# =============================================================================

NODEJS_CHANGE_SYMBOLS = {
    "added": "+",
    "removed": "-",
    "changed": "~",
    "updated": "~",
    "deprecated": "!",
    "audited": "",
}

# npm/pnpm output patterns
NODEJS_PATTERNS = {
    "packages_added": r"added (\d+)",
    "packages_removed": r"removed (\d+)",
    "packages_changed": r"changed (\d+)",
    "duration": r"in ([\d.]+)s?",
    "audited": r"audited (\d+)",
    "vulnerabilities": r"(\d+) vulnerabilities?",
}


# =============================================================================
# File System Symbols
# =============================================================================

# File type indicators (ls -l style)
FILE_TYPE_SYMBOLS = {
    "-": "-",  # regular file
    "d": "d",  # directory
    "l": "l",  # symlink
    "c": "c",  # character device
    "b": "b",  # block device
    "s": "s",  # socket
    "p": "p",  # named pipe
}

# Permission symbols (rwx -> symbols)
PERMISSION_SYMBOLS = {
    "rwx": "rwx",
    "rw-": "rw",
    "r-x": "rx",
    "r--": "r",
    "-wx": "wx",
    "-w-": "w",
    "--x": "x",
    "---": "-",
}

# File size units
SIZE_UNITS = {
    "bytes": "B",
    "kilobytes": "K",
    "megabytes": "M",
    "gigabytes": "G",
    "terabytes": "T",
}

# Grep match context symbols
GREP_SYMBOLS = {
    "match": ">",  # matched line
    "context": ":",  # context line
    "separator": "--",
}


# =============================================================================
# Network Symbols
# =============================================================================

# HTTP status code categories
HTTP_STATUS_SYMBOLS = {
    # 2xx Success
    "200": "OK",
    "201": "Created",
    "204": "NoContent",
    # 3xx Redirect
    "301": "Moved",
    "302": "Found",
    "304": "NotModified",
    # 4xx Client Error
    "400": "BadReq",
    "401": "Unauth",
    "403": "Forbidden",
    "404": "NotFound",
    # 5xx Server Error
    "500": "SrvErr",
    "502": "BadGate",
    "503": "Unavail",
    "504": "Timeout",
}

# HTTP method symbols
HTTP_METHOD_SYMBOLS = {
    "GET": "G",
    "POST": "P",
    "PUT": "U",
    "DELETE": "D",
    "PATCH": "X",
    "HEAD": "H",
    "OPTIONS": "O",
}

# curl/wget progress patterns to remove
NETWORK_SKIP_PATTERNS = [
    r"^\s*\d+\s+\d+\s+\d+\s+\d+",  # Progress numbers
    r"^\s*% Total\s+%",  # curl progress
    r"^\s*\d+\s+\d+\s+\d+",  # Download progress
    r"^\s*0\s+0\s+0\s+",  # Zero progress
]


# =============================================================================
# Error Detection Patterns (preserve verbatim)
# =============================================================================

ERROR_INDICATORS = [
    r"^Error:",
    r"^error:",
    r"^ERROR",
    r"^Exception:",
    r"^Traceback",
    r"^\s+File \".*\", line \d+",
    r"^\s+\^+",
    r"^E\s+assert",
    r"^E\s+Error",
    r"^E\s+Exception",
    r"^FAIL\s",
    r"FAILED",
    r"ENOENT",
    r"ECONNREFUSED",
    r"ETIMEDOUT",
    r"Permission denied",
    r"fatal:",
    r"panic:",
    r"segmentation fault",
]


# =============================================================================
# Helper Functions
# =============================================================================


def symbolize_git_status(line: str) -> str | None:
    """Convert a git status line to symbolized format.

    Args:
        line: A line from git status output

    Returns:
        Symbolized line or None if not a status line
    """
    line_lower = line.lower()

    # Check each status type
    for status, symbol in GIT_STATUS_SYMBOLS.items():
        if status in line_lower:
            # Extract file path after status keyword
            match = re.search(rf"{re.escape(status)}\s+(.+)", line, re.IGNORECASE)
            if match:
                file_path = match.group(1).strip()
                # Remove usage hints
                file_path = re.sub(r'\s*\(use "[^"]+".*\)', "", file_path)
                return f"{symbol}:{file_path}"

    return None


def symbolize_docker_state(state_raw: str) -> str:
    """Convert docker state to symbol.

    Args:
        state_raw: Raw state string like "Up 2 hours" or "Exited (0) 3 days ago"

    Returns:
        Symbol and condensed duration, e.g., "U2h" or "X3d"
    """
    # Extract state and duration
    match = re.match(
        r"(Up|Exited|Created|Restarting|Paused|Dead)\s*(.*)",
        state_raw,
        re.IGNORECASE,
    )
    if not match:
        return state_raw[:7] if len(state_raw) > 7 else state_raw

    state = match.group(1)
    duration = match.group(2).strip()

    # Get symbol
    symbol = DOCKER_STATE_SYMBOLS.get(state, state[0])

    # Compact duration
    if duration:
        duration = re.sub(r"(\d+)\s*hours?", r"\1h", duration, flags=re.IGNORECASE)
        duration = re.sub(r"(\d+)\s*days?", r"\1d", duration, flags=re.IGNORECASE)
        duration = re.sub(r"(\d+)\s*minutes?", r"\1m", duration, flags=re.IGNORECASE)
        duration = re.sub(r"(\d+)\s*seconds?", r"\1s", duration, flags=re.IGNORECASE)
        duration = re.sub(r"(\d+)\s*weeks?", r"\1w", duration, flags=re.IGNORECASE)
        duration = re.sub(r"\s*\(.*\)", "", duration)  # Remove exit codes/health
        duration = re.sub(r"\s*ago\s*", "", duration)
        duration = duration.strip()
        return f"{symbol}{duration}"

    return symbol


def symbolize_pytest_result(result: str) -> str:
    """Convert pytest result to symbol.

    Args:
        result: Result string like "PASSED", "FAILED", etc.

    Returns:
        Single character symbol
    """
    return PYTEST_RESULT_SYMBOLS.get(result, result[0] if result else "?")


def symbolize_nodejs_change(change_type: str) -> str:
    """Convert nodejs change type to symbol.

    Args:
        change_type: Change type like "added", "removed", etc.

    Returns:
        Single character symbol
    """
    return NODEJS_CHANGE_SYMBOLS.get(
        change_type.lower(), change_type[0] if change_type else ""
    )


def has_errors(lines: list[str]) -> bool:
    """Detect if output contains error information.

    Args:
        lines: List of output lines

    Returns:
        True if error patterns detected
    """
    for line in lines:
        for pattern in ERROR_INDICATORS:
            if re.search(pattern, line, re.IGNORECASE):
                return True
    return False


def get_category_symbols(category: str) -> dict[str, Any]:
    """Get all symbols for a category.

    Args:
        category: Category name (git, docker, python, nodejs, files, network)

    Returns:
        Dictionary of symbols for the category
    """
    symbols_map = {
        "git": {
            "status": GIT_STATUS_SYMBOLS,
            "patterns": GIT_STATUS_PATTERNS,
        },
        "docker": {
            "state": DOCKER_STATE_SYMBOLS,
            "health": DOCKER_HEALTH_SYMBOLS,
            "headers": DOCKER_HEADERS,
        },
        "python": {
            "results": PYTEST_RESULT_SYMBOLS,
            "patterns": PYTEST_PATTERNS,
        },
        "nodejs": {
            "changes": NODEJS_CHANGE_SYMBOLS,
            "patterns": NODEJS_PATTERNS,
        },
        "files": {
            "types": FILE_TYPE_SYMBOLS,
            "permissions": PERMISSION_SYMBOLS,
            "size": SIZE_UNITS,
            "grep": GREP_SYMBOLS,
        },
        "network": {
            "status": HTTP_STATUS_SYMBOLS,
            "methods": HTTP_METHOD_SYMBOLS,
            "skip": NETWORK_SKIP_PATTERNS,
        },
    }
    return symbols_map.get(category, {})
