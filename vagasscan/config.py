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
    public_database_path: Path = PROJECT_ROOT / "data" / "vagasscan_public.db"
    public_profile_path: Path = PROJECT_ROOT / "data" / "profile_public.json"
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    adzuna_country: str = "br"
    adzuna_results_per_page: int = 20
    adzuna_timeout: float = 10.0
    adzuna_cache_minutes: int = 30
    max_extra_pages_for_filter: int = 2
    saved_jobs_limit: int = 200
    public_search_cooldown_seconds: int = 15
    public_search_limit_per_hour: int = 30
    public_analysis_limit_per_minute: int = 10
    admin_search_limit_per_hour: int = 100
    adzuna_global_limit_per_minute: int = 10
    admin_username: str = "admin"
    admin_password_hash: str = ""
    session_secret: str = ""
    public_demo: bool = True
    enable_file_organizer_web: bool = False
    file_organizer_source: Path | None = None
    file_organizer_destination: Path | None = None
    host: str = "127.0.0.1"
    port: int = 8000
    environment: str = "development"
    base_url: str = "http://127.0.0.1:8000"
    cookie_secure: bool = False


def _bool_from_env(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "sim", "yes", "on"}


def _float_from_env(name: str, default: float, minimum: float = 1.0) -> float:
    import os

    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if math.isfinite(value) and value >= minimum else default


def _int_from_env(name: str, default: int, minimum: int, maximum: int) -> int:
    import os

    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return min(maximum, max(minimum, value))


def _optional_path(value: str | None) -> Path | None:
    return _path_from_env(value, value) if value and value.strip() else None


def load_settings(env_path: Path | None = None) -> Settings:
    """Carrega configurações sem exigir que o arquivo .env exista."""
    import os

    load_dotenv(env_path or PROJECT_ROOT / ".env")
    timeout = _float_from_env("JOB_API_TIMEOUT", 10.0)
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
        api_requires_token=_bool_from_env(os.getenv("JOB_API_REQUIRES_TOKEN")),
        api_timeout=timeout,
        public_database_path=_path_from_env(
            os.getenv("VAGASSCAN_PUBLIC_DATABASE"), "data/vagasscan_public.db"
        ),
        public_profile_path=_path_from_env(
            os.getenv("VAGASSCAN_PUBLIC_PROFILE"), "data/profile_public.json"
        ),
        adzuna_app_id=os.getenv("ADZUNA_APP_ID", "").strip(),
        adzuna_app_key=os.getenv("ADZUNA_APP_KEY", "").strip(),
        adzuna_country=os.getenv("ADZUNA_COUNTRY", "br").strip().lower() or "br",
        adzuna_results_per_page=_int_from_env(
            "ADZUNA_RESULTS_PER_PAGE", 20, 1, 50
        ),
        adzuna_timeout=_float_from_env("ADZUNA_TIMEOUT", 10.0),
        adzuna_cache_minutes=_int_from_env("ADZUNA_CACHE_MINUTES", 30, 1, 1440),
        max_extra_pages_for_filter=_int_from_env(
            "VAGASSCAN_MAX_EXTRA_PAGES_FOR_FILTER", 2, 0, 2
        ),
        saved_jobs_limit=_int_from_env("VAGASSCAN_SAVED_JOBS_LIMIT", 200, 1, 500),
        public_search_cooldown_seconds=_int_from_env(
            "VAGASSCAN_PUBLIC_SEARCH_COOLDOWN_SECONDS", 15, 1, 300
        ),
        public_search_limit_per_hour=_int_from_env(
            "VAGASSCAN_PUBLIC_SEARCH_LIMIT_PER_HOUR", 30, 1, 1000
        ),
        public_analysis_limit_per_minute=_int_from_env(
            "VAGASSCAN_PUBLIC_ANALYSIS_LIMIT_PER_MINUTE", 10, 1, 100
        ),
        admin_search_limit_per_hour=_int_from_env(
            "VAGASSCAN_ADMIN_SEARCH_LIMIT_PER_HOUR", 100, 1, 5000
        ),
        adzuna_global_limit_per_minute=_int_from_env(
            "VAGASSCAN_ADZUNA_GLOBAL_LIMIT_PER_MINUTE", 10, 1, 60
        ),
        admin_username=os.getenv("VAGASSCAN_ADMIN_USERNAME", "admin").strip() or "admin",
        admin_password_hash=os.getenv("VAGASSCAN_ADMIN_PASSWORD_HASH", "").strip(),
        session_secret=os.getenv("VAGASSCAN_SESSION_SECRET", "").strip(),
        public_demo=_bool_from_env(os.getenv("VAGASSCAN_PUBLIC_DEMO"), True),
        enable_file_organizer_web=_bool_from_env(
            os.getenv("VAGASSCAN_ENABLE_FILE_ORGANIZER_WEB")
        ),
        file_organizer_source=_optional_path(os.getenv("VAGASSCAN_FILE_ORGANIZER_SOURCE")),
        file_organizer_destination=_optional_path(
            os.getenv("VAGASSCAN_FILE_ORGANIZER_DESTINATION")
        ),
        host=os.getenv("VAGASSCAN_HOST", "127.0.0.1").strip() or "127.0.0.1",
        port=_int_from_env("VAGASSCAN_PORT", 8000, 1, 65535),
        environment=os.getenv("VAGASSCAN_ENV", "development").strip().lower()
        or "development",
        base_url=os.getenv(
            "VAGASSCAN_BASE_URL", "http://127.0.0.1:8000"
        ).strip()
        or "http://127.0.0.1:8000",
        cookie_secure=_bool_from_env(os.getenv("VAGASSCAN_COOKIE_SECURE")),
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
