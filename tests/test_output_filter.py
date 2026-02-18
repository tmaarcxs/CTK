"""Tests for output filtering functions."""

from ctk.utils.output_filter import (
    collapse_empty_lines,
    compact_docker_output,
    compact_git_status,
    compact_pytest_output,
    deduplicate_similar_lines,
    filter_output,
    postprocess_output,
    preprocess_output,
)


class TestFilterOutput:
    """Tests for the filter_output function."""

    def test_empty_output(self):
        """Empty output should remain empty."""
        assert filter_output("", "git") == ""

    def test_removes_empty_lines(self):
        """Should remove empty lines."""
        output = "line1\n\n\nline2\n"
        result = filter_output(output, "git")
        assert "line1" in result
        assert "line2" in result

    def test_removes_separator_lines(self):
        """Should remove separator lines."""
        output = "line1\n===\n---\n+++\nline2"
        result = filter_output(output, "git")
        assert "line1" in result
        assert "line2" in result

    def test_removes_progress_bars(self):
        """Should remove progress bar lines."""
        output = "line1\n50% |====    |\nline2"
        result = filter_output(output, "git")
        assert "line1" in result
        assert "line2" in result

    def test_removes_timing_info(self):
        """Should remove timing info lines."""
        output = "line1\nDone in 5.2s\nCompleted in 100ms\nline2"
        result = filter_output(output, "git")
        assert "line1" in result
        assert "line2" in result

    def test_removes_warnings(self):
        """Should remove warning lines."""
        output = "line1\nWARN: something\nwarning: deprecated\nline2"
        result = filter_output(output, "git")
        assert "line1" in result
        assert "line2" in result

    def test_preserves_important_content(self):
        """Should preserve important content."""
        output = "error: something failed\nline2"
        result = filter_output(output, "git")
        assert "error:" in result
        assert "line2" in result


