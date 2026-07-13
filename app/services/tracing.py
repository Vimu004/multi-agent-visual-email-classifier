"""Simple local tracing utilities."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime

from sqlmodel import Session

from ..models import TraceEventRecord


@dataclass
class TraceLogger:
    """Persists trace events to SQLite and keeps an in-memory copy."""

    workflow_id: str
    session: Session
    accumulator: list[dict]

    @contextmanager
    def span(self, agent_name: str, event_type: str, input_summary: str) -> dict:
        started_at = datetime.utcnow()
        record: dict[str, str] = {}
        try:
            yield record
            status = record.get("status", "completed")
            output = record.get("output_summary", "")
        except Exception as exc:  # pragma: no cover - safety net
            status = "error"
            output = f"Exception: {exc}"
            record["status"] = status
            record["output_summary"] = output
            raise
        finally:
            completed_at = datetime.utcnow()
            duration = int((completed_at - started_at).total_seconds() * 1000)
            trace_dict = {
                "agent_name": agent_name,
                "status": status,
                "duration_ms": duration,
                "summary": output,
            }
            self.accumulator.append(trace_dict)
            self.session.add(
                TraceEventRecord(
                    workflow_id=self.workflow_id,
                    agent_name=agent_name,
                    event_type=event_type,
                    input_summary=input_summary[:255],
                    output_summary=output[:255],
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_ms=duration,
                    status=status,
                )
            )
            # Commit each span immediately so the dashboard can poll and render
            # the trace live while the workflow is still running.
            try:
                self.session.commit()
            except Exception:  # pragma: no cover - keep the workflow running
                self.session.rollback()
