# -*- coding: utf-8 -*-
"""FastAPI：桌面组价项目 ↔ 手机端同步 API。"""
from __future__ import annotations

import socket
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from src.db.database import init_database
from src.knowledge.calibration import load_project_pairs
from src.knowledge.query import PricingContext
from src.knowledge.repository import KnowledgeRepository
from src.pricing.component_judge import judge_line_components
from src.pricing.engine import PricingEngine
from src.pricing.reconcile import component_total
from src.sync.bundle import build_sync_bundle, write_sync_bundle
from src.sync.corrections import (
    export_corrections_json,
    get_revision,
    list_corrections,
    save_correction,
)

ROOT = Path(__file__).resolve().parents[2]
MOBILE_DIR = ROOT / "mobile"


class CorrectionIn(BaseModel):
    project_id: str
    dedupe_key: str
    name: str
    feature: str = ""
    unit: str
    quantity: Optional[float] = None
    material_main: Optional[float] = None
    material_loss_rate: float = 0
    material_aux: Optional[float] = None
    labor: Optional[float] = None
    machinery: Optional[float] = None
    cost_unit_price: Optional[float] = None
    note: str = ""
    device_id: str = ""


class JudgeIn(BaseModel):
    name: str
    feature: str = ""
    unit: str
    city: str = ""
    tier: str = "mid"


class JobDeliverIn(BaseModel):
    project_id: str
    match_mode: Optional[str] = None


class JobCalibrateIn(BaseModel):
    project_id: str
    rel_tol: float = 0.10
    learn: bool = False


def _require_job_token(
    authorization: Optional[str] = None,
    x_api_token: Optional[str] = None,
) -> None:
    from fastapi import HTTPException

    from src.sync.config import get_api_token, remote_jobs_enabled

    if not remote_jobs_enabled():
        raise HTTPException(status_code=403, detail="远程任务已在 sync_server.json 中关闭")
    token = get_api_token()
    if not token:
        raise HTTPException(
            status_code=401,
            detail="未配置 Token，请在电脑上运行: python app.py sync token",
        )
    provided = (x_api_token or "").strip()
    if not provided and authorization:
        provided = authorization.replace("Bearer ", "").strip()
    if provided != token:
        raise HTTPException(status_code=401, detail="无效 API Token")