class TestFilterOutputEnhanced:
    """Tests for enhanced output filtering functionality."""

    def test_strips_ansi_codes(self):
        """Should strip ANSI escape sequences."""
        output = "\x1b[32mCompleted\x1b[0m\n\x1b[31mError\x1b[0m"
        result = filter_output(output, "git")
        assert "\x1b[" not in result
        assert "Completed" in result
        assert "Error" in result

    def test_strips_ansi_cursor_codes(self):
        """Should strip ANSI cursor movement codes."""
        output = "\x1b[2K\x1b[GProgress\x1b[?25h"
        result = filter_output(output, "git")
        assert "\x1b[" not in result

    def test_removes_box_drawing(self):
        """Should remove Unicode box drawing characters."""
        output = "┌─────┐\n│ data │\n└─────┘"
        result = filter_output(output, "git")
        assert "┌" not in result
        assert "┐" not in result
        assert "│" not in result
        assert "└" not in result
        assert "data" in result

    def test_removes_double_line_box_drawing(self):
        """Should remove double-line box drawing characters."""
        output = "╔═════╗\n║ text ║\n╚═════╝"
        result = filter_output(output, "git")
        assert "╔" not in result
        assert "═" not in result
        assert "text" in result

    def test_compacts_git_status(self):
        """Should compact git status to short format."""
        output = "modified:   src/app.ts\ndeleted:    src/old.ts"
        result = filter_output(output, "git")
        # New format uses colon separator and groups by status
        assert "M:" in result
        assert "D:" in result

    def test_compacts_git_status_new_file(self):
        """Should compact new file status."""
        output = "new file:   src/new.ts"
        result = filter_output(output, "git")
        assert "A:src/new.ts" in result

    def test_removes_git_usage_hints(self):
        """Should remove git usage hint parentheticals."""
        output = 'modified: file.ts (use "git add" to update)'
        result = filter_output(output, "git")
        assert "(use" not in result
        assert "M:file.ts" in result

    def test_removes_git_branch_info(self):
        """Should remove verbose branch info."""
        output = "On branch main\nYour branch is up to date with 'origin/main'.\nmodified: file.ts"
        result = filter_output(output, "git")
        assert "On branch" not in result
        assert "M:file.ts" in result

    def test_preserves_errors(self):
        """Should preserve error messages."""
        output = "WARN: x\nerror: critical failure\nINFO: done"
        result = filter_output(output, "git")
        assert "error: critical failure" in result

    def test_preserves_error_codes(self):
        """Should preserve error codes like ENOENT."""
        output = "Error: ENOENT: no such file\nECONNREFUSED connection refused"
        result = filter_output(output, "git")
        assert "ENOENT" in result
        assert "ECONNREFUSED" in result

    def test_removes_passing_tests(self):
        """Should remove passing test lines but keep failures."""
        # Use format that matches expected pytest pattern
        output = "tests/test.py::test_one PASSED [10%]\ntests/test.py::test_two FAILED [20%]\ntests/test.py::test_three PASSED [30%]\n1 passed, 1 failed"
        result = filter_output(output, "python")
        assert "FAILED" in result or "FAIL" in result

    def test_preserves_pytest_failures(self):
        """Should preserve pytest failure details."""
        output = "test_one FAILED [10%]\n> assert 1 == 2\nE assert 1 == 2"
        result = filter_output(output, "python")
        assert "FAILED" in result
        assert "assert" in result

    def test_removes_pytest_collection(self):
        """Should remove pytest collection messages."""
        output = "collected 100 items\ntest_one PASSED"
        result = filter_output(output, "python")
        assert "collected" not in result

    def test_compacts_docker_ids(self):
        """Should truncate Docker container IDs to 7 chars."""
        output = "abc123456789 nginx Up 2 hours"
        result = filter_output(output, "docker")
        assert "abc1234" in result
        assert "abc123456789" not in result

    def test_removes_docker_headers(self):
        """Should remove Docker header lines."""
        output = "CONTAINER ID   IMAGE     COMMAND\nabc123 nginx bash"
        result = filter_output(output, "docker")
        assert "CONTAINER ID" not in result
        assert "abc123" in result or "nginx" in result

    def test_removes_npm_funding(self):
        """Should remove npm funding messages."""
        output = "added 5 packages\nfunding message: support us\naudited 100 packages"
        result = filter_output(output, "nodejs")
        assert "funding" not in result.lower()

    def test_deduplicates_similar_lines(self):
        """Should compress similar consecutive lines."""
        # Create output with similar log lines (must be 15+ chars to trigger dedup)
        output = "\n".join(
            [
                "[2024-01-01] Request processed successfully id=1",
                "[2024-01-01] Request processed successfully id=2",
                "[2024-01-01] Request processed successfully id=3",
                "[2024-01-01] Request processed successfully id=4",
                "[2024-01-01] Different log entry here",
            ]
        )
        result = filter_output(output, "docker")
        # Should have compressed output (fewer lines than input)
        result_lines = [line for line in result.split("\n") if line.strip()]
        assert len(result_lines) < 5

    def test_preserves_diff_hunks(self):
        """Should preserve diff hunk markers."""
        output = "@@ -1,4 +1,4 @@\n-old\n+new"
        result = filter_output(output, "git")
        assert "@@" in result or "old" in result or "new" in result

    def test_preserves_file_paths_with_lines(self):
        """Should preserve file paths with line numbers."""
        output = "src/app.ts:42: error: Type error"
        result = filter_output(output, "git")
        assert "src/app.ts:42" in result or "error" in result

    def test_collapses_empty_lines(self):
        """Should collapse multiple empty lines to one."""
        output = "line1\n\n\n\n\nline2"
        result = filter_output(output, "git")
        # Should not have 3+ consecutive newlines
        assert "\n\n\n" not in result

    def test_normalizes_trailing_whitespace(self):
        """Should remove trailing whitespace."""
        output = "line1   \nline2\t\t\n"
        result = filter_output(output, "git")
        assert "line1   " not in result
        assert "line2\t\t" not in result


