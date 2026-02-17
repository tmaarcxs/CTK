"""Tests for CLI commands."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from ctk.cli import cli
from ctk.core.metrics import MetricsDB


class TestCliBasics:
    """Basic CLI tests."""

    @pytest.fixture
    def runner(self):
        """Create a CLI runner."""
        return CliRunner()

    def test_version(self, runner):
        """Should show version."""
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "1.0.0" in result.output

    def test_help(self, runner):
        """Should show help."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "CTK" in result.output

    def test_no_command(self, runner):
        """Should show help when no command given."""
        result = runner.invoke(cli, [])
        assert result.exit_code == 0
        assert "CTK" in result.output or "Usage" in result.output


class TestGainCommand:
    """Tests for the gain command."""

    @pytest.fixture
    def runner(self):
        """Create a CLI runner."""
        return CliRunner()

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database with sample data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_metrics.db"
            db = MetricsDB(db_path)
            # Add sample data
            db.record(
                original_command="git status",
                rewritten_command="ctk git status",
                category="git",
                original_tokens=100,
                filtered_tokens=30,
                tokens_saved=70,
                savings_percent=70.0,
            )
            db.record(
                original_command="docker ps",
                rewritten_command="ctk docker ps",
                category="docker",
                original_tokens=200,
                filtered_tokens=50,
                tokens_saved=150,
                savings_percent=75.0,
            )
            yield db_path

    @patch("ctk.cli.get_metrics")
    def test_gain_summary(self, mock_get_metrics, runner, temp_db):
        """Should show gain summary."""
        mock_get_metrics.return_value = MetricsDB(temp_db)
        result = runner.invoke(cli, ["gain"])
        assert result.exit_code == 0
        assert "Token Savings" in result.output

    @patch("ctk.cli.get_metrics")
    def test_gain_history(self, mock_get_metrics, runner, temp_db):
        """Should show command history."""
        mock_get_metrics.return_value = MetricsDB(temp_db)
        result = runner.invoke(cli, ["gain", "--history"])
        assert result.exit_code == 0

    @patch("ctk.cli.get_metrics")
    def test_gain_daily(self, mock_get_metrics, runner, temp_db):
        """Should show daily statistics."""
        mock_get_metrics.return_value = MetricsDB(temp_db)
        result = runner.invoke(cli, ["gain", "--daily"])
        assert result.exit_code == 0

    @patch("ctk.cli.get_metrics")
    def test_gain_weekly(self, mock_get_metrics, runner, temp_db):
        """Should show weekly statistics."""
        mock_get_metrics.return_value = MetricsDB(temp_db)
        result = runner.invoke(cli, ["gain", "--weekly"])
        assert result.exit_code == 0

    @patch("ctk.cli.get_metrics")
    def test_gain_monthly(self, mock_get_metrics, runner, temp_db):
        """Should show monthly statistics."""
        mock_get_metrics.return_value = MetricsDB(temp_db)
        result = runner.invoke(cli, ["gain", "--monthly"])
        assert result.exit_code == 0

    @patch("ctk.cli.get_metrics")
    def test_gain_top_option(self, mock_get_metrics, runner, temp_db):
        """Should respect --top option."""
        mock_get_metrics.return_value = MetricsDB(temp_db)
        result = runner.invoke(cli, ["gain", "--top", "5"])
        assert result.exit_code == 0

    @patch("ctk.cli.get_metrics")
    def test_gain_export_json(self, mock_get_metrics, runner, temp_db):
        """Should export to JSON."""
        mock_get_metrics.return_value = MetricsDB(temp_db)
        result = runner.invoke(cli, ["gain", "--export", "json"])
        assert result.exit_code == 0

    @patch("ctk.cli.get_metrics")
    def test_gain_export_csv(self, mock_get_metrics, runner, temp_db):
        """Should export to CSV."""
        mock_get_metrics.return_value = MetricsDB(temp_db)
        result = runner.invoke(cli, ["gain", "--export", "csv"])
        assert result.exit_code == 0


class TestConfigCommand:
    """Tests for the config command."""

    @pytest.fixture
    def runner(self):
        """Create a CLI runner."""
        return CliRunner()

    def test_config_show(self, runner):
        """Should show configuration."""
        result = runner.invoke(cli, ["config", "--show"])
        assert result.exit_code == 0

    def test_config_init(self, runner):
        """Should initialize configuration."""
        result = runner.invoke(cli, ["config", "--init"])
        assert result.exit_code == 0


class TestDiscoverCommand:
    """Tests for the discover command."""

    @pytest.fixture
    def runner(self):
        """Create a CLI runner."""
        return CliRunner()

    def test_discover_no_history(self, runner):
        """Should handle missing history gracefully."""
        with patch("ctk.cli.Path") as mock_path:
            mock_path.home.return_value = Path("/nonexistent")
            result = runner.invoke(cli, ["discover"])
            assert result.exit_code == 0
            assert "No Claude Code history" in result.output or "analyzing" in result.output.lower()