def create_app():
    from fastapi import Depends, FastAPI, Header, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    init_database()
    app = FastAPI(title="工程造价组价同步", version="1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    async def mobile_home():
        index = MOBILE_DIR / "index.html"
        if index.exists():
            return FileResponse(index)
        return {"message": "手机端 UI 未找到，请检查 mobile/index.html"}

    if MOBILE_DIR.exists():
        app.mount("/mobile", StaticFiles(directory=str(MOBILE_DIR), html=True), name="mobile")

    def api_token_dep(
        authorization: Optional[str] = Header(None),
        x_api_token: Optional[str] = Header(None, alias="X-API-Token"),
    ):
        from src.sync.config import auth_required, get_api_token

        if not auth_required():
            return
        token = get_api_token()
        provided = (x_api_token or "").strip()
        if not provided and authorization:
            provided = authorization.replace("Bearer ", "").strip()
        if provided != token:
            raise HTTPException(status_code=401, detail="无效 API Token")

    def job_token_dep(
        authorization: Optional[str] = Header(None),
        x_api_token: Optional[str] = Header(None, alias="X-API-Token"),
    ):
        _require_job_token(authorization=authorization, x_api_token=x_api_token)

    @app.get("/api/health")
    async def health():
        from src.sync.config import auth_required, remote_jobs_enabled

        return {
            "ok": True,
            "revision": get_revision(),
            "principle": "组价须对照名称+项目特征+单位",
            "auth_required": auth_required(),
            "remote_jobs_enabled": remote_jobs_enabled(),
        }

    @app.get("/api/projects")
    async def projects():
        pairs = load_project_pairs()
        return [
            {
                "id": p.get("id"),
                "label": p.get("label", p.get("id")),
                "city": p.get("city", ""),
                "tier": p.get("tier", "mid"),
            }
            for p in pairs
        ]

    @app.get("/api/sync/status")
    async def sync_status():
        pending = list_corrections(status="pending")
        return {
            "revision": get_revision(),
            "pending_corrections": len(pending),
        }

    @app.post("/api/sync/bundle")
    async def rebuild_bundle(
        project_id: Optional[str] = None,
        _: None = Depends(api_token_dep),
    ):
        path = write_sync_bundle(project_id=project_id)
        return {"path": str(path), "revision": get_revision()}

    @app.get("/api/sync/bundle")
    async def get_bundle(project_id: Optional[str] = None, refresh: bool = False):
        bundle_path = ROOT / "data" / "sync" / "latest_bundle.json"
        if refresh or not bundle_path.exists():
            write_sync_bundle(project_id=project_id)
        if bundle_path.exists():
            import json

            return json.loads(bundle_path.read_text(encoding="utf-8"))
        return build_sync_bundle(project_id=project_id)

    @app.get("/api/projects/{project_id}/lines")
    async def project_lines(project_id: str, filter: str = "all", limit: int = 200):
        bundle = build_sync_bundle(project_id=project_id)
        proj = next((p for p in bundle["projects"] if p["id"] == project_id), None)
        if not proj:
            raise HTTPException(404, f"未知项目: {project_id}")
        lines = proj["lines"]
        if filter == "worst":
            lines = [ln for ln in lines if ln.get("pct_diff") is not None and abs(ln["pct_diff"]) > 10]
        elif filter == "pending":
            pending_keys = {c["dedupe_key"] for c in list_corrections(project_id=project_id)}
            lines = [ln for ln in lines if ln["dedupe_key"] in pending_keys]
        return {"project": proj, "lines": lines[:limit]}

    @app.post("/api/corrections")
    async def post_correction(body: CorrectionIn, _: None = Depends(api_token_dep)):
        if not body.unit.strip():
            raise HTTPException(400, "单位不能为空（组价须名称+特征+单位）")
        cid = save_correction(body.model_dump())
        total = body.cost_unit_price
        if total is None:
            total = component_total(
                {
                    "material_main": body.material_main or 0,
                    "material_loss_rate": body.material_loss_rate or 0,
                    "material_aux": body.material_aux or 0,
                    "labor": body.labor or 0,
                    "machinery": body.machinery or 0,
                }
            )
        return {"id": cid, "revision": get_revision(), "cost_unit": total}

    @app.get("/api/corrections")
    async def get_corrections(project_id: Optional[str] = None, status: str = "pending"):
        return list_corrections(project_id=project_id, status=status)

    @app.post("/api/corrections/export")
    async def export_corrections(
        project_id: Optional[str] = None,
        _: None = Depends(api_token_dep),
    ):
        path = export_corrections_json(project_id=project_id)
        return {"path": str(path), "revision": get_revision()}

    @app.post("/api/judge")
    async def judge_line(body: JudgeIn):
        repo = KnowledgeRepository()
        engine = PricingEngine()
        tier = body.tier or "mid"
        if tier in ("高", "中", "低"):
            tier = {"高": "high", "中": "mid", "低": "low"}[tier]
        ctx = PricingContext(city=body.city or "", price_tier=tier) if body.city or body.tier else None
        j = judge_line_components(
            body.name,
            body.feature or "",
            body.unit,
            engine,
            repo,
            ctx=ctx,
        )
        return {
            "craft": j.craft_label,
            "trade": j.trade,
            "confidence": round(j.confidence, 3),
            "auto_fill_ok": j.auto_fill_ok,
            "source": j.source,
            "material_main": j.material_main,
            "material_aux": j.material_aux,
            "labor": j.labor,
            "machinery": j.machinery,
            "notes": j.notes,
            "warnings": j.warnings,
        }

    @app.get("/api/jobs")
    async def jobs_list(limit: int = 20, _: None = Depends(job_token_dep)):
        from src.sync.jobs import list_jobs

        return list_jobs(limit=limit)

    @app.get("/api/jobs/{job_id}")
    async def job_detail(job_id: str, _: None = Depends(job_token_dep)):
        from src.sync.jobs import get_job

        job = get_job(job_id)
        if not job:
            raise HTTPException(404, f"任务不存在: {job_id}")
        return job.to_dict()

    @app.post("/api/jobs/deliver")
    async def job_deliver(body: JobDeliverIn, _: None = Depends(job_token_dep)):
        from src.sync.jobs import submit_job
        from src.sync.runner import run_deliver_project

        rec = submit_job(
            "deliver",
            lambda: run_deliver_project(body.project_id, match_mode=body.match_mode),
            project_id=body.project_id,
            params=body.model_dump(),
        )
        return rec.to_dict()

    @app.post("/api/jobs/calibrate")
    async def job_calibrate(body: JobCalibrateIn, _: None = Depends(job_token_dep)):
        from src.sync.jobs import submit_job
        from src.sync.runner import run_calibrate_project

        rec = submit_job(
            "calibrate",
            lambda: run_calibrate_project(
                body.project_id,
                rel_tol=body.rel_tol,
                learn=body.learn,
            ),
            project_id=body.project_id,
            params=body.model_dump(),
        )
        return rec.to_dict()

    @app.post("/api/jobs/bundle")
    async def job_bundle(project_id: Optional[str] = None, _: None = Depends(job_token_dep)):
        from src.sync.jobs import submit_job

        rec = submit_job(
            "bundle",
            lambda: {"path": str(write_sync_bundle(project_id=project_id)), "revision": get_revision()},
            project_id=project_id,
        )
        return rec.to_dict()

    @app.post("/api/jobs/pull")
    async def job_pull(project_id: Optional[str] = None, _: None = Depends(job_token_dep)):
        from src.sync.jobs import submit_job
        from src.sync.runner import run_sync_pull

        rec = submit_job("pull", lambda: run_sync_pull(project_id=project_id), project_id=project_id)
        return rec.to_dict()

    return app


def local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def run_server(*, host: str = "0.0.0.0", port: int = 8765, reload: bool = False) -> None:
    import uvicorn

    from src.sync.config import auth_required, get_api_token

    init_database()
    write_sync_bundle()
    ip = local_ip()
    token = get_api_token()
    print(f"同步服务: http://{ip}:{port}/  （局域网）")
    print(f"API: http://{ip}:{port}/api/health")
    if auth_required():
        print(f"远程 Token 已配置（请求头 X-API-Token 或 Authorization: Bearer）")
    else:
        print("警告: 未配置 Token，远程任务接口未保护。请运行: python app.py sync token")
    print("")
    print("外网远程指挥 deliver（推荐 Tailscale）:")
    print("  1. 电脑、手机均安装 Tailscale 并登录同一账号")
    print("  2. python app.py sync token   # 生成 Token，勿泄露")
    print("  3. python app.py sync serve   # 保持运行，电脑勿休眠")
    print("  4. 手机 Tailscale 里看电脑 IP，浏览器打开 http://100.x.x.x:8765/")
    print("  5. 设置页填 Token → 「远程」页点「跑 deliver」")
    uvicorn.run(
        "src.sync.api:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
    )
