from __future__ import annotations

import secrets

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from vagasscan.security import verificar_senha
from vagasscan.web.common import (
    client_key,
    contexto,
    exigir_admin,
    templates,
    texto_limitado,
    validar_csrf,
)

router = APIRouter()


@router.get("/login")
async def login_get(request: Request):
    if request.session.get("admin"):
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        contexto(request, admin_enabled=request.app.state.admin_enabled),
    )


@router.post("/login")
async def login_post(request: Request):
    form = await validar_csrf(request)
    limiter = request.app.state.rate_limiter
    key = client_key(request)
    window = 15 * 60
    if limiter.blocked("login", key, 5, window):
        error = "Muitas tentativas. Aguarde alguns minutos."
    elif not request.app.state.admin_enabled:
        error = "O acesso administrativo ainda não está configurado."
    else:
        try:
            username = texto_limitado(form.get("username"), "Usuário", 100, required=True)
            password = texto_limitado(form.get("password"), "Senha", 500, required=True)
        except ValueError as exc:
            error = str(exc)
            limiter.record("login", key, window)
        else:
            settings = request.app.state.settings
            valid_user = secrets.compare_digest(username, settings.admin_username)
            valid_password = verificar_senha(password, settings.admin_password_hash)
            if valid_user and valid_password:
                request.session.clear()
                request.session["admin"] = settings.admin_username
                request.session["csrf_token"] = secrets.token_urlsafe(32)
                return RedirectResponse("/dashboard", status_code=303)
            error = "Usuário ou senha inválidos."
            limiter.record("login", key, window)
    return templates.TemplateResponse(
        request,
        "login.html",
        contexto(request, error=error, admin_enabled=request.app.state.admin_enabled),
        status_code=401,
    )


@router.post("/logout")
async def logout(request: Request):
    exigir_admin(request)
    await validar_csrf(request)
    request.session.clear()
    return RedirectResponse("/", status_code=303)
