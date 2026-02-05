"""
Weekly Export for Claude Code Analysis
======================================

Generates a comprehensive export of trading data, logs, and playbooks
for weekly analysis and optimization by Claude Code.

The export creates:
1. analysis_export.json - Structured data for parsing
2. ANALYSIS_REPORT.md - Human-readable summary
3. Copies relevant playbooks to history
"""

import json
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

# Try to import psycopg2 for database access
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    HAS_DB = True
except ImportError:
    HAS_DB = False
    RealDictCursor = None


class WeeklyExporter:
    """
    Exports trading data for weekly Claude Code analysis.

    Creates a comprehensive snapshot of:
    - Trading performance
    - Error patterns
    - Playbook effectiveness
    - System health
    - Recommendations for improvement
    """

    EXPORT_DIR = Path("analysis_exports")
    PLAYBOOK_HISTORY = Path("config/playbook_history")
    LOGS_DIR = Path("logs")

    def __init__(self):
        """Initialize the exporter."""
        self.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        self.PLAYBOOK_HISTORY.mkdir(parents=True, exist_ok=True)
        self.db_url = os.getenv("DATABASE_URL")

    def _get_db_connection(self):
        """Get database connection if available."""
        if not HAS_DB or not self.db_url:
            return None
        try:
            return psycopg2.connect(self.db_url)
        except Exception:
            return None

    def export_weekly_analysis(self) -> dict:
        """
        Generate the complete weekly export.

        Returns:
            Dict with export paths and summary
        """
        timestamp = datetime.now()
        week_start = timestamp - timedelta(days=7)
        export_name = f"week_{timestamp.strftime('%Y%m%d')}"

        # Create export subdirectory
        export_path = self.EXPORT_DIR / export_name
        export_path.mkdir(parents=True, exist_ok=True)

        # Gather all data
        export_data = {
            "metadata": {
                "generated_at": timestamp.isoformat(),
                "week_start": week_start.isoformat(),
                "week_end": timestamp.isoformat(),
                "export_name": export_name,
            },
            "performance": self._get_performance_data(week_start, timestamp),
            "trades": self._get_trades_data(week_start, timestamp),
            "errors": self._get_errors_summary(),
            "decisions": self._get_decisions_summary(week_start, timestamp),
            "playbook_stats": self._get_playbook_stats(),
            "system_health": self._get_system_health(),
            "recommendations": [],  # Will be filled by analysis
        }

        # Save JSON export
        json_path = export_path / "analysis_export.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2, default=str)

        # Generate markdown report
        md_path = export_path / "ANALYSIS_REPORT.md"
        self._generate_markdown_report(export_data, md_path)

        # Copy current playbook to history
        self._archive_playbook(timestamp)

        # Copy relevant logs
        self._copy_logs(export_path, week_start)

        return {
            "export_path": str(export_path),
            "json_export": str(json_path),
            "md_report": str(md_path),
            "summary": {
                "total_trades": export_data["trades"]["total_count"],
                "win_rate": export_data["trades"].get("win_rate", 0),
                "total_pnl": export_data["performance"].get("total_pnl", 0),
                "error_count": export_data["errors"]["total_count"],
            },
        }

    def _get_performance_data(self, start: datetime, end: datetime) -> dict:
        """Get performance metrics for the week."""
        conn = self._get_db_connection()
        if not conn:
            return {"error": "Database not available", "total_pnl": 0}

        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get daily P&L
                cur.execute(
                    """
                    SELECT
                        DATE(created_at) as date,
                        SUM(CASE WHEN outcome_1h > 0 THEN outcome_1h ELSE 0 END) as profit,
                        SUM(CASE WHEN outcome_1h < 0 THEN outcome_1h ELSE 0 END) as loss
                    FROM trades
                    WHERE created_at BETWEEN %s AND %s
                    GROUP BY DATE(created_at)
                    ORDER BY date
                    """,
                    (start, end),
                )
                daily = cur.fetchall()

                total_profit = sum(d["profit"] or 0 for d in daily)
                total_loss = sum(d["loss"] or 0 for d in daily)

                return {
                    "total_pnl": total_profit + total_loss,
                    "total_profit": total_profit,
                    "total_loss": total_loss,
                    "daily_breakdown": [dict(d) for d in daily],
                    "best_day": max(daily, key=lambda x: (x["profit"] or 0) + (x["loss"] or 0))
                    if daily
                    else None,
                    "worst_day": min(daily, key=lambda x: (x["profit"] or 0) + (x["loss"] or 0))
                    if daily
                    else None,
                }
        except Exception as e:
            return {"error": str(e), "total_pnl": 0}
        finally:
            conn.close()

    def _get_trades_data(self, start: datetime, end: datetime) -> dict:
        """Get trade statistics for the week."""
        conn = self._get_db_connection()
        if not conn:
            return {"error": "Database not available", "total_count": 0}

        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Total trades
                cur.execute(
                    """
                    SELECT
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE outcome_1h > 0) as winning,
                        COUNT(*) FILTER (WHERE outcome_1h < 0) as losing,
                        AVG(outcome_1h) as avg_outcome,
                        AVG(confidence) as avg_confidence
                    FROM trades
                    WHERE created_at BETWEEN %s AND %s
                    """,
                    (start, end),
                )
                stats = cur.fetchone()

                # By symbol
                cur.execute(
                    """
                    SELECT
                        symbol,
                        COUNT(*) as trades,
                        AVG(outcome_1h) as avg_outcome
                    FROM trades
                    WHERE created_at BETWEEN %s AND %s
                    GROUP BY symbol
                    """,
                    (start, end),
                )
                by_symbol = cur.fetchall()

                # By Fear & Greed range
                cur.execute(
                    """
                    SELECT
                        CASE
                            WHEN fear_greed_at_entry < 20 THEN 'extreme_fear'
                            WHEN fear_greed_at_entry < 40 THEN 'fear'
                            WHEN fear_greed_at_entry < 60 THEN 'neutral'
                            WHEN fear_greed_at_entry < 80 THEN 'greed'
                            ELSE 'extreme_greed'
                        END as fg_range,
                        COUNT(*) as trades,
                        AVG(outcome_1h) as avg_outcome
                    FROM trades
                    WHERE created_at BETWEEN %s AND %s
                      AND fear_greed_at_entry IS NOT NULL
                    GROUP BY fg_range
                    """,
                    (start, end),
                )
                by_fg = cur.fetchall()

                total = stats["total"] if stats else 0
                winning = stats["winning"] if stats else 0

                return {
                    "total_count": total,
                    "winning_count": winning,
                    "losing_count": stats["losing"] if stats else 0,
                    "win_rate": winning / total if total > 0 else 0,
                    "avg_outcome": stats["avg_outcome"] if stats else 0,
                    "avg_confidence": stats["avg_confidence"] if stats else 0,
                    "by_symbol": [dict(s) for s in by_symbol],
                    "by_fear_greed": [dict(f) for f in by_fg],
                }
        except Exception as e:
            return {"error": str(e), "total_count": 0}
        finally:
            conn.close()

    def _get_errors_summary(self) -> dict:
        """Get error summary from logs."""
        error_log = self.LOGS_DIR / "error.log"
        if not error_log.exists():
            return {"total_count": 0, "categories": {}}

        errors = []
        categories = {}

        try:
            with open(error_log, encoding="utf-8") as f:
                for line in f:
                    try:
                        error = json.loads(line)
                        errors.append(error)

                        # Categorize by error type
                        error_type = error.get("data", {}).get("error_type", "Unknown")
                        categories[error_type] = categories.get(error_type, 0) + 1
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass

        # Get most common errors
        sorted_categories = sorted(categories.items(), key=lambda x: x[1], reverse=True)

        return {
            "total_count": len(errors),
            "categories": dict(sorted_categories[:10]),
            "recent_errors": errors[-20:],
            "most_common": sorted_categories[0] if sorted_categories else None,
        }

    def _get_decisions_summary(self, start: datetime, end: datetime) -> dict:
        """Get AI decision summary from logs."""
        decision_log = self.LOGS_DIR / "decision.log"
        if not decision_log.exists():
            return {"total_count": 0}

        decisions = []
        actions = {"BUY": 0, "SELL": 0, "HOLD": 0}
        confidence_sum = 0

        try:
            with open(decision_log, encoding="utf-8") as f:
                for line in f:
                    try:
                        decision = json.loads(line)
                        # Check if within date range
                        ts = datetime.fromisoformat(decision["timestamp"].replace("Z", "+00:00"))
                        if start <= ts.replace(tzinfo=None) <= end:
                            decisions.append(decision)
                            action = decision.get("data", {}).get("action", "HOLD")
                            actions[action] = actions.get(action, 0) + 1
                            confidence_sum += decision.get("data", {}).get("confidence", 0)
                    except (json.JSONDecodeError, KeyError, ValueError):
                        continue
        except Exception:
            pass

        return {
            "total_count": len(decisions),
            "action_distribution": actions,
            "avg_confidence": confidence_sum / len(decisions) if decisions else 0,
            "high_confidence_count": sum(
                1 for d in decisions if d.get("data", {}).get("confidence", 0) > 0.7
            ),
        }

    def _get_playbook_stats(self) -> dict:
        """Get playbook statistics."""
        playbook_path = Path("config/TRADING_PLAYBOOK.md")
        history_count = len(list(self.PLAYBOOK_HISTORY.glob("playbook_v*.md")))

        stats = {
            "current_version": 0,
            "history_count": history_count,
            "last_updated": None,
        }

        if playbook_path.exists():
            content = playbook_path.read_text(encoding="utf-8")
            # Extract version
            for line in content.split("\n"):
                if line.startswith("Version:"):
                    try:
                        stats["current_version"] = int(line.split(":")[1].strip())
                    except ValueError:
                        pass
                elif line.startswith("Letzte Aktualisierung:"):
                    stats["last_updated"] = line.split(":", 1)[1].strip()
                    break

        return stats

    def _get_system_health(self) -> dict:
        """Get system health indicators."""
        system_log = self.LOGS_DIR / "system.log"
        health = {
            "status": "unknown",
            "uptime_data": [],
            "last_health_check": None,
        }

        if system_log.exists():
            try:
                with open(system_log, encoding="utf-8") as f:
                    for line in f:
                        try:
                            entry = json.loads(line)
                            if entry.get("data", {}).get("event") == "health_check":
                                health["last_health_check"] = entry
                                health["status"] = entry.get("data", {}).get("status", "unknown")
                        except json.JSONDecodeError:
                            continue
            except Exception:
                pass

        return health

    def _generate_markdown_report(self, data: dict, output_path: Path):
        """Generate a human-readable markdown report."""
        md = f"""# Weekly Trading Analysis Report

Generated: {data["metadata"]["generated_at"]}
Period: {data["metadata"]["week_start"][:10]} to {data["metadata"]["week_end"][:10]}

---

## Performance Summary

| Metric | Value |
|--------|-------|
| Total P&L | ${data["performance"].get("total_pnl", 0):.2f} |
| Total Profit | ${data["performance"].get("total_profit", 0):.2f} |
| Total Loss | ${data["performance"].get("total_loss", 0):.2f} |

---

## Trade Statistics

| Metric | Value |
|--------|-------|
| Total Trades | {data["trades"].get("total_count", 0)} |
| Winning Trades | {data["trades"].get("winning_count", 0)} |
| Losing Trades | {data["trades"].get("losing_count", 0)} |
| Win Rate | {data["trades"].get("win_rate", 0):.1%} |
| Avg Confidence | {data["trades"].get("avg_confidence", 0):.2f} |

### By Symbol
"""
        for symbol in data["trades"].get("by_symbol", []):
            md += f"- **{symbol['symbol']}**: {symbol['trades']} trades, avg outcome: {symbol['avg_outcome']:.4f}\n"

        md += """
### By Fear & Greed Range
"""
        for fg in data["trades"].get("by_fear_greed", []):
            md += f"- **{fg['fg_range']}**: {fg['trades']} trades, avg outcome: {fg['avg_outcome']:.4f}\n"

        md += f"""
---

## Error Analysis

| Metric | Value |
|--------|-------|
| Total Errors | {data["errors"].get("total_count", 0)} |
| Most Common | {data["errors"].get("most_common", ("None", 0))} |

### Error Categories
"""
        for error_type, count in data["errors"].get("categories", {}).items():
            md += f"- **{error_type}**: {count}\n"

        md += f"""
---

## AI Decisions

| Metric | Value |
|--------|-------|
| Total Decisions | {data["decisions"].get("total_count", 0)} |
| Avg Confidence | {data["decisions"].get("avg_confidence", 0):.2f} |
| High Confidence (>0.7) | {data["decisions"].get("high_confidence_count", 0)} |

### Action Distribution
"""
        for action, count in data["decisions"].get("action_distribution", {}).items():
            md += f"- **{action}**: {count}\n"

        md += f"""
---

## Playbook Status

| Metric | Value |
|--------|-------|
| Current Version | {data["playbook_stats"].get("current_version", 0)} |
| History Count | {data["playbook_stats"].get("history_count", 0)} |
| Last Updated | {data["playbook_stats"].get("last_updated", "N/A")} |

---

## Recommendations for Claude Code

Based on this data, analyze and provide recommendations for:

1. **Playbook Updates**: What rules should be added/modified based on trade outcomes?
2. **Error Patterns**: What code changes would reduce the most common errors?
3. **Decision Quality**: How can AI confidence be improved?
4. **Risk Management**: Are there patterns in losing trades that suggest rule changes?
5. **System Health**: Any infrastructure improvements needed?

---

*This report was auto-generated for Claude Code analysis.*
"""

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(md)

    def _archive_playbook(self, timestamp: datetime):
        """Archive current playbook to history."""
        current = Path("config/TRADING_PLAYBOOK.md")
        if not current.exists():
            return

        # Read current version
        content = current.read_text(encoding="utf-8")
        version = 0
        for line in content.split("\n"):
            if line.startswith("Version:"):
                try:
                    version = int(line.split(":")[1].strip())
                except ValueError:
                    pass
                break

        # Archive with timestamp
        archive_name = f"playbook_v{version}_{timestamp.strftime('%Y%m%d')}.md"
        archive_path = self.PLAYBOOK_HISTORY / archive_name
        shutil.copy2(current, archive_path)

    def _copy_logs(self, export_path: Path, start: datetime):
        """Copy relevant log entries to export."""
        logs_export = export_path / "logs"
        logs_export.mkdir(exist_ok=True)

        # Copy recent portions of each log
        for log_file in self.LOGS_DIR.glob("*.log"):
            if log_file.stat().st_size > 0:
                dest = logs_export / log_file.name
                # For large files, only copy last 1MB
                if log_file.stat().st_size > 1024 * 1024:
                    with open(log_file, "rb") as f:
                        f.seek(-1024 * 1024, 2)  # Last 1MB
                        content = f.read()
                    with open(dest, "wb") as f:
                        f.write(content)
                else:
                    shutil.copy2(log_file, dest)


def run_weekly_export() -> dict:
    """Run the weekly export and return results."""
    exporter = WeeklyExporter()
    return exporter.export_weekly_analysis()


if __name__ == "__main__":
    result = run_weekly_export()
    print(json.dumps(result, indent=2))
