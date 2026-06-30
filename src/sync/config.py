# -*- coding: utf-8 -*-
"""同步服务配置（外网远程须 Token + 建议 Tailscale）。"""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "sync_server.json"


def _default_config() -> dict:
    return {
        "api_token": "",
        "remote_jobs_enabled": True,
        "allowed_projects": [],
        "_comment": "api_token 留空则仅局域网只读；外网请设 Token 并配合 Tailscale。也可设环境变量 SYNC_API_TOKEN。",
    }


def load_sync_config() -> dict:
    if not CONFIG_PATH.exists():
        return _default_config()
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _default_config()
    base = _default_config()
    base.update({k: v for k, v in data.items() if not k.startswith("_")})
    return base


def save_sync_config(data: dict) -> Path:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    merged = _default_config()
    merged.update({k: v for k, v in data.items() if not k.startswith("_")})
    CONFIG_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return CONFIG_PATH


def get_api_token() -> str:
    env = os.environ.get("SYNC_API_TOKEN", "").strip()
    if env:
        return env
    return (load_sync_config().get("api_token") or "").strip()


def remote_jobs_enabled() -> bool:
    cfg = load_sync_config()
    return bool(cfg.get("remote_jobs_enabled", True))


def allowed_projects() -> Optional[List[str]]:
    cfg = load_sync_config()
    items = cfg.get("allowed_projects") or []
    return list(items) if items else None


def ensure_api_token(*, force_new: bool = False) -> str:
    token = get_api_token()
    if token and not force_new:
        return token
    token = secrets.token_urlsafe(24)
    cfg = load_sync_config()
    cfg["api_token"] = token
    save_sync_config(cfg)
    return token


def auth_required() -> bool:
    return bool(get_api_token())
