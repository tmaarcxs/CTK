"""Tests for the command rewriter module."""

from ctk.core.rewriter import (
    COMMAND_CATEGORIES,
    RewriteResult,
    _extract_docker_subcommand,
    _extract_git_subcommand,
    _extract_simple_subcommand,
    _extract_subcommand_generic,
    extract_prefix,
    get_command_category,
    rewrite_command,
    should_rewrite_command,
)


class TestExtractPrefix:
    """Tests for prefix extraction."""

    def test_no_prefix(self):
        """Commands without prefix should return empty prefix."""
        prefix, body = extract_prefix("git status")
        assert prefix == ""
        assert body == "git status"

    def test_sudo_prefix(self):
        """Should extract sudo prefix."""
        prefix, body = extract_prefix("sudo git status")
        assert prefix == "sudo "
        assert body == "git status"

    def test_sudo_with_flags(self):
        """Should extract sudo with flags."""
        prefix, body = extract_prefix("sudo -u user git status")
        assert "sudo" in prefix
        assert body == "git status"

    def test_env_var_prefix(self):
        """Should extract environment variable prefix."""
        prefix, body = extract_prefix("FOO=bar git status")
        assert prefix == "FOO=bar "
        assert body == "git status"

    def test_multiple_env_vars(self):
        """Should extract multiple environment variables."""
        prefix, body = extract_prefix("FOO=bar BAZ=qux git status")
        assert "FOO=bar" in prefix
        assert "BAZ=qux" in prefix
        assert body == "git status"

    def test_env_and_sudo(self):
        """Should extract both env vars and sudo."""
        prefix, body = extract_prefix("FOO=bar sudo git status")
        assert "FOO=bar" in prefix
        assert "sudo" in prefix
        assert body == "git status"


class TestExtractSubcommandGeneric:
    """Tests for generic subcommand extraction."""

    def test_basic_extraction(self):
        """Should extract basic subcommand."""
        result = _extract_subcommand_generic("tool subcommand args", "tool", [])
        assert result == "subcommand"

    def test_with_strip_patterns(self):
        """Should strip patterns before extraction."""
        result = _extract_subcommand_generic(
            "tool --flag value subcommand args", "tool", [r"--flag\s+[^\s]+\s*"]
        )
        assert result == "subcommand"

    def test_empty_after_strip(self):
        """Should return None if nothing remains after stripping."""
        result = _extract_subcommand_generic(
            "tool --flag value", "tool", [r"--flag\s+[^\s]+\s*"]
        )
        assert result is None


class TestGitSubcommand:
    """Tests for git subcommand extraction."""

    def test_basic_git(self):
        """Should extract basic git subcommand."""
        assert _extract_git_subcommand("git status") == "status"
        assert _extract_git_subcommand("git commit -m 'msg'") == "commit"

    def test_git_with_c_flag(self):
        """Should strip -C flag."""
        assert _extract_git_subcommand("git -C /path status") == "status"

    def test_git_with_no_pager(self):
        """Should strip --no-pager flag."""
        assert _extract_git_subcommand("git --no-pager status") == "status"

    def test_git_with_option_equals(self):
        """Should strip --option=value patterns."""
        assert _extract_git_subcommand("git --work-tree=/tmp status") == "status"


class TestDockerSubcommand:
    """Tests for docker subcommand extraction."""

    def test_basic_docker(self):
        """Should extract basic docker subcommand."""
        assert _extract_docker_subcommand("docker ps") == "ps"
        assert _extract_docker_subcommand("docker images") == "images"

    def test_docker_compose(self):
        """Should recognize compose as subcommand."""
        assert _extract_docker_subcommand("docker compose up") == "compose"
        assert _extract_docker_subcommand("docker compose ps") == "compose"

    def test_docker_with_h_flag(self):
        """Should strip -H flag."""
        assert _extract_docker_subcommand("docker -H tcp://host ps") == "ps"

    def test_docker_with_context(self):
        """Should strip --context flag."""
        assert _extract_docker_subcommand("docker --context prod ps") == "ps"


class TestSimpleSubcommand:
    """Tests for simple subcommand extraction."""

    def test_basic_extraction(self):
        """Should extract second word."""
        assert _extract_simple_subcommand("gh pr list") == "pr"
        assert _extract_simple_subcommand("gh issue create") == "issue"

    def test_no_subcommand(self):
        """Should return None if no second word."""
        assert _extract_simple_subcommand("gh") is None


