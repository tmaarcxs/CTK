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
        assert "1.4" in result.output

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
            assert (
                "No Claude Code history" in result.output
                or "analyzing" in result.output.lower()
            )


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
    """Tests for command groups (docker, git, etc.)."""

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


class TestFlagPassthrough:
    """Tests for flag passthrough in various commands."""

    @pytest.fixture
    def runner(self):
        """Create a CLI runner."""
        return CliRunner()

    @patch("ctk.cli._run_command")
    def test_docker_compose_exec_with_t_flag(self, mock_run, runner):
        """Should pass -T flag to docker compose exec."""
        _result = runner.invoke(
            cli, ["docker", "compose", "exec", "-T", "backend", "python", "test.py"]
        )
        assert mock_run.called
        # Verify the command includes the -T flag
        call_args = mock_run.call_args[0][0]
        assert "-T" in call_args

    @patch("ctk.cli._run_command")
    def test_docker_exec_with_it_flags(self, mock_run, runner):
        """Should pass -it flags to docker exec."""
        _result = runner.invoke(cli, ["docker", "exec", "-it", "container", "bash"])
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        assert "-it" in call_args

    @patch("ctk.cli._run_command")
    def test_curl_with_multiple_flags(self, mock_run, runner):
        """Should pass multiple flags to curl."""
        _result = runner.invoke(cli, ["curl", "-s", "-X", "GET", "http://example.com"])
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        assert "-s" in call_args
        assert "-X" in call_args
        assert "GET" in call_args

    @patch("ctk.cli._run_command")
    def test_git_status_with_flags(self, mock_run, runner):
        """Should pass flags to git status."""
        _result = runner.invoke(cli, ["git", "status", "--short", "--branch"])
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        assert "--short" in call_args
        assert "--branch" in call_args

    @patch("ctk.cli._run_command")
    def test_grep_with_rn_flags(self, mock_run, runner):
        """Should pass -r -n flags to grep."""
        _result = runner.invoke(cli, ["grep", "-r", "-n", "pattern", "."])
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        assert "-r" in call_args
        assert "-n" in call_args

    @patch("ctk.cli._run_command")
    def test_npm_with_save_dev_flag(self, mock_run, runner):
        """Should pass --save-dev flag to npm."""
        _result = runner.invoke(cli, ["npm", "install", "--save-dev", "package"])
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        assert "--save-dev" in call_args

    @patch("ctk.cli._run_command")
    def test_pytest_with_xv_flags(self, mock_run, runner):
        """Should pass -x -v flags to pytest."""
        _result = runner.invoke(cli, ["pytest", "-x", "-v", "tests/"])
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        assert "-x" in call_args
        assert "-v" in call_args

    @patch("ctk.cli._run_command")
    def test_docker_compose_up_with_d_flag(self, mock_run, runner):
        """Should pass -d flag to docker compose up."""
        _result = runner.invoke(cli, ["docker", "compose", "up", "-d"])
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        assert "-d" in call_args

    @patch("ctk.cli._run_command")
    def test_docker_compose_logs_with_f_flag(self, mock_run, runner):
        """Should pass -f flag to docker compose logs."""
        _result = runner.invoke(cli, ["docker", "compose", "logs", "-f", "backend"])
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        assert "-f" in call_args

    @patch("ctk.cli._run_command")
    def test_docker_ps_with_a_flag(self, mock_run, runner):
        """Should pass -a flag to docker ps."""
        _result = runner.invoke(cli, ["docker", "ps", "-a"])
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        assert "-a" in call_args

    @patch("ctk.cli._run_command")
    def test_pip_install_with_e_flag(self, mock_run, runner):
        """Should pass -e flag to pip install."""
        _result = runner.invoke(cli, ["pip", "install", "-e", "."])
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        assert "-e" in call_args

    @patch("ctk.cli._run_command")
    def test_find_with_type_flag(self, mock_run, runner):
        """Should pass -type flag to find."""
        _result = runner.invoke(cli, ["find", ".", "-type", "f", "-name", "*.py"])
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        assert "-type" in call_args
        assert "f" in call_args

    @patch("ctk.cli._run_command")
    def test_sed_with_i_flag(self, mock_run, runner):
        """Should pass -i flag to sed."""
        _result = runner.invoke(cli, ["sed", "-i", "s/old/new/g", "file.txt"])
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        assert "-i" in call_args

    @patch("ctk.cli._run_command")
    def test_jq_with_r_flag(self, mock_run, runner):
        """Should pass -r flag to jq."""
        _result = runner.invoke(cli, ["jq", "-r", ".name", "data.json"])
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        assert "-r" in call_args

    @patch("ctk.cli._run_command")
    def test_apt_with_y_flag(self, mock_run, runner):
        """Should pass -y flag to apt."""
        _result = runner.invoke(cli, ["apt", "install", "-y", "package"])
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        assert "-y" in call_args

    @patch("ctk.cli._run_command")
    def test_docker_compose_exec_complex_command(self, mock_run, runner):
        """Should pass complex command with multiple flags."""
        _result = runner.invoke(
            cli,
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "-e",
                "VAR=value",
                "backend",
                "python",
                "-m",
                "pytest",
                "-xvs",
                "tests/",
            ],
        )
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        assert "-T" in call_args
        assert "-e" in call_args
        assert "VAR=value" in call_args


class TestCommandRegistry:
    """Tests for command registry pattern."""

    def test_registry_has_docker_commands(self):
        from ctk.cli import COMMAND_REGISTRY

        docker_commands = [(g, c) for (g, c) in COMMAND_REGISTRY.keys() if g == "docker"]
        assert ("docker", "ps") in docker_commands
        assert ("docker", "images") in docker_commands
        assert ("docker", "logs") in docker_commands

    def test_registry_has_git_commands(self):
        from ctk.cli import COMMAND_REGISTRY

        git_commands = [(g, c) for (g, c) in COMMAND_REGISTRY.keys() if g == "git"]
        assert ("git", "status") in git_commands
        assert ("git", "log") in git_commands
        assert ("git", "diff") in git_commands

    def test_registry_has_ungrouped_commands(self):
        from ctk.cli import COMMAND_REGISTRY

        ungrouped = [(g, c) for (g, c) in COMMAND_REGISTRY.keys() if g == ""]
        assert ("", "npm") in ungrouped
        assert ("", "pip") in ungrouped