class TestProxyCommand:
    """Tests for the proxy command."""

    @pytest.fixture
    def runner(self):
        """Create a CLI runner."""
        return CliRunner()

    @patch("ctk.cli.get_metrics")
    @patch("subprocess.run")
    def test_proxy_command(self, mock_run, mock_get_metrics, runner):
        """Should execute proxy command."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        mock_get_metrics.return_value = MagicMock()

        _ = runner.invoke(cli, ["proxy", "echo", "test"])
        # May exit with code from subprocess
        assert mock_run.called


class TestCommandGroups:
    """Tests for command groups (docker, git, kubectl)."""

    @pytest.fixture
    def runner(self):
        """Create a CLI runner."""
        return CliRunner()

    def test_docker_group_help(self, runner):
        """Should show docker group help."""
        result = runner.invoke(cli, ["docker", "--help"])
        assert result.exit_code == 0
        assert "docker" in result.output.lower()

    def test_git_group_help(self, runner):
        """Should show git group help."""
        result = runner.invoke(cli, ["git", "--help"])
        assert result.exit_code == 0
        assert "git" in result.output.lower()

    def test_kubectl_group_help(self, runner):
        """Should show kubectl group help."""
        result = runner.invoke(cli, ["kubectl", "--help"])
        assert result.exit_code == 0
        assert "kubectl" in result.output.lower()


class TestFileCommands:
    """Tests for file-related commands."""

    @pytest.fixture
    def runner(self):
        """Create a CLI runner."""
        return CliRunner()

    @patch("ctk.cli._run_command")
    def test_ls_command(self, mock_run, runner):
        """Should execute ls command."""
        _ = runner.invoke(cli, ["ls"])
        assert mock_run.called

    @patch("ctk.cli._run_command")
    def test_tree_command(self, mock_run, runner):
        """Should execute tree command."""
        _ = runner.invoke(cli, ["tree"])
        assert mock_run.called

    @patch("ctk.cli._run_command")
    def test_grep_command(self, mock_run, runner):
        """Should execute grep command."""
        _ = runner.invoke(cli, ["grep", "pattern"])
        assert mock_run.called

    @patch("ctk.cli._run_command")
    def test_find_command(self, mock_run, runner):
        """Should execute find command."""
        _ = runner.invoke(cli, ["find", "--", ".", "-type", "f"])
        assert mock_run.called


class TestSystemCommands:
    """Tests for system commands."""

    @pytest.fixture
    def runner(self):
        """Create a CLI runner."""
        return CliRunner()

    @patch("ctk.cli._run_command")
    def test_ps_command(self, mock_run, runner):
        """Should execute ps command."""
        _ = runner.invoke(cli, ["ps"])
        assert mock_run.called

    @patch("ctk.cli._run_command")
    def test_free_command(self, mock_run, runner):
        """Should execute free command."""
        _ = runner.invoke(cli, ["free"])
        assert mock_run.called

    @patch("ctk.cli._run_command")
    def test_date_command(self, mock_run, runner):
        """Should execute date command."""
        _ = runner.invoke(cli, ["date"])
        assert mock_run.called


class TestPythonCommands:
    """Tests for Python-related commands."""

    @pytest.fixture
    def runner(self):
        """Create a CLI runner."""
        return CliRunner()

    @patch("ctk.cli._run_command")
    def test_pytest_command(self, mock_run, runner):
        """Should execute pytest command."""
        _ = runner.invoke(cli, ["pytest"])
        assert mock_run.called

    @patch("ctk.cli._run_command")
    def test_ruff_command(self, mock_run, runner):
        """Should execute ruff command."""
        _ = runner.invoke(cli, ["ruff", "check", "."])
        assert mock_run.called

    @patch("ctk.cli._run_command")
    def test_pip_command(self, mock_run, runner):
        """Should execute pip command."""
        _ = runner.invoke(cli, ["pip", "list"])
        assert mock_run.called


class TestNodejsCommands:
    """Tests for Node.js-related commands."""

    @pytest.fixture
    def runner(self):
        """Create a CLI runner."""
        return CliRunner()

    @patch("ctk.cli._run_command")
    def test_npm_command(self, mock_run, runner):
        """Should execute npm command."""
        _ = runner.invoke(cli, ["npm", "test"])
        assert mock_run.called

    @patch("ctk.cli._run_command")
    def test_pnpm_command(self, mock_run, runner):
        """Should execute pnpm command."""
        _ = runner.invoke(cli, ["pnpm", "install"])
        assert mock_run.called

    @patch("ctk.cli._run_command")
    def test_vitest_command(self, mock_run, runner):
        """Should execute vitest command."""
        _ = runner.invoke(cli, ["vitest"])
        assert mock_run.called

    @patch("ctk.cli._run_command")
    def test_tsc_command(self, mock_run, runner):
        """Should execute tsc command."""
        _ = runner.invoke(cli, ["tsc"])
        assert mock_run.called


class TestNetworkCommands:
    """Tests for network commands."""

    @pytest.fixture
    def runner(self):
        """Create a CLI runner."""
        return CliRunner()

    @patch("ctk.cli._run_command")
    def test_curl_command(self, mock_run, runner):
        """Should execute curl command."""
        _ = runner.invoke(cli, ["curl", "http://example.com"])
        assert mock_run.called

    @patch("ctk.cli._run_command")
    def test_wget_command(self, mock_run, runner):
        """Should execute wget command."""
        _ = runner.invoke(cli, ["wget", "http://example.com/file"])
        assert mock_run.called


