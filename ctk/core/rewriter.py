"""Command rewriting engine for CTK."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class RewriteResult:
    """Result of a command rewrite operation."""

    original: str
    rewritten: str | None
    category: str
    should_rewrite: bool


@dataclass
class CommandCategory:
    """Configuration for a command category."""

    name: str
    patterns: list[tuple[re.Pattern[str], str]]
    subcommands: list[str] | None = None
    subcommand_extractor: Callable[[str], str | None] | None = None


def _compile_pattern(pattern: str) -> re.Pattern[str]:
    """Compile a regex pattern."""
    return re.compile(pattern)


def _extract_subcommand_generic(
    cmd: str, prefix: str, strip_patterns: list[str]
) -> str | None:
    """Generic subcommand extractor with configurable strip patterns.

    Args:
        cmd: The command string
        prefix: The command prefix to remove (e.g., "git", "docker")
        strip_patterns: List of regex patterns to strip from the command

    Returns:
        The extracted subcommand or None
    """
    # Remove the command prefix
    cmd = re.sub(rf"^{re.escape(prefix)}\s+", "", cmd)

    # Apply all strip patterns
    for pattern in strip_patterns:
        cmd = re.sub(pattern, "", cmd)

    cmd = cmd.strip()
    parts = cmd.split()
    return parts[0] if parts else None


def _extract_git_subcommand(cmd: str) -> str | None:
    """Extract git subcommand, stripping flags like -C, -c, etc."""
    return _extract_subcommand_generic(
        cmd,
        "git",
        [
            r"(-C|-c)\s+[^\s]+\s*",
            r"--[a-z-]+=[^\s]+\s*",
            r"--(no-pager|no-optional-locks|bare|literal-pathspecs)\s*",
        ],
    )


def _extract_docker_subcommand(cmd: str) -> str | None:
    """Extract docker subcommand, handling compose specially."""
    cmd = re.sub(r"^docker\s+", "", cmd)
    if cmd.startswith("compose"):
        return "compose"
    return _extract_subcommand_generic(
        "docker " + cmd,
        "docker",
        [r"(-H|--context|--config)\s+[^\s]+\s*", r"--[a-z-]+=[^\s]+\s*"],
    )


def _extract_simple_subcommand(cmd: str) -> str | None:
    """Extract subcommand for tools like gh (second word)."""
    parts = cmd.split()
    return parts[1] if len(parts) > 1 else None


# Registry of command categories with their configurations
COMMAND_CATEGORIES: dict[str, CommandCategory] = {}


def _register_category(
    name: str,
    patterns: list[tuple[str, str]],
    subcommands: list[str] | None = None,
    extractor: Callable[[str], str | None] | None = None,
) -> None:
    """Register a command category."""
    compiled_patterns = [(_compile_pattern(p), label) for p, label in patterns]
    COMMAND_CATEGORIES[name] = CommandCategory(
        name=name,
        patterns=compiled_patterns,
        subcommands=subcommands,
        subcommand_extractor=extractor,
    )


# Register all command categories
_register_category(
    "docker",
    [
        (r"^docker\s+compose\s+", "docker compose"),
        (r"^docker\s+ps", "docker ps"),
        (r"^docker\s+images", "docker images"),
        (r"^docker\s+logs", "docker logs"),
        (r"^docker\s+run", "docker run"),
        (r"^docker\s+build", "docker build"),
        (r"^docker\s+exec", "docker exec"),
        (r"^docker\s+inspect", "docker inspect"),
        (r"^docker\s+cp", "docker cp"),
    ],
    subcommands=[
        "compose",
        "ps",
        "images",
        "logs",
        "run",
        "build",
        "exec",
        "inspect",
        "cp",
    ],
    extractor=_extract_docker_subcommand,
)

_register_category(
    "git",
    [(r"^git\s+", "git")],
    subcommands=[
        "status",
        "diff",
        "log",
        "add",
        "commit",
        "push",
        "pull",
        "branch",
        "fetch",
        "stash",
        "show",
        "merge",
        "rebase",
        "checkout",
    ],
    extractor=_extract_git_subcommand,
)

_register_category(
    "gh",
    [
        (r"^gh\s+pr", "gh pr"),
        (r"^gh\s+issue", "gh issue"),
        (r"^gh\s+run", "gh run"),
        (r"^gh\s+api", "gh api"),
        (r"^gh\s+release", "gh release"),
    ],
    subcommands=["pr", "issue", "run", "api", "release"],
    extractor=_extract_simple_subcommand,
)

_register_category(
    "files",
    [
        (r"^ls(\s|$)", "ls"),
        (r"^tree(\s|$)", "tree"),
        (r"^cat\s+", "read"),
        (r"^rg\s+", "grep"),
        (r"^grep\s+", "grep"),
        (r"^find\s+", "find"),
        (r"^diff\s+", "diff"),
        (r"^head\s+", "head"),
        (r"^du(\s|$)", "du"),
        (r"^rm(\s|$)", "rm"),
        (r"^ln(\s|$)", "ln"),
        (r"^mv(\s|$)", "mv"),
        (r"^stat\s+", "stat"),
    ],
)

_register_category(
    "system",
    [
        (r"^ps\s+", "ps"),
        (r"^free(\s|$)", "free"),
        (r"^date(\s|$)", "date"),
        (r"^whoami(\s|$)", "whoami"),
        (r"^uname(\s|$)", "uname"),
        (r"^dpkg\s+", "dpkg"),
        (r"^apt(\s|$)", "apt"),
        (r"^pkill\s+", "pkill"),
        (r"^top(\s|$)", "top"),
        (r"^htop(\s|$)", "htop"),
    ],
)

_register_category(
    "python",
    [
        (r"^pytest(\s|$)", "pytest"),
        (r"^python\s+-m\s+pytest", "pytest"),
        (r"^ruff\s+", "ruff"),
        (r"^pip\s+", "pip"),
        (r"^uv\s+pip\s+", "pip"),
    ],
)

_register_category(
    "nodejs",
    [
        (r"^pnpm\s+test", "vitest"),
        (r"^pnpm\s+tsc", "tsc"),
        (r"^pnpm\s+lint", "lint"),
        (r"^pnpm\s+playwright", "playwright"),
        (r"^pnpm\s+(list|ls|outdated)", "pnpm"),
        (r"^npm\s+test", "npm test"),
        (r"^npm\s+run\s+", "npm"),
        (r"^(npx\s+)?vitest", "vitest"),
        (r"^(npx\s+)?vue-tsc", "tsc"),
        (r"^(npx\s+)?tsc", "tsc"),
        (r"^(npx\s+)?eslint", "lint"),
        (r"^(npx\s+)?prettier", "prettier"),
        (r"^(npx\s+)?playwright", "playwright"),
        (r"^(npx\s+)?prisma", "prisma"),
    ],
)

_register_category(
    "network",
    [
        (r"^curl\s+", "curl"),
        (r"^wget\s+", "wget"),
    ],
)

# Legacy dict for backward compatibility
COMMAND_PATTERNS = {
    name: {
        "patterns": [(p.pattern, label) for p, label in cat.patterns],
        "subcommands": cat.subcommands,
    }
    for name, cat in COMMAND_CATEGORIES.items()
}


def extract_prefix(cmd: str) -> tuple[str, str]:
    """Extract environment variable prefix and sudo prefix from command.

    Returns: (prefix_to_preserve, command_body)
    """
    prefix = ""
    remaining = cmd

    # Extract env vars at the start
    env_match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*=[^\s]*\s+)+", remaining)
    if env_match:
        prefix += env_match.group(0)
        remaining = remaining[len(env_match.group(0)) :]

    # Extract sudo with optional flags
    sudo_match = re.match(r"^sudo(\s+-[A-Za-z]+(\s+[^\s]+)?)?\s+", remaining)
    if sudo_match:
        prefix += sudo_match.group(0)
        remaining = remaining[len(sudo_match.group(0)) :]

    return prefix, remaining


def should_rewrite_command(cmd: str) -> RewriteResult:
    """Determine if a command should be rewritten and how.

    Args:
        cmd: The command string to analyze

    Returns:
        RewriteResult with rewrite information
    """
    if not cmd or cmd.startswith("ctk ") or cmd.startswith("rtk "):
        return RewriteResult(cmd, None, "none", False)

    # Skip heredocs
    if "<<" in cmd:
        return RewriteResult(cmd, None, "none", False)

    prefix, cmd_body = extract_prefix(cmd)

    for category_name, category in COMMAND_CATEGORIES.items():
        for pattern, _ in category.patterns:
            if pattern.search(cmd_body):
                # Check if there are subcommands to validate
                if category.subcommands and category.subcommand_extractor:
                    extracted = category.subcommand_extractor(cmd_body)

                    # If we have subcommands, check if extracted is valid
                    if extracted and extracted in category.subcommands:
                        rewritten = f"{prefix}ctk {cmd_body}"
                        return RewriteResult(cmd, rewritten, category_name, True)
                    elif extracted is None:
                        # Pattern matched but no specific subcommand required
                        rewritten = f"{prefix}ctk {cmd_body}"
                        return RewriteResult(cmd, rewritten, category_name, True)
                else:
                    # No subcommand validation needed
                    rewritten = f"{prefix}ctk {cmd_body}"
                    return RewriteResult(cmd, rewritten, category_name, True)

    return RewriteResult(cmd, None, "none", False)


def rewrite_command(cmd: str) -> str | None:
    """Simple function to just return the rewritten command or None.

    Args:
        cmd: The command string to rewrite

    Returns:
        Rewritten command string or None if no rewrite needed
    """
    result = should_rewrite_command(cmd)
    return result.rewritten


def get_command_category(cmd: str) -> str:
    """Get the category for a command without rewriting."""
    result = should_rewrite_command(cmd)
    return result.category
