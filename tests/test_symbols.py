"""Tests for symbol dictionaries and helper functions."""

from ctk.utils.symbols import (
    DOCKER_STATE_SYMBOLS,
    GIT_STATUS_SYMBOLS,
    GIT_SYMBOL_TO_STATUS,
    NODEJS_CHANGE_SYMBOLS,
    PYTEST_RESULT_SYMBOLS,
    get_category_symbols,
    has_errors,
    symbolize_docker_state,
    symbolize_git_status,
    symbolize_nodejs_change,
    symbolize_pytest_result,
)


class TestGitStatusSymbols:
    """Tests for git status symbol mappings."""

    def test_symbol_mapping_exists(self):
        """All expected status types should have symbols."""
        expected = [
            "modified:",
            "deleted:",
            "new file:",
            "renamed:",
            "copied:",
            "type changed:",
        ]
        for status in expected:
            assert status in GIT_STATUS_SYMBOLS

    def test_symbols_are_single_char(self):
        """Status symbols should be single characters."""
        for symbol in GIT_STATUS_SYMBOLS.values():
            assert len(symbol) == 1

    def test_reverse_mapping(self):
        """Reverse mapping should be consistent."""
        for status, symbol in GIT_STATUS_SYMBOLS.items():
            assert GIT_SYMBOL_TO_STATUS[symbol] == status.rstrip(":")

    def test_symbolize_git_status_modified(self):
        """Should symbolize modified status."""
        result = symbolize_git_status("modified:   src/app.ts")
        assert result == "M:src/app.ts"

    def test_symbolize_git_status_deleted(self):
        """Should symbolize deleted status."""
        result = symbolize_git_status("deleted:    src/old.ts")
        assert result == "D:src/old.ts"

    def test_symbolize_git_status_new_file(self):
        """Should symbolize new file status."""
        result = symbolize_git_status("new file:   src/new.ts")
        assert result == "A:src/new.ts"

    def test_symbolize_git_status_removes_hints(self):
        """Should remove usage hints from status lines."""
        result = symbolize_git_status('modified: file.ts (use "git add" to update)')
        assert result == "M:file.ts"

    def test_symbolize_git_status_non_status(self):
        """Non-status lines should return None."""
        result = symbolize_git_status("On branch main")
        assert result is None


class TestDockerStateSymbols:
    """Tests for docker state symbol mappings."""

    def test_state_mapping_exists(self):
        """All expected states should have symbols."""
        expected = ["Up", "Exited", "Created", "Restarting", "Paused", "Dead"]
        for state in expected:
            assert state in DOCKER_STATE_SYMBOLS

    def test_symbols_are_short(self):
        """State symbols should be 1-2 characters."""
        for symbol in DOCKER_STATE_SYMBOLS.values():
            assert len(symbol) <= 2

    def test_symbolize_docker_state_up(self):
        """Should symbolize Up state with duration."""
        result = symbolize_docker_state("Up 2 hours")
        assert result == "U2h"

    def test_symbolize_docker_state_exited(self):
        """Should symbolize Exited state with duration."""
        result = symbolize_docker_state("Exited (0) 3 days ago")
        assert "X" in result
        assert "3d" in result

    def test_symbolize_docker_state_minutes(self):
        """Should compact minutes."""
        result = symbolize_docker_state("Up 30 minutes")
        assert result == "U30m"

    def test_symbolize_docker_state_seconds(self):
        """Should compact seconds."""
        result = symbolize_docker_state("Up 45 seconds")
        assert result == "U45s"

    def test_symbolize_docker_state_weeks(self):
        """Should compact weeks."""
        result = symbolize_docker_state("Up 2 weeks")
        assert result == "U2w"

    def test_symbolize_docker_state_no_duration(self):
        """Should handle state without duration."""
        result = symbolize_docker_state("Up")
        assert result == "U"


class TestPytestResultSymbols:
    """Tests for pytest result symbol mappings."""

    def test_result_mapping_exists(self):
        """All expected results should have symbols."""
        expected = ["PASSED", "FAILED", "ERROR", "SKIPPED", "XFAILED", "XPASSED"]
        for result in expected:
            assert result in PYTEST_RESULT_SYMBOLS

    def test_symbols_are_single_char(self):
        """Result symbols should be single characters."""
        for symbol in PYTEST_RESULT_SYMBOLS.values():
            assert len(symbol) == 1

    def test_symbolize_pytest_result_passed(self):
        """Should symbolize PASSED as dot."""
        assert symbolize_pytest_result("PASSED") == "."

    def test_symbolize_pytest_result_failed(self):
        """Should symbolize FAILED as F."""
        assert symbolize_pytest_result("FAILED") == "F"

    def test_symbolize_pytest_result_unknown(self):
        """Unknown results should return first character."""
        result = symbolize_pytest_result("UNKNOWN")
        assert result == "U"


class TestNodejsChangeSymbols:
    """Tests for nodejs change symbol mappings."""

    def test_change_mapping_exists(self):
        """All expected change types should have symbols."""
        expected = ["added", "removed", "changed", "deprecated"]
        for change in expected:
            assert change in NODEJS_CHANGE_SYMBOLS

    def test_symbolize_nodejs_change_added(self):
        """Should symbolize added as +."""
        assert symbolize_nodejs_change("added") == "+"

    def test_symbolize_nodejs_change_removed(self):
        """Should symbolize removed as -."""
        assert symbolize_nodejs_change("removed") == "-"

    def test_symbolize_nodejs_change_changed(self):
        """Should symbolize changed as ~."""
        assert symbolize_nodejs_change("changed") == "~"

    def test_symbolize_nodejs_change_case_insensitive(self):
        """Should handle different cases."""
        assert symbolize_nodejs_change("ADDED") == "+"


class TestErrorDetection:
    """Tests for error detection."""

    def test_detects_error_prefix(self):
        """Should detect Error: prefix."""
        assert has_errors(["Error: something failed"]) is True

    def test_detects_traceback(self):
        """Should detect Python traceback."""
        assert has_errors(["Traceback (most recent call last):"]) is True

    def test_detects_failed(self):
        """Should detect FAILED."""
        assert has_errors(["test_one FAILED"]) is True

    def test_detects_fatal(self):
        """Should detect git fatal error."""
        assert has_errors(["fatal: not a git repository"]) is True

    def test_no_error_in_normal_output(self):
        """Normal output should not trigger error detection."""
        assert has_errors(["M:src/app.ts", "A:src/new.ts"]) is False

    def test_no_error_in_empty_list(self):
        """Empty list should not have errors."""
        assert has_errors([]) is False


class TestGetCategorySymbols:
    """Tests for get_category_symbols function."""

    def test_git_category(self):
        """Should return git symbols."""
        symbols = get_category_symbols("git")
        assert "status" in symbols
        assert symbols["status"] == GIT_STATUS_SYMBOLS

    def test_docker_category(self):
        """Should return docker symbols."""
        symbols = get_category_symbols("docker")
        assert "state" in symbols
        assert symbols["state"] == DOCKER_STATE_SYMBOLS

    def test_python_category(self):
        """Should return python symbols."""
        symbols = get_category_symbols("python")
        assert "results" in symbols
        assert symbols["results"] == PYTEST_RESULT_SYMBOLS

    def test_nodejs_category(self):
        """Should return nodejs symbols."""
        symbols = get_category_symbols("nodejs")
        assert "changes" in symbols
        assert symbols["changes"] == NODEJS_CHANGE_SYMBOLS

    def test_unknown_category(self):
        """Unknown category should return empty dict."""
        symbols = get_category_symbols("unknown")
        assert symbols == {}