class TestShouldRewriteCommand:
    """Tests for should_rewrite_command function."""

    def test_empty_command(self):
        """Empty commands should not be rewritten."""
        result = should_rewrite_command("")
        assert result.should_rewrite is False
        assert result.category == "none"

    def test_ctk_command(self):
        """CTK commands should not be rewritten."""
        result = should_rewrite_command("ctk git status")
        assert result.should_rewrite is False

    def test_rtk_command(self):
        """RTK commands should not be rewritten."""
        result = should_rewrite_command("rtk git status")
        assert result.should_rewrite is False

    def test_heredoc_command(self):
        """Commands with heredocs should not be rewritten."""
        result = should_rewrite_command("cat <<EOF")
        assert result.should_rewrite is False

    def test_git_status(self):
        """git status should be rewritten."""
        result = should_rewrite_command("git status")
        assert result.should_rewrite is True
        assert result.category == "git"
        assert result.rewritten == "ctk git status"

    def test_git_status_with_sudo(self):
        """git status with sudo should preserve prefix."""
        result = should_rewrite_command("sudo git status")
        assert result.should_rewrite is True
        assert result.rewritten == "sudo ctk git status"

    def test_git_status_with_env(self):
        """git status with env vars should preserve prefix."""
        result = should_rewrite_command("GIT_DIR=/tmp git status")
        assert result.should_rewrite is True
        assert "GIT_DIR=/tmp" in result.rewritten
        assert "ctk git status" in result.rewritten

    def test_docker_ps(self):
        """docker ps should be rewritten."""
        result = should_rewrite_command("docker ps")
        assert result.should_rewrite is True
        assert result.category == "docker"

    def test_docker_compose(self):
        """docker compose commands should be rewritten."""
        result = should_rewrite_command("docker compose up")
        assert result.should_rewrite is True
        assert result.category == "docker"

    def test_ls_command(self):
        """ls should be rewritten."""
        result = should_rewrite_command("ls -la")
        assert result.should_rewrite is True
        assert result.category == "files"

    def test_cat_command(self):
        """cat should be rewritten."""
        result = should_rewrite_command("cat file.txt")
        assert result.should_rewrite is True
        assert result.category == "files"

    def test_pytest_command(self):
        """pytest should be rewritten."""
        result = should_rewrite_command("pytest tests/")
        assert result.should_rewrite is True
        assert result.category == "python"

    def test_npm_command(self):
        """npm test should be rewritten."""
        result = should_rewrite_command("npm test")
        assert result.should_rewrite is True
        assert result.category == "nodejs"

    def test_curl_command(self):
        """curl should be rewritten."""
        result = should_rewrite_command("curl http://example.com")
        assert result.should_rewrite is True
        assert result.category == "network"

    def test_gh_command(self):
        """gh pr should be rewritten."""
        result = should_rewrite_command("gh pr list")
        assert result.should_rewrite is True
        assert result.category == "gh"

    def test_unknown_command(self):
        """Unknown commands should not be rewritten."""
        result = should_rewrite_command("unknowncommand args")
        assert result.should_rewrite is False
        assert result.category == "none"

    def test_git_unknown_subcommand(self):
        """git with unknown subcommand should not be rewritten."""
        result = should_rewrite_command("git unknownsubcommand")
        assert result.should_rewrite is False


class TestRewriteCommand:
    """Tests for rewrite_command function."""

    def test_returns_rewritten(self):
        """Should return rewritten command string."""
        assert rewrite_command("git status") == "ctk git status"

    def test_returns_none_for_no_rewrite(self):
        """Should return None for commands that don't need rewriting."""
        assert rewrite_command("") is None
        assert rewrite_command("unknowncommand") is None


class TestGetCommandCategory:
    """Tests for get_command_category function."""

    def test_git_category(self):
        """Should return git category."""
        assert get_command_category("git status") == "git"

    def test_docker_category(self):
        """Should return docker category."""
        assert get_command_category("docker ps") == "docker"

    def test_none_category(self):
        """Should return none for unknown commands."""
        assert get_command_category("unknown") == "none"


class TestCommandCategories:
    """Tests for command category registration."""

    def test_categories_exist(self):
        """All expected categories should be registered."""
        expected = {
            "docker",
            "git",
            "gh",
            "files",
            "system",
            "python",
            "nodejs",
            "network",
        }
        assert expected <= set(COMMAND_CATEGORIES.keys())

    def test_category_has_patterns(self):
        """Each category should have patterns."""
        for name, cat in COMMAND_CATEGORIES.items():
            assert len(cat.patterns) > 0, f"Category {name} has no patterns"

    def test_category_has_name(self):
        """Each category should have correct name."""
        for name, cat in COMMAND_CATEGORIES.items():
            assert cat.name == name


class TestRewriteResult:
    """Tests for RewriteResult dataclass."""

    def test_dataclass_creation(self):
        """Should create RewriteResult correctly."""
        result = RewriteResult(
            original="git status",
            rewritten="ctk git status",
            category="git",
            should_rewrite=True,
        )
        assert result.original == "git status"
        assert result.rewritten == "ctk git status"
        assert result.category == "git"
        assert result.should_rewrite is True

    def test_dataclass_no_rewrite(self):
        """Should create RewriteResult for no-rewrite case."""
        result = RewriteResult(
            original="unknown", rewritten=None, category="none", should_rewrite=False
        )
        assert result.rewritten is None
