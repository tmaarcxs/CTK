"""Tests for pattern compression functions."""

from ctk.utils.filters import (
    _compress_files_output as compress_files_output,
)
from ctk.utils.filters import (
    _compress_network_output as compress_network_output,
)
from ctk.utils.filters import (
    _compress_patterns as compress_patterns,
)
from ctk.utils.filters import (
    _matches_expected_format as matches_expected_format,
)
from ctk.utils.filters import (
    compress_docker_output,
    compress_git_status,
    compress_nodejs_output,
    compress_pytest_output,
)


class TestCompressGitStatus:
    """Tests for git status compression."""

    def test_compress_basic_status(self):
        """Should compress basic git status."""
        lines = [
            "On branch main",
            "",
            "Changes to be committed:",
            "  modified:   src/app.ts",
            "  new file:   src/new.ts",
        ]
        result = compress_git_status(lines)
        assert "M:src/app.ts" in result
        assert "A:src/new.ts" in result

    def test_compress_groups_by_status(self):
        """Should group files by status type."""
        lines = [
            "modified:   src/app.ts",
            "modified:   src/utils.ts",
            "deleted:    src/old.ts",
        ]
        result = compress_git_status(lines)
        # All modified files should be on one line
        assert any(
            "M:" in line and "src/app.ts" in line and "src/utils.ts" in line
            for line in result
        )

    def test_compress_untracked_files(self):
        """Should handle untracked files."""
        lines = [
            "Untracked files:",
            "  config.env",
            "  .env.local",
        ]
        result = compress_git_status(lines)
        assert "?:" in result[0]
        assert "config.env" in result[0]

    def test_compress_removes_usage_hints(self):
        """Should remove usage hints."""
        lines = ['modified: file.ts (use "git add" to update)']
        result = compress_git_status(lines)
        assert "(use" not in result[0]

    def test_compress_empty_input(self):
        """Should handle empty input."""
        result = compress_git_status([])
        assert result == []


class TestCompressDockerOutput:
    """Tests for docker output compression."""

    def test_compress_docker_ps(self):
        """Should compress docker ps output."""
        lines = [
            "CONTAINER ID   IMAGE         COMMAND    STATUS       PORTS                NAMES",
            'abc123456789   nginx:latest  "/bin/sh"  Up 2 hours   0.0.0.0:80->80/tcp   web',
        ]
        result = compress_docker_output(lines)
        # Header should be removed
        assert not any("CONTAINER ID" in line for line in result)
        # Container should be compressed
        assert any("abc1234" in line for line in result)
        assert any("nginx" in line for line in result)

    def test_compress_truncates_ids(self):
        """Should truncate container IDs to 7 chars."""
        lines = ["abc123456789   nginx   Up 2 hours   web"]
        result = compress_docker_output(lines)
        assert "abc1234" in result[0]
        assert "abc123456789" not in result[0]

    def test_compress_removes_image_tag(self):
        """Should remove image tags."""
        # Need 6+ columns for compression to trigger
        lines = ["abc123   nginx:latest   /bin/sh   2h ago   Up 2 hours   web"]
        result = compress_docker_output(lines)
        assert "nginx" in result[0]

    def test_compress_compacts_duration(self):
        """Should compact duration in status."""
        # Need 6+ columns for compression to trigger
        lines = ["abc123   nginx   /bin/sh   2h ago   Up 2 hours   web"]
        result = compress_docker_output(lines)
        assert "U2h" in result[0]

    def test_compress_exited_status(self):
        """Should handle Exited status."""
        # Need 6+ columns for compression to trigger
        lines = ["abc123   nginx   /bin/sh   3d ago   Exited (0) 3 days ago   web"]
        result = compress_docker_output(lines)
        assert "X" in result[0]

    def test_compress_empty_input(self):
        """Should handle empty input."""
        result = compress_docker_output([])
        assert result == []


class TestCompressPytestOutput:
    """Tests for pytest output compression."""

    def test_compress_keeps_failures(self):
        """Should keep failure information."""
        lines = [
            "tests/test_file.py::test_one PASSED",
            "tests/test_file.py::test_two FAILED",
            "tests/test_file.py::test_three PASSED",
        ]
        result = compress_pytest_output(lines)
        # Should have FAIL indicator
        assert any("FAIL" in line for line in result)

    def test_compress_removes_passing(self):
        """Should remove passing tests."""
        lines = [
            "test_one PASSED",
            "test_two PASSED",
            "test_three PASSED",
        ]
        result = compress_pytest_output(lines)
        assert "PASSED" not in result

    def test_compress_includes_summary(self):
        """Should include test summary."""
        lines = [
            "test_one PASSED",
            "test_two FAILED",
            "48 passed, 2 failed in 3.42s",
        ]
        result = compress_pytest_output(lines)
        assert any("48p" in line for line in result)
        assert any("2f" in line for line in result)

    def test_compress_empty_input(self):
        """Should handle empty input."""
        result = compress_pytest_output([])
        assert result == []


