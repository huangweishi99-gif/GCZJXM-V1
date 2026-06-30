# -*- coding: utf-8 -*-
"""后台任务队列：外网远程触发 deliver / calibrate。"""
from __future__ import annotations

import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from threading import Lock
from typing import Any, Callable, Dict, List, Optional

from src.sync.config import allowed_projects

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sync-job")
_lock = Lock()
_jobs: Dict[str, "JobRecord"] = {}
_MAX_JOBS = 100


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


@dataclass
class JobRecord:
    id: str
    kind: str
    project_id: Optional[str]
    status: JobStatus
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    params: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _trim_jobs() -> None:
    if len(_jobs) <= _MAX_JOBS:
        return
    ordered = sorted(_jobs.values(), key=lambda j: j.created_at)
    for old in ordered[: len(_jobs) - _MAX_JOBS]:
        _jobs.pop(old.id, None)


def _assert_project_allowed(project_id: str) -> None:
    allowed = allowed_projects()
    if allowed is not None and project_id not in allowed:
        raise ValueError(f"项目 {project_id} 未在 sync_server.json allowed_projects 中")


def submit_job(
    kind: str,
    fn: Callable[[], Any],
    *,
    project_id: Optional[str] = None,
    params: Optional[dict] = None,
) -> JobRecord:
    if project_id:
        _assert_project_allowed(project_id)

    job_id = uuid.uuid4().hex[:12]
    rec = JobRecord(
        id=job_id,
        kind=kind,
        project_id=project_id,
        status=JobStatus.queued,
        created_at=_now(),
        params=params or {},
    )
    with _lock:
        _jobs[job_id] = rec
        _trim_jobs()

    def _run() -> None:
        with _lock:
            rec.status = JobStatus.running
            rec.started_at = _now()
        try:
            result = fn()
            with _lock:
                rec.status = JobStatus.done
                rec.result = result
                rec.finished_at = _now()
        except Exception as exc:
            with _lock:
                rec.status = JobStatus.failed
                rec.error = str(exc)
                rec.result = {"traceback": traceback.format_exc()}
                rec.finished_at = _now()

    _executor.submit(_run)
    return rec


def get_job(job_id: str) -> Optional[JobRecord]:
    with _lock:
        return _jobs.get(job_id)


def list_jobs(limit: int = 20) -> List[dict]:
    with _lock:
        items = sorted(_jobs.values(), key=lambda j: j.created_at, reverse=True)
    return [j.to_dict() for j in items[:limit]]