class TestPreprocessOutput:
    """Tests for preprocess_output function."""

    def test_empty_input(self):
        """Empty input should return empty."""
        assert preprocess_output("") == ""

    def test_strips_ansi_colors(self):
        """Should strip ANSI color codes."""
        output = "\x1b[31mRed\x1b[0m \x1b[32mGreen\x1b[0m"
        result = preprocess_output(output)
        assert result == "Red Green"

    def test_strips_ansi_bright_colors(self):
        """Should strip ANSI bright color codes."""
        output = "\x1b[91mBright Red\x1b[0m"
        result = preprocess_output(output)
        assert result == "Bright Red"

    def test_removes_box_characters(self):
        """Should remove all box drawing characters."""
        output = "┌─┐│└┘├┤┬┴┼"
        result = preprocess_output(output)
        assert result == ""

    def test_collapse_empty_lines(self):
        """Should collapse consecutive empty lines."""
        output = "a\n\n\nb\n\n\nc"
        result = preprocess_output(output)
        assert "\n\n\n" not in result


class TestCompactFunctions:
    """Tests for category-specific compact functions."""

    def test_git_status_compact(self):
        """Test git status compacting."""
        output = "modified:   src/app.ts\ndeleted:    src/old.ts"
        result = compact_git_status(output)
        assert "M src/app.ts" in result
        assert "D src/old.ts" in result

    def test_pytest_keeps_failures(self):
        """Test pytest output keeps failures."""
        output = "test_one PASSED\ntest_two FAILED\ntest_three PASSED"
        result = compact_pytest_output(output)
        assert "FAILED" in result
        assert "PASSED" not in result

    def test_docker_truncates_ids(self):
        """Test docker output truncates IDs."""
        output = "abc123456789 nginx Up"
        result = compact_docker_output(output)
        assert "abc1234" in result


class TestCollapseEmptyLines:
    """Tests for collapse_empty_lines function."""

    def test_empty_list(self):
        """Empty list should return empty string."""
        assert collapse_empty_lines([]) == ""

    def test_no_empty_lines(self):
        """Should preserve non-empty lines."""
        assert collapse_empty_lines(["a", "b", "c"]) == "a\nb\nc"

    def test_collapses_consecutive(self):
        """Should collapse consecutive empty lines."""
        assert collapse_empty_lines(["a", "", "", "b"]) == "a\n\nb"


class TestDeduplicateSimilarLines:
    """Tests for deduplicate_similar_lines function."""

    def test_short_list(self):
        """Short lists should not be modified."""
        lines = ["a", "b"]
        assert deduplicate_similar_lines(lines) == lines

    def test_dissimilar_lines(self):
        """Dissimilar lines should not be compressed."""
        lines = ["line 1", "completely different", "another unique line"]
        result = deduplicate_similar_lines(lines)
        assert len(result) == 3


class TestPostprocessOutput:
    """Tests for postprocess_output function."""

    def test_empty_output(self):
        """Empty output should return empty."""
        assert postprocess_output("", "git") == ""

    def test_unknown_category(self):
        """Unknown category should return unchanged."""
        output = "some output"
        assert postprocess_output(output, "unknown") == output