class TestCompressNodejsOutput:
    """Tests for nodejs output compression."""

    def test_compress_package_summary(self):
        """Should compress package change summary."""
        lines = ["added 25 packages, removed 3 packages, changed 12 packages in 5.2s"]
        result = compress_nodejs_output(lines)
        assert any("+25" in line for line in result)
        assert any("-3" in line for line in result)
        assert any("~12" in line for line in result)

    def test_compress_includes_duration(self):
        """Should include duration in output."""
        lines = ["added 10 packages in 3.5s"]
        result = compress_nodejs_output(lines)
        assert any("3.5s" in line for line in result)

    def test_compress_empty_input(self):
        """Should handle empty input."""
        result = compress_nodejs_output([])
        assert result == []


class TestCompressPatterns:
    """Tests for main compress_patterns function."""

    def test_compress_git(self):
        """Should route git to git compressor."""
        lines = ["modified: src/app.ts"]
        result = compress_patterns(lines, "git")
        assert any("M:" in line for line in result)

    def test_compress_docker(self):
        """Should route docker to docker compressor."""
        lines = ["abc123456789   nginx   Up 2 hours   web"]
        result = compress_patterns(lines, "docker")
        assert any("abc1234" in line for line in result)

    def test_compress_python(self):
        """Should route python to pytest compressor."""
        lines = ["tests/test.py::test_one FAILED", "1 passed, 1 failed in 1.0s"]
        result = compress_patterns(lines, "python")
        assert any("FAIL" in line for line in result)

    def test_compress_nodejs(self):
        """Should route nodejs to nodejs compressor."""
        lines = ["added 5 packages in 2.0s"]
        result = compress_patterns(lines, "nodejs")
        assert any("+5" in line for line in result)

    def test_compress_unknown_category(self):
        """Should return unchanged for unknown category."""
        lines = ["some output"]
        result = compress_patterns(lines, "unknown")
        assert result == lines

    def test_compress_with_errors(self):
        """Should return with minimal processing if errors detected."""
        lines = ["Error: something failed", "at some.function()"]
        result = compress_patterns(lines, "python")
        # Should preserve error info
        assert any("Error:" in line for line in result)


class TestMatchesExpectedFormat:
    """Tests for format detection."""

    def test_git_format_detected(self):
        """Should recognize git status format."""
        lines = ["On branch main", "modified: src/app.ts"]
        assert matches_expected_format(lines, "git") is True

    def test_docker_format_detected(self):
        """Should recognize docker output format."""
        lines = ["CONTAINER ID   IMAGE", "abc123   nginx"]
        assert matches_expected_format(lines, "docker") is True

    def test_python_format_detected(self):
        """Should recognize pytest output format."""
        lines = ["test_one PASSED", "collected 10 items"]
        assert matches_expected_format(lines, "python") is True

    def test_nodejs_format_detected(self):
        """Should recognize npm/pnpm output format."""
        lines = ["added 5 packages"]
        assert matches_expected_format(lines, "nodejs") is True

    def test_empty_lines_not_matched(self):
        """Empty lines should not match."""
        assert matches_expected_format([], "git") is False

    def test_unknown_category_returns_true(self):
        """Unknown categories should return True."""
        lines = ["anything"]
        assert matches_expected_format(lines, "unknown") is True

    def test_files_format_detected(self):
        """Should recognize files output format."""
        lines = ["-rw-r--r--  1 user group  1234 Jan 15 file.txt"]
        assert matches_expected_format(lines, "files") is True

    def test_network_format_detected(self):
        """Should recognize network output format."""
        lines = ["HTTP/1.1 200 OK", "content-type: text/html"]
        assert matches_expected_format(lines, "network") is True


class TestCompressFilesOutput:
    """Tests for files output compression."""

    def test_compress_ls_output(self):
        """Should compress ls -l output."""
        lines = [
            "total 24",
            "-rw-r--r--  1 user group  12345 Jan 15 10:30 file.txt",
            "drwxr-xr-x  2 user group   4096 Jan 15 10:30 subdir",
        ]
        result = compress_files_output(lines)
        # Should remove 'total' line
        assert not any("total" in line for line in result)
        # Should have compact format
        assert any("file.txt" in line for line in result)

    def test_compress_grep_output(self):
        """Should compress grep output."""
        lines = [
            "src/app.ts:42:some text here",
            "src/app.ts:56:another match",
        ]
        result = compress_files_output(lines)
        # Should compact to file:line format
        assert any("src/app.ts" in line for line in result)

    def test_compress_find_output(self):
        """Should compress find output."""
        lines = [
            "./src/components/Button.tsx",
            "./src/components/Input.tsx",
        ]
        result = compress_files_output(lines)
        # Should remove ./
        assert not any(line.startswith("./") for line in result)

    def test_compress_empty_files(self):
        """Should handle empty input."""
        result = compress_files_output([])
        assert result == []


class TestCompressNetworkOutput:
    """Tests for network output compression."""

    def test_compress_curl_status(self):
        """Should extract HTTP status from curl output."""
        lines = [
            "< HTTP/1.1 200 OK",
            "< Content-Type: text/html",
            "",
            "response body",
        ]
        result = compress_network_output(lines)
        # Should have compact status
        assert any("HTTP:200" in line for line in result)

    def test_compress_curl_progress_removed(self):
        """Should remove curl progress output."""
        lines = [
            "% Total    % Received % Xferd",
            "  0     0    0     0    0     0",
            "response body",
        ]
        result = compress_network_output(lines)
        # Progress lines should be removed
        assert not any("% Total" in line for line in result)

    def test_compress_empty_network(self):
        """Should handle empty input."""
        result = compress_network_output([])
        assert result == []
