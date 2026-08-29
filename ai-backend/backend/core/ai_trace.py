from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
from threading import RLock
from typing import Any
import uuid


TRACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,120}$")
SENSITIVE_METADATA_KEYS = {
    "answer",
    "content",
    "file_path",
    "filename",
    "input_path",
    "original_filename",
    "patient_id",
    "patient_id_card",
    "patient_name",
    "phone",
    "prompt",
    "question",
}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def normalize_trace_id(value: str | None) -> str:
    candidate = str(value or "").strip()
    if TRACE_ID_PATTERN.fullmatch(candidate):
        return candidate
    return f"tr_{datetime.now().strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:12]}"


def _safe_value(value: Any, depth: int = 0) -> Any:
    if depth >= 3:
        return "[truncated]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:240]
    if isinstance(value, (list, tuple)):
        return [_safe_value(item, depth + 1) for item in value[:20]]
    if isinstance(value, dict):
        return {
            str(key): "[redacted]" if str(key).lower() in SENSITIVE_METADATA_KEYS else _safe_value(item, depth + 1)
            for key, item in list(value.items())[:30]
        }
    return str(value)[:240]


class AiTraceStore:
    """Local, privacy-aware trace storage for AI execution metadata."""

    def __init__(self, data_root: Path):
        self.root = data_root / "ai-traces"
        self._lock = RLock()

    def _path_for(self, trace_id: str) -> Path:
        return self.root / f"{normalize_trace_id(trace_id)}.json"

    def _read(self, trace_id: str) -> dict[str, Any] | None:
        path = self._path_for(trace_id)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _write(self, trace_id: str, payload: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path_for(trace_id)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)

    def start(
        self,
        trace_id: str | None,
        operation: str,
        *,
        actor_user_id: int | None = None,
        actor_role: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        normalized_id = normalize_trace_id(trace_id)
        with self._lock:
            existing = self._read(normalized_id)
            if existing is not None:
                return normalized_id
            timestamp = now_iso()
            payload = {
                "schema_version": "ai_trace_v1",
                "trace_id": normalized_id,
                "operation": str(operation or "unknown")[:80],
                "status": "running",
                "actor_user_id": actor_user_id,
                "actor_role": str(actor_role or "")[:32],
                "started_at": timestamp,
                "updated_at": timestamp,
                "metadata": _safe_value(metadata or {}),
                "events": [
                    {
                        "at": timestamp,
                        "stage": "request_received",
                        "status": "completed",
                        "details": {"storage": "local"},
                    }
                ],
            }
            self._write(normalized_id, payload)
        return normalized_id

    def event(
        self,
        trace_id: str | None,
        stage: str,
        status: str,
        *,
        duration_ms: float | int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        normalized_id = normalize_trace_id(trace_id)
        with self._lock:
            payload = self._read(normalized_id)
            if payload is None:
                return
            timestamp = now_iso()
            event: dict[str, Any] = {
                "at": timestamp,
                "stage": str(stage or "unknown")[:80],
                "status": str(status or "unknown")[:32],
                "details": _safe_value(details or {}),
            }
            if isinstance(duration_ms, (int, float)):
                event["duration_ms"] = round(max(0.0, float(duration_ms)), 3)
            events = payload.get("events", [])
            if not isinstance(events, list):
                events = []
            payload["events"] = (events + [event])[-120:]
            payload["updated_at"] = timestamp
            self._write(normalized_id, payload)

    def finish(
        self,
        trace_id: str | None,
        status: str,
        *,
        duration_ms: float | int | None = None,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        normalized_id = normalize_trace_id(trace_id)
        with self._lock:
            payload = self._read(normalized_id)
            if payload is None:
                return
            timestamp = now_iso()
            final_status = status if status in {"completed", "failed", "cancelled"} else "failed"
            payload["status"] = final_status
            payload["completed_at"] = timestamp
            payload["updated_at"] = timestamp
            if isinstance(duration_ms, (int, float)):
                payload["duration_ms"] = round(max(0.0, float(duration_ms)), 3)
            if result:
                payload["result"] = _safe_value(result)
            if error:
                payload["error"] = _safe_value(error)
            events = payload.get("events", [])
            if not isinstance(events, list):
                events = []
            payload["events"] = (events + [{
                "at": timestamp,
                "stage": "request_finished",
                "status": final_status,
                "details": _safe_value(result or error or {}),
            }])[-120:]
            self._write(normalized_id, payload)

    @staticmethod
    def _permitted(payload: dict[str, Any], actor_user_id: int | None, is_admin: bool) -> bool:
        if is_admin or actor_user_id is None:
            return True
        return payload.get("actor_user_id") == actor_user_id

    def list(
        self,
        *,
        limit: int = 80,
        operation: str | None = None,
        status: str | None = None,
        actor_user_id: int | None = None,
        is_admin: bool = False,
    ) -> list[dict[str, Any]]:
        with self._lock:
            paths = sorted(self.root.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True) if self.root.is_dir() else []
            rows: list[dict[str, Any]] = []
            for path in paths:
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if not isinstance(payload, dict) or not self._permitted(payload, actor_user_id, is_admin):
                    continue
                if operation and payload.get("operation") != operation:
                    continue
                if status and payload.get("status") != status:
                    continue
                rows.append({
                    "trace_id": payload.get("trace_id"),
                    "operation": payload.get("operation"),
                    "status": payload.get("status"),
                    "started_at": payload.get("started_at"),
                    "completed_at": payload.get("completed_at"),
                    "updated_at": payload.get("updated_at"),
                    "duration_ms": payload.get("duration_ms"),
                    "metadata": payload.get("metadata", {}),
                    "result": payload.get("result", {}),
                    "error": payload.get("error", {}),
                })
                if len(rows) >= max(1, min(int(limit), 200)):
                    break
        return rows

    def get(
        self,
        trace_id: str,
        *,
        actor_user_id: int | None = None,
        is_admin: bool = False,
    ) -> dict[str, Any] | None:
        with self._lock:
            payload = self._read(trace_id)
            if payload is None or not self._permitted(payload, actor_user_id, is_admin):
                return None
            return payload

    def summary(
        self,
        *,
        actor_user_id: int | None = None,
        is_admin: bool = False,
    ) -> dict[str, Any]:
        rows = self.list(limit=200, actor_user_id=actor_user_id, is_admin=is_admin)
        completed = [item for item in rows if item.get("status") in {"completed", "failed", "cancelled"}]
        succeeded = sum(item.get("status") == "completed" for item in completed)
        durations = [item.get("duration_ms") for item in completed if isinstance(item.get("duration_ms"), (int, float))]
        return {
            "total": len(rows),
            "completed": len(completed),
            "succeeded": succeeded,
            "failed": sum(item.get("status") == "failed" for item in completed),
            "success_rate": round(succeeded / len(completed), 4) if completed else None,
            "average_duration_ms": round(sum(durations) / len(durations), 3) if durations else None,
        }