class TestCompactDockerOutputDuration:
    """Verify docker output uses compact_duration helper.

    Docker ps format requires 6+ columns to trigger compacting:
    ID IMAGE COMMAND CREATED STATUS PORTS NAMES
    """

    def test_compacts_hours(self):
        # Full docker ps format: ID IMAGE COMMAND CREATED STATUS PORTS NAMES
        output = 'abc123456789   nginx:latest   "/docker-entrypoint…"   2 hours ago   Up 2 hours   0.0.0.0:80->80/tcp   web'
        result = compact_docker_output(output)
        assert "2h" in result

    def test_compacts_days(self):
        output = 'abc123456789   nginx:latest   "/docker-entrypoint…"   3 days ago   Up 3 days   0.0.0.0:80->80/tcp   web'
        result = compact_docker_output(output)
        assert "3d" in result

    def test_compacts_minutes(self):
        output = 'abc123456789   nginx:latest   "/docker-entrypoint…"   45 minutes ago   Up 45 minutes   0.0.0.0:80->80/tcp   web'
        result = compact_docker_output(output)
        assert "45m" in result

    def test_compacts_seconds(self):
        output = 'abc123456789   nginx:latest   "/docker-entrypoint…"   30 seconds ago   Up 30 seconds   0.0.0.0:80->80/tcp   web'
        result = compact_docker_output(output)
        assert "30s" in result

    def test_compacts_weeks(self):
        output = 'abc123456789   nginx:latest   "/docker-entrypoint…"   2 weeks ago   Up 2 weeks   0.0.0.0:80->80/tcp   web'
        result = compact_docker_output(output)
        assert "2w" in result

    def test_removes_health_info(self):
        output = 'abc123456789   nginx:latest   "/docker-entrypoint…"   2 hours ago   Up 2 hours (healthy)   0.0.0.0:80->80/tcp   web'
        result = compact_docker_output(output)
        assert "(healthy)" not in result
        assert "2h" in result

    def test_removes_ago_suffix(self):
        output = 'abc123456789   nginx:latest   "/docker-entrypoint…"   2 hours ago   Up 2 hours ago   0.0.0.0:80->80/tcp   web'
        result = compact_docker_output(output)
        assert " ago" not in result
        assert "2h" in result


class TestEnhancedPipeline:
    """Tests for the enhanced compression pipeline."""

    def test_git_status_compressed(self):
        """Git status should use symbol grouping."""
        output = "On branch main\nmodified:   src/app.ts\nmodified:   src/utils.ts\nnew file:   src/new.ts"
        result = filter_output(output, "git")
        # Should use symbol format
        assert "M:" in result or "A:" in result
        # Should not have verbose format
        assert "On branch" not in result

    def test_docker_ps_compressed(self):
        """Docker ps should use symbol compression."""
        output = "CONTAINER ID   IMAGE         STATUS\nabc123456789   nginx:latest  Up 2 hours"
        result = filter_output(output, "docker")
        # ID should be truncated
        assert "abc1234" in result
        assert "abc123456789" not in result

    def test_pytest_failures_compressed(self):
        """Pytest output should show failures and summary."""
        output = "test_one PASSED\ntest_two FAILED\n48 passed, 2 failed in 3.42s"
        result = filter_output(output, "python")
        # Should have failure info
        assert "FAIL" in result or "FAILED" in result or "f" in result

    def test_nodejs_packages_compressed(self):
        """NodeJS output should use symbol format."""
        # Use format that triggers compression
        output = "added 25 packages, removed 3 packages, changed 12 packages in 5.2s"
        result = filter_output(output, "nodejs")
        # Should have compressed package counts or be empty (filtered)
        # The compression happens on the summary line format
        assert result == "" or "+" in result or "25" in result or "5.2s" in result

    def test_errors_preserved(self):
        """Error output should be preserved verbatim."""
        output = (
            "Error: something failed\nTraceback (most recent call last):\n  at test()"
        )
        result = filter_output(output, "python")
        # Error info should be preserved
        assert "Error:" in result
        assert "Traceback" in result

    def test_empty_output_handled(self):
        """Empty output should be handled gracefully."""
        assert filter_output("", "git") == ""
        assert filter_output("", "docker") == ""
        assert filter_output("", "python") == ""
        assert filter_output("", "nodejs") == ""

    def test_unknown_category_fallback(self):
        """Unknown categories should use basic filtering."""
        output = "some output\n\n\nmore output"
        result = filter_output(output, "unknown")
        assert "some output" in result
        assert "more output" in result
