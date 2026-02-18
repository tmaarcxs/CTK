"""Token estimation utilities."""

import re


def estimate_tokens(text: str) -> int:
    """Estimate token count for text using a simple heuristic.

    Uses approximately 4 characters per token as a rough estimate,
    which works reasonably well for English text and code.
    """
    if not text:
        return 0
    # Count words and punctuation separately for better accuracy
    words = len(re.findall(r"\b\w+\b", text))
    punctuation = len(re.findall(r"[^\w\s]", text))
    # Average: words ~1.3 tokens, punctuation ~0.5 tokens
    return int(words * 1.3 + punctuation * 0.5 + 1)


def estimate_command_tokens(cmd: str) -> int:
    """Estimate tokens for a command string."""
    return estimate_tokens(cmd)


def estimate_output_tokens(output: str) -> int:
    """Estimate tokens for command output."""
    return estimate_tokens(output)


def calculate_savings(original: str, filtered: str) -> dict:
    """Calculate token savings between original and filtered output."""
    original_tokens = estimate_tokens(original)
    filtered_tokens = estimate_tokens(filtered)
    saved = max(0, original_tokens - filtered_tokens)
    percent = (saved / original_tokens * 100) if original_tokens > 0 else 0

    return {
        "original_tokens": original_tokens,
        "filtered_tokens": filtered_tokens,
        "tokens_saved": saved,
        "savings_percent": round(percent, 1),
    }
