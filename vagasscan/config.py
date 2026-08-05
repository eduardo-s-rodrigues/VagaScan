from __future__ import annotations

import logging
import math
import sys
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _path_from_env(value: str | None, default: str) -> Path:
    path = Path(value or default)
    return path if path.is_absolute() else PROJECT_ROOT / path


@dataclass(frozen=True, slots=True)
class Settings:
    database_path: Path
    demo_database_path: Path
    profile_path: Path
    keywords_path: Path
    log_path: Path
    api_url: str = ""
    api_token: str = ""
    api_token_header: str = "Authorization"
    api_requires_token: bool = False
    api_timeout: float = 10.0


def load_settings(env_path: Path | None = None) -> Settings:
    """Carrega configurações sem exigir que o arquivo .env exista."""
    import os

    load_dotenv(env_path or PROJECT_ROOT / ".env")
    try:
        timeout = float(os.getenv("JOB_API_TIMEOUT", "10"))
    except ValueError:
        timeout = 10.0
    if not math.isfinite(timeout) or timeout < 1:
        timeout = 10.0
    token_header = os.getenv("JOB_API_TOKEN_HEADER", "Authorization").strip()
    return Settings(
        database_path=_path_from_env(os.getenv("VAGASSCAN_DATABASE"), "data/vagasscan.db"),
        demo_database_path=_path_from_env(
            os.getenv("VAGASSCAN_DEMO_DATABASE"), "data/vagasscan_demo.db"
        ),
        profile_path=_path_from_env(os.getenv("VAGASSCAN_PROFILE"), "data/profile.json"),
        keywords_path=_path_from_env(os.getenv("VAGASSCAN_KEYWORDS"), "data/keywords.json"),
        log_path=_path_from_env(os.getenv("VAGASSCAN_LOG"), "logs/vagasscan.log"),
        api_url=os.getenv("JOB_API_URL", "").strip(),
        api_token=os.getenv("JOB_API_TOKEN", "").strip(),
        api_token_header=token_header or "Authorization",
        api_requires_token=os.getenv("JOB_API_REQUIRES_TOKEN", "false").lower()
        in {"1", "true", "sim", "yes"},
        api_timeout=timeout,
    )


def configure_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8")],
        force=True,
    )


def configure_terminal_utf8() -> None:
    """Padroniza entrada para UTF-8 sem interferir na saída nativa do console Windows."""
    with suppress(AttributeError, ValueError):
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
