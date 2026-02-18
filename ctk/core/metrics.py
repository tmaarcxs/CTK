"""Metrics database for tracking token savings."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .config import get_config

SCHEMA = """
CREATE TABLE IF NOT EXISTS executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT (datetime('now')),
    original_command TEXT NOT NULL,
    rewritten_command TEXT,
    category TEXT,
    exec_time_ms INTEGER,
    original_tokens INTEGER DEFAULT 0,
    filtered_tokens INTEGER DEFAULT 0,
    tokens_saved INTEGER DEFAULT 0,
    savings_percent REAL DEFAULT 0.0
);

CREATE INDEX IF NOT EXISTS idx_timestamp ON executions(timestamp);
CREATE INDEX IF NOT EXISTS idx_category ON executions(category);
"""


class MetricsDB:
    """SQLite database for tracking CTK metrics."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or get_config().database_path
        self._ensure_db()

    def _ensure_db(self) -> None:
        """Ensure database and tables exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(SCHEMA)

    def _time_filter(self, days: int) -> tuple[str, list[Any]]:
        """Build WHERE clause and params for time-based filtering.

        Args:
            days: Number of days to filter (0 = all time)

        Returns:
            Tuple of (where_clause, params)
        """
        if days > 0:
            return "WHERE timestamp >= datetime('now', ?)", [f"-{days} days"]
        return "", []

    def record(
        self,
        original_command: str,
        rewritten_command: str | None,
        category: str,
        exec_time_ms: int = 0,
        original_tokens: int = 0,
        filtered_tokens: int = 0,
        tokens_saved: int = 0,
        savings_percent: float = 0.0,
    ) -> int:
        """Record a command execution."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO executions
                (original_command, rewritten_command, category, exec_time_ms,
                 original_tokens, filtered_tokens, tokens_saved, savings_percent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    original_command,
                    rewritten_command,
                    category,
                    exec_time_ms,
                    original_tokens,
                    filtered_tokens,
                    tokens_saved,
                    savings_percent,
                ),
            )
            return cursor.lastrowid or 0

    def get_summary(self, days: int = 0) -> dict[str, Any]:
        """Get summary statistics."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            where, params = self._time_filter(days)

            row = conn.execute(
                f"""
                SELECT
                    COUNT(*) as total_commands,
                    SUM(tokens_saved) as total_saved,
                    SUM(tokens_saved) * 100.0 / NULLIF(SUM(original_tokens), 0) as overall_savings_pct,
                    SUM(CASE WHEN rewritten_command IS NOT NULL THEN 1 ELSE 0 END) as rewritten_count,
                    SUM(original_tokens) as total_original_tokens,
                    SUM(filtered_tokens) as total_filtered_tokens,
                    MAX(tokens_saved) as max_saved,
                    MIN(tokens_saved) as min_saved
                FROM executions
                {where}
                """,
                params,
            ).fetchone()

            return {
                "total_commands": row["total_commands"] or 0,
                "total_tokens_saved": row["total_saved"] or 0,
                "avg_savings_percent": round(row["overall_savings_pct"] or 0, 1),
                "rewritten_commands": row["rewritten_count"] or 0,
                "total_original_tokens": row["total_original_tokens"] or 0,
                "total_filtered_tokens": row["total_filtered_tokens"] or 0,
                "max_tokens_saved": row["max_saved"] or 0,
                "min_tokens_saved": row["min_saved"] or 0,
            }

    def get_history(
        self, limit: int = 50, category: str | None = None
    ) -> list[dict[str, Any]]:
        """Get command history."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            where = ""
            params: list[Any] = []
            if category:
                where = "WHERE category = ?"
                params = [category]

            rows = conn.execute(
                f"""
                SELECT * FROM executions
                {where}
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                params + [limit],
            ).fetchall()

            return [dict(row) for row in rows]

    def get_top_commands(self, days: int = 0, limit: int = 10) -> list[dict[str, Any]]:
        """Get top commands by usage frequency and tokens saved."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            where, params = self._time_filter(days)

            rows = conn.execute(
                f"""
                SELECT
                    original_command,
                    COUNT(*) as count,
                    SUM(tokens_saved) as tokens_saved,
                    AVG(savings_percent) as avg_savings,
                    SUM(original_tokens) as original_tokens,
                    SUM(filtered_tokens) as filtered_tokens
                FROM executions
                {where}
                GROUP BY original_command
                ORDER BY count DESC
                LIMIT ?
                """,
                params + [limit],
            ).fetchall()

            return [dict(row) for row in rows]

    def get_top_savers(self, days: int = 0, limit: int = 10) -> list[dict[str, Any]]:
        """Get commands with highest token savings."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            where, params = self._time_filter(days)

            rows = conn.execute(
                f"""
                SELECT
                    original_command,
                    COUNT(*) as count,
                    SUM(tokens_saved) as tokens_saved,
                    AVG(savings_percent) as avg_savings,
                    SUM(original_tokens) as original_tokens,
                    SUM(filtered_tokens) as filtered_tokens
                FROM executions
                {where}
                GROUP BY original_command
                ORDER BY tokens_saved DESC
                LIMIT ?
                """,
                params + [limit],
            ).fetchall()

            return [dict(row) for row in rows]

    def get_by_category(self, days: int = 0) -> dict[str, dict[str, Any]]:
        """Get statistics grouped by category."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            where, params = self._time_filter(days)

            rows = conn.execute(
                f"""
                SELECT
                    category,
                    COUNT(*) as count,
                    SUM(tokens_saved) as tokens_saved,
                    SUM(tokens_saved) * 100.0 / NULLIF(SUM(original_tokens), 0) as overall_savings_pct,
                    SUM(original_tokens) as original_tokens,
                    SUM(filtered_tokens) as filtered_tokens
                FROM executions
                {where}
                GROUP BY category
                ORDER BY tokens_saved DESC
                """,
                params,
            ).fetchall()

            return {
                row["category"]: {
                    "count": row["count"],
                    "tokens_saved": row["tokens_saved"] or 0,
                    "avg_savings_percent": round(row["overall_savings_pct"] or 0, 1),
                    "original_tokens": row["original_tokens"] or 0,
                    "filtered_tokens": row["filtered_tokens"] or 0,
                }
                for row in rows
            }

    def get_daily_stats(self, days: int = 7) -> list[dict[str, Any]]:
        """Get daily statistics."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            rows = conn.execute(
                """
                SELECT
                    date(timestamp) as date,
                    COUNT(*) as commands,
                    SUM(tokens_saved) as tokens_saved,
                    SUM(tokens_saved) * 100.0 / NULLIF(SUM(original_tokens), 0) as avg_savings
                FROM executions
                WHERE timestamp >= datetime('now', ?)
                GROUP BY date(timestamp)
                ORDER BY date DESC
                """,
                [f"-{days} days"],
            ).fetchall()

            return [dict(row) for row in rows]

    def export(self, format: str = "json", output_path: Path | None = None) -> str:
        """Export metrics to JSON or CSV."""
        history = self.get_history(limit=10000)

        if format == "json":
            data = json.dumps(history, indent=2, default=str)
        else:  # CSV
            import csv
            import io

            output = io.StringIO()
            if history:
                writer = csv.DictWriter(output, fieldnames=history[0].keys())
                writer.writeheader()
                writer.writerows(history)
            data = output.getvalue()

        if output_path:
            output_path.write_text(data)

        return data

    def clear(self, older_than_days: int = 0) -> int:
        """Clear old records."""
        with sqlite3.connect(self.db_path) as conn:
            if older_than_days > 0:
                cursor = conn.execute(
                    "DELETE FROM executions WHERE timestamp < datetime('now', ?)",
                    [f"-{older_than_days} days"],
                )
            else:
                cursor = conn.execute("DELETE FROM executions")
            return cursor.rowcount

    def migrate_from_rtk(self, rtk_db_path: Path) -> int:
        """Migrate data from RTK history.db."""
        if not rtk_db_path.exists():
            return 0

        migrated = 0
        with sqlite3.connect(rtk_db_path) as rtk_conn:
            rtk_conn.row_factory = sqlite3.Row
            try:
                rows = rtk_conn.execute(
                    "SELECT * FROM history ORDER BY timestamp"
                ).fetchall()

                for row in rows:
                    self.record(
                        original_command=row.get("command", ""),
                        rewritten_command=row.get("rewritten_command"),
                        category=row.get("category", "unknown"),
                        original_tokens=row.get("original_tokens", 0),
                        filtered_tokens=row.get("filtered_tokens", 0),
                        tokens_saved=row.get("tokens_saved", 0),
                        savings_percent=row.get("savings_percent", 0),
                    )
                    migrated += 1
            except sqlite3.OperationalError:
                pass  # Table doesn't exist or wrong schema

        return migrated


# Global instance
_metrics: MetricsDB | None = None


def get_metrics() -> MetricsDB:
    """Get the global metrics database instance."""
    global _metrics
    if _metrics is None:
        _metrics = MetricsDB()
    return _metrics
