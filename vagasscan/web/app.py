from __future__ import annotations

import logging
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response

from vagasscan.bootstrap import AppContext, criar_contexto
from vagasscan.config import Settings, configure_logging, load_settings
from vagasscan.web.common import WEB_ROOT, RateLimiter, contexto, templates
from vagasscan.web.routes import auth, dashboard, public


def create_app(
    settings: Settings | None = None,
    *,
    private_context: AppContext | None = None,
    public_context: AppContext | None = None,
    adzuna_session: object | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    if settings.environment == "production" and not settings.session_secret:
        raise RuntimeError("VAGASSCAN_SESSION_SECRET é obrigatório em produção.")
    runtime_secret = settings.session_secret or secrets.token_urlsafe(48)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_path)
        application.state.private = private_context or criar_contexto(settings)
        application.state.public = public_context or criar_contexto(settings, publico=True)
        try:
            yield
        finally:
            logging.shutdown()

    application = FastAPI(
        title="VagaScan",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
        debug=False,
    )
    application.state.settings = settings
    application.state.adzuna_session = adzuna_session
    application.state.rate_limiter = RateLimiter()
    application.state.client_key_secret = runtime_secret.encode("utf-8")
    application.state.flash_messages = {}
    application.state.admin_enabled = bool(
        settings.session_secret and settings.admin_password_hash
    )
    application.add_middleware(
        SessionMiddleware,
        secret_key=runtime_secret,
        session_cookie="vagasscan_session",
        max_age=8 * 60 * 60,
        same_site="lax",
        https_only=settings.cookie_secure or settings.environment == "production",
    )
    application.mount("/static", StaticFiles(directory=WEB_ROOT / "static"), name="static")
    application.include_router(public.router)
    application.include_router(auth.router)
    application.include_router(dashboard.router)

    @application.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'self'; form-action 'self'; "
            "frame-ancestors 'none'; object-src 'none'; img-src 'self' data:; "
            "style-src 'self'; script-src 'self'; connect-src 'self'"
        )
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    @application.exception_handler(404)
    async def not_found(request: Request, _: Exception):
        return templates.TemplateResponse(
            request,
            "erro.html",
            contexto(
                request,
                title="Página não encontrada",
                message="A página solicitada não existe.",
            ),
            status_code=404,
        )

    @application.exception_handler(403)
    async def forbidden(request: Request, exc: Exception):
        message = getattr(exc, "detail", "Acesso não permitido.")
        return templates.TemplateResponse(
            request,
            "erro.html",
            contexto(request, title="Acesso não permitido", message=message),
            status_code=403,
        )

    @application.exception_handler(429)
    async def too_many(request: Request, exc: Exception):
        message = getattr(exc, "detail", "Limite temporário atingido.")
        return templates.TemplateResponse(
            request,
            "erro.html",
            contexto(request, title="Muitas solicitações", message=message),
            status_code=429,
        )

    @application.exception_handler(ValueError)
    async def invalid_value(request: Request, exc: ValueError):
        return templates.TemplateResponse(
            request,
            "erro.html",
            contexto(request, title="Dados inválidos", message=str(exc)),
            status_code=400,
        )

    return application


app = create_app()
