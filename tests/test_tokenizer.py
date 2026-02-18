"""Tests for the token estimation utilities."""

from ctk.utils.tokenizer import (
    calculate_savings,
    estimate_command_tokens,
    estimate_output_tokens,
    estimate_tokens,
)


class TestEstimateTokens:
    """Tests for estimate_tokens function."""

    def test_empty_string(self):
        """Empty string should have 0 tokens."""
        assert estimate_tokens("") == 0

    def test_single_word(self):
        """Single word should estimate ~1-2 tokens."""
        tokens = estimate_tokens("hello")
        assert 1 <= tokens <= 3

    def test_multiple_words(self):
        """Multiple words should estimate more tokens."""
        tokens = estimate_tokens("hello world foo bar")
        assert tokens >= 4

    def test_with_punctuation(self):
        """Punctuation should add to token count."""
        text_no_punct = "hello world"
        text_with_punct = "hello, world!"
        assert estimate_tokens(text_with_punct) > estimate_tokens(text_no_punct)

    def test_long_text(self):
        """Longer text should estimate more tokens."""
        short = "short"
        long = "short " * 100
        assert estimate_tokens(long) > estimate_tokens(short)

    def test_code_text(self):
        """Code should be estimatable."""
        code = "def foo():\n    return 'bar'"
        tokens = estimate_tokens(code)
        assert tokens > 0

    def test_mixed_content(self):
        """Mixed content should be estimatable."""
        text = "Hello, world! This is a test. 123 456"
        tokens = estimate_tokens(text)
        assert tokens > 0

    def test_newlines(self):
        """Newlines should be handled."""
        text = "line1\nline2\nline3"
        tokens = estimate_tokens(text)
        assert tokens > 0

    def test_special_characters(self):
        """Special characters should be handled."""
        text = "foo@bar.com $100 #hashtag"
        tokens = estimate_tokens(text)
        assert tokens > 0


class TestEstimateCommandTokens:
    """Tests for estimate_command_tokens function."""

    def test_simple_command(self):
        """Simple command should be estimatable."""
        tokens = estimate_command_tokens("git status")
        assert tokens > 0

    def test_command_with_args(self):
        """Command with arguments should estimate more tokens."""
        simple = estimate_command_tokens("git")
        with_args = estimate_command_tokens("git status --short --branch")
        assert with_args > simple

    def test_complex_command(self):
        """Complex command should be estimatable."""
        cmd = "docker compose -f docker-compose.prod.yml up -d --build"
        tokens = estimate_command_tokens(cmd)
        assert tokens > 0


class TestEstimateOutputTokens:
    """Tests for estimate_output_tokens function."""

    def test_empty_output(self):
        """Empty output should have 0 tokens."""
        assert estimate_output_tokens("") == 0

    def test_multiline_output(self):
        """Multiline output should be estimatable."""
        output = "line1\nline2\nline3\n"
        tokens = estimate_output_tokens(output)
        assert tokens > 0

    def test_large_output(self):
        """Large output should estimate more tokens."""
        small = "single line"
        large = "\n".join([f"line {i}" for i in range(100)])
        assert estimate_output_tokens(large) > estimate_output_tokens(small)


class TestCalculateSavings:
    """Tests for calculate_savings function."""

    def test_no_savings(self):
        """Identical strings should have no savings."""
        result = calculate_savings("same text", "same text")
        assert result["original_tokens"] == result["filtered_tokens"]
        assert result["tokens_saved"] == 0
        assert result["savings_percent"] == 0

    def test_full_savings(self):
        """Empty filtered string should show full savings."""
        result = calculate_savings("some long text here", "")
        assert result["original_tokens"] > 0
        assert result["filtered_tokens"] == 0
        assert result["tokens_saved"] == result["original_tokens"]
        assert result["savings_percent"] == 100.0

    def test_partial_savings(self):
        """Partial filtering should show partial savings."""
        original = "this is a long piece of text with many words"
        filtered = "short text"
        result = calculate_savings(original, filtered)
        assert result["original_tokens"] > result["filtered_tokens"]
        assert result["tokens_saved"] > 0
        assert 0 < result["savings_percent"] < 100

    def test_empty_original(self):
        """Empty original should show no savings."""
        result = calculate_savings("", "some text")
        assert result["original_tokens"] == 0
        assert result["savings_percent"] == 0

    def test_both_empty(self):
        """Both empty should show zeros."""
        result = calculate_savings("", "")
        assert result["original_tokens"] == 0
        assert result["filtered_tokens"] == 0
        assert result["tokens_saved"] == 0
        assert result["savings_percent"] == 0

    def test_result_structure(self):
        """Result should have all expected keys."""
        result = calculate_savings("original", "filtered")
        assert "original_tokens" in result
        assert "filtered_tokens" in result
        assert "tokens_saved" in result
        assert "savings_percent" in result

    def test_tokens_saved_calculation(self):
        """Tokens saved should be original - filtered."""
        result = calculate_savings("one two three four five", "one")
        expected_saved = result["original_tokens"] - result["filtered_tokens"]
        assert result["tokens_saved"] == expected_saved

    def test_percent_calculation(self):
        """Savings percent should be tokens_saved / original * 100."""
        original = "one two three four five six seven eight"
        filtered = "one"
        result = calculate_savings(original, filtered)
        if result["original_tokens"] > 0:
            expected_percent = (
                result["tokens_saved"] / result["original_tokens"]
            ) * 100
            assert abs(result["savings_percent"] - expected_percent) < 0.1

    def test_never_negative_savings(self):
        """Tokens saved should never be negative."""
        result = calculate_savings("short", "much longer text here")
        assert result["tokens_saved"] >= 0

    def test_filtered_larger_than_original(self):
        """Should handle case where filtered is larger than original."""
        result = calculate_savings("a", "a b c d e f g")
        # Savings should be 0 (can't save negative tokens)
        assert result["tokens_saved"] >= 0


class TestEstimateTokensRealWorld:
    """Real-world test cases for token estimation."""

    def test_docker_ps_output(self):
        """Should estimate Docker ps output."""
        output = """
CONTAINER ID   IMAGE     COMMAND   CREATED   STATUS    PORTS     NAMES
abc123         nginx     "nginx"   2 days    Up        80/tcp    web
"""
        tokens = estimate_tokens(output)
        assert tokens > 0

    def test_git_status_output(self):
        """Should estimate git status output."""
        output = """
On branch main
Changes to be committed:
  modified:   file1.py
  new file:   file2.py
"""
        tokens = estimate_tokens(output)
        assert tokens > 0

    def test_pytest_output(self):
        """Should estimate pytest output."""
        output = """
============================= test session starts ==============================
collected 10 items

test_module.py ...F......                                               [100%]
"""
        tokens = estimate_tokens(output)
        assert tokens > 0

    def test_npm_output(self):
        """Should estimate npm output."""
        output = """
added 50 packages in 5s
10 packages are looking for funding
  run `npm fund` for details
"""
        tokens = estimate_tokens(output)
        assert tokens > 0
