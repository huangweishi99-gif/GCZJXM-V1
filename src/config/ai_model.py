"""AI 模型配置加载：从 config/ai_model.json + .env 合并读取。

- 非敏感字段（base_url/model_name/enable_tool_calls/timeout）放 ai_model.json
- 敏感字段（api_key）走 .env（gitignore），变量名在 ai_model.json 的 `api_key_env` 指定
- .env 加载用最简实现（无外部依赖），不覆盖已存在的环境变量
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CFG_PATH = _ROOT / "config" / "ai_model.json"
_ENV_PATH = _ROOT / ".env"


def _load_env_file(env_path: Path) -> None:
    """最简 .env 加载：只设置尚未存在的环境变量，不覆盖 shell 已设置的。"""
    if not env_path.exists():
        return
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
    except Exception:
        # .env 解析失败不阻塞主流程
        pass


def load_ai_model_config(
    cfg_path: Optional[Path] = None,
    *,
    allow_env_override: bool = True,
) -> Dict[str, Any]:
    """读取 AI 模型配置。

    Args:
        cfg_path: 配置文件路径；默认 config/ai_model.json
        allow_env_override: 是否允许 env 变量覆盖（默认 True）

    Returns:
        dict: 含 provider/base_url/model_name/api_key/enable_tool_calls/timeout/max_tokens/temperature
              若未配置或关键字段缺失，返回空 dict。
    """
    _load_env_file(_ENV_PATH)
    path = cfg_path or _DEFAULT_CFG_PATH
    if not path.exists():
        return {}
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    if allow_env_override:
        # env 优先级：GROK_BASE_URL / GROK_MODEL / GROK_TIMEOUT / GROK_MAX_TOKENS 可覆盖配置
        if os.environ.get("GROK_BASE_URL"):
            cfg["base_url"] = os.environ["GROK_BASE_URL"]
        if os.environ.get("GROK_MODEL"):
            cfg["model_name"] = os.environ["GROK_MODEL"]
        if os.environ.get("GROK_TIMEOUT"):
            try:
                cfg["timeout_seconds"] = int(os.environ["GROK_TIMEOUT"])
            except ValueError:
                pass
        if os.environ.get("GROK_MAX_TOKENS"):
            try:
                cfg["max_tokens"] = int(os.environ["GROK_MAX_TOKENS"])
            except ValueError:
                pass

    # 读 API key
    env_name = cfg.get("api_key_env", "GROK_API_KEY")
    cfg["api_key"] = os.environ.get(env_name, "")

    # 简化别名
    cfg.setdefault("base_url", cfg.get("base_url", ""))
    cfg.setdefault("model_name", cfg.get("model_name", "grok-4.7"))
    cfg.setdefault("timeout_seconds", cfg.get("timeout_seconds", 60))
    cfg.setdefault("max_tokens", cfg.get("max_tokens", 4000))
    cfg.setdefault("temperature", cfg.get("temperature", 0.1))
    cfg.setdefault("enable_tool_calls", cfg.get("enable_tool_calls", True))

    return cfg


def is_ai_model_configured() -> bool:
    """是否已配置（base_url + api_key 都齐）。"""
    cfg = load_ai_model_config()
    return bool(cfg.get("base_url") and cfg.get("api_key"))
