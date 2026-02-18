"""Tests for the metrics database module."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from ctk.core.metrics import MetricsDB


class TestMetricsDB:
    """Tests for MetricsDB class."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_metrics.db"
            yield MetricsDB(db_path)

    @pytest.fixture
    def populated_db(self, temp_db):
        """Create a database with sample data."""
        temp_db.record(
            original_command="git status",
            rewritten_command="ctk git status",
            category="git",
            original_tokens=100,
            filtered_tokens=30,
            tokens_saved=70,
            savings_percent=70.0,
        )
        temp_db.record(
            original_command="docker ps",
            rewritten_command="ctk docker ps",
            category="docker",
            original_tokens=200,
            filtered_tokens=50,
            tokens_saved=150,
            savings_percent=75.0,
        )
        temp_db.record(
            original_command="git log",
            rewritten_command="ctk git log",
            category="git",
            original_tokens=150,
            filtered_tokens=60,
            tokens_saved=90,
            savings_percent=60.0,
        )
        yield temp_db

    def test_db_creation(self, temp_db):
        """Database should be created with correct schema."""
        assert temp_db.db_path.exists()

    def test_record_insert(self, temp_db):
        """Should insert a record and return ID."""
        row_id = temp_db.record(
            original_command="git status",
            rewritten_command="ctk git status",
            category="git",
            original_tokens=100,
            filtered_tokens=30,
            tokens_saved=70,
            savings_percent=70.0,
        )
        assert row_id > 0

    def test_get_summary_empty(self, temp_db):
        """Summary of empty database should return zeros."""
        summary = temp_db.get_summary()
        assert summary["total_commands"] == 0
        assert summary["total_tokens_saved"] == 0
        assert summary["rewritten_commands"] == 0

    def test_get_summary(self, populated_db):
        """Summary should aggregate statistics correctly."""
        summary = populated_db.get_summary()
        assert summary["total_commands"] == 3
        assert summary["total_tokens_saved"] == 310  # 70 + 150 + 90
        assert summary["rewritten_commands"] == 3
        assert summary["total_original_tokens"] == 450  # 100 + 200 + 150
        assert summary["total_filtered_tokens"] == 140  # 30 + 50 + 60

    def test_get_history(self, populated_db):
        """Should return command history."""
        history = populated_db.get_history(limit=10)
        assert len(history) == 3

    def test_get_history_with_category(self, populated_db):
        """Should filter history by category."""
        history = populated_db.get_history(limit=10, category="git")
        assert len(history) == 2
        for entry in history:
            assert entry["category"] == "git"

    def test_get_history_limit(self, populated_db):
        """Should respect limit parameter."""
        history = populated_db.get_history(limit=2)
        assert len(history) == 2

    def test_get_by_category(self, populated_db):
        """Should group statistics by category."""
        by_category = populated_db.get_by_category()
        assert "git" in by_category
        assert "docker" in by_category
        assert by_category["git"]["count"] == 2
        assert by_category["docker"]["count"] == 1
        assert by_category["git"]["tokens_saved"] == 160  # 70 + 90
        assert by_category["docker"]["tokens_saved"] == 150

    def test_get_top_commands(self, populated_db):
        """Should return top commands by usage."""
        top = populated_db.get_top_commands(limit=10)
        assert len(top) == 3
        # All commands have count 1, so order is by insertion
        commands = [c["original_command"] for c in top]
        assert "git status" in commands
        assert "docker ps" in commands

    def test_get_top_savers(self, populated_db):
        """Should return commands sorted by tokens saved."""
        top = populated_db.get_top_savers(limit=10)
        assert len(top) == 3
        # docker ps should be first (150 tokens saved)
        assert top[0]["original_command"] == "docker ps"
        assert top[0]["tokens_saved"] == 150

    def test_get_daily_stats(self, populated_db):
        """Should return daily statistics."""
        daily = populated_db.get_daily_stats(days=7)
        assert len(daily) >= 1
        # Today should have all 3 commands
        today = datetime.now().strftime("%Y-%m-%d")
        today_stat = next((d for d in daily if d["date"] == today), None)
        if today_stat:
            assert today_stat["commands"] == 3

    def test_export_json(self, populated_db):
        """Should export to JSON format."""
        json_data = populated_db.export(format="json")
        assert "git status" in json_data
        assert "docker ps" in json_data

    def test_export_csv(self, populated_db):
        """Should export to CSV format."""
        csv_data = populated_db.export(format="csv")
        assert "original_command" in csv_data
        assert "git status" in csv_data

    def test_export_to_file(self, populated_db):
        """Should export to file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            output_path = Path(f.name)

        try:
            populated_db.export(format="json", output_path=output_path)
            assert output_path.exists()
            content = output_path.read_text()
            assert "git status" in content
        finally:
            output_path.unlink(missing_ok=True)

    def test_clear_all(self, populated_db):
        """Should clear all records."""
        count = populated_db.clear()
        assert count == 3
        summary = populated_db.get_summary()
        assert summary["total_commands"] == 0

    def test_clear_old_records(self, populated_db):
        """Should only clear records older than specified days."""
        # Records are new, so clearing old records should remove nothing
        count = populated_db.clear(older_than_days=1)
        assert count == 0
        summary = populated_db.get_summary()
        assert summary["total_commands"] == 3

    def test_record_without_rewritten(self, temp_db):
        """Should record commands without rewritten version."""
        row_id = temp_db.record(
            original_command="proxy command",
            rewritten_command=None,
            category="proxy",
        )
        assert row_id > 0
        history = temp_db.get_history(limit=1)
        assert history[0]["rewritten_command"] is None

    def test_summary_avg_savings(self, populated_db):
        """Should calculate overall savings percent from total tokens."""
        summary = populated_db.get_summary()
        # Total saved: 310, Total original: 450 -> 310/450 = 68.89%
        assert abs(summary["avg_savings_percent"] - 68.9) < 0.2


class TestMetricsDBEdgeCases:
    """Edge case tests for MetricsDB."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_metrics.db"
            yield MetricsDB(db_path)

    def test_empty_category_filter(self, temp_db):
        """Should handle empty results for category filter."""
        history = temp_db.get_history(limit=10, category="nonexistent")
        assert history == []

    def test_zero_tokens(self, temp_db):
        """Should handle zero token values."""
        temp_db.record(
            original_command="small command",
            rewritten_command="ctk small command",
            category="test",
            original_tokens=0,
            filtered_tokens=0,
            tokens_saved=0,
            savings_percent=0.0,
        )
        summary = temp_db.get_summary()
        assert summary["total_tokens_saved"] == 0

    def test_large_token_values(self, temp_db):
        """Should handle large token values."""
        large_value = 10_000_000
        temp_db.record(
            original_command="big output command",
            rewritten_command="ctk big output command",
            category="test",
            original_tokens=large_value,
            filtered_tokens=large_value // 10,
            tokens_saved=large_value - large_value // 10,
            savings_percent=90.0,
        )
        summary = temp_db.get_summary()
        assert summary["total_tokens_saved"] == large_value - large_value // 10

    def test_special_characters_in_command(self, temp_db):
        """Should handle special characters in commands."""
        special_cmd = "echo 'hello \"world\"' && cat file.txt | grep 'pattern'"
        temp_db.record(
            original_command=special_cmd,
            rewritten_command=f"ctk {special_cmd}",
            category="test",
        )
        history = temp_db.get_history(limit=1)
        assert history[0]["original_command"] == special_cmd

    def test_unicode_in_command(self, temp_db):
        """Should handle unicode in commands."""
        unicode_cmd = "echo 'hello 世界' 🚀"
        temp_db.record(
            original_command=unicode_cmd,
            rewritten_command=f"ctk {unicode_cmd}",
            category="test",
        )
        history = temp_db.get_history(limit=1)
        assert history[0]["original_command"] == unicode_cmd


class TestTimeFilterHelper:
    """Tests for _time_filter helper method."""

    def test_no_filter(self):
        """When days=0, return empty WHERE clause."""
        from ctk.core.metrics import MetricsDB

        db = MetricsDB()
        where, params = db._time_filter(0)
        assert where == ""
        assert params == []

    def test_filter_7_days(self):
        """When days=7, return proper WHERE clause."""
        from ctk.core.metrics import MetricsDB

        db = MetricsDB()
        where, params = db._time_filter(7)
        assert "timestamp >= datetime" in where
        assert params == ["-7 days"]

    def test_filter_30_days(self):
        """When days=30, return proper WHERE clause."""
        from ctk.core.metrics import MetricsDB

        db = MetricsDB()
        where, params = db._time_filter(30)
        assert params == ["-30 days"]
