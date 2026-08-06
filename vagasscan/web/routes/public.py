from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from vagasscan.models import Vaga
from vagasscan.providers import ErroProvedor
from vagasscan.web.common import (
    client_key,
    consulta_da_requisicao,
    contexto,
    provedor,
    templates,
    texto_limitado,
    validar_csrf,
)

router = APIRouter()


@router.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@router.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html", contexto(request))


@router.get("/buscar")
async def buscar(request: Request):
    if not request.app.state.settings.public_demo:
        raise HTTPException(status_code=403, detail="A demonstração pública está desativada.")
    if not request.query_params.get("termo"):
        return templates.TemplateResponse(
            request, "buscar.html", contexto(request, private=False)
        )
    limiter = request.app.state.rate_limiter
    if not limiter.allow("public-search", client_key(request), 5, 60):
        return templates.TemplateResponse(
            request,
            "erro.html",
            contexto(
                request,
                title="Muitas buscas",
                message="Aguarde um minuto antes de fazer uma nova busca.",
            ),
            status_code=429,
        )
    try:
        consulta = consulta_da_requisicao(request)
        provider_name = str(request.query_params.get("provedor") or "adzuna")
        provider = provedor(request, provider_name)
        service = request.app.state.public.vaga_service
        if (
            provider_name == "adzuna"
            and service.cache
            and service.cache.obter(provider.nome, consulta) is None
            and not limiter.allow("adzuna-global", "global", 10, 60)
        ):
            raise ErroProvedor(
                "O limite preventivo de consultas à Adzuna foi atingido. Tente em um minuto.",
                codigo="limite",
                transitorio=True,
                limite=True,
            )
        resultado = service.buscar_e_salvar(provider, consulta)
    except (ValueError, ErroProvedor) as exc:
        return templates.TemplateResponse(
            request,
            "buscar.html",
            contexto(request, private=False, error=str(exc)),
            status_code=400,
        )
    return templates.TemplateResponse(
        request,
        "resultados.html",
        contexto(
            request,
            resultado=resultado,
            consulta=consulta,
            provider_name=provider_name,
            private=False,
        ),
    )


@router.get("/vagas/{vaga_id}")
async def vaga_detalhe(request: Request, vaga_id: int):
    vaga = request.app.state.public.vagas.obter_publico(vaga_id)
    if not vaga:
        raise HTTPException(status_code=404)
    requisitos = request.app.state.public.vagas.listar_requisitos(vaga_id)
    modelo = Vaga(**{key: value for key, value in vaga.items() if key in Vaga.__dataclass_fields__})
    analise, _ = request.app.state.public.vaga_service.analisar_temporaria(modelo)
    return templates.TemplateResponse(
        request,
        "vaga_detalhe.html",
        contexto(
            request,
            vaga=vaga,
            requisitos=requisitos,
            analise=analise,
            private=False,
        ),
    )


@router.get("/analisar")
async def analisar_get(request: Request):
    if not request.app.state.settings.public_demo:
        raise HTTPException(status_code=403, detail="A demonstração pública está desativada.")
    return templates.TemplateResponse(
        request, "analisar.html", contexto(request, private=False, values={})
    )


@router.post("/analisar")
async def analisar_post(request: Request):
    if not request.app.state.settings.public_demo:
        raise HTTPException(status_code=403, detail="A demonstração pública está desativada.")
    form = await validar_csrf(request)
    limiter = request.app.state.rate_limiter
    if not limiter.allow("public-analysis", client_key(request), 10, 60):
        raise HTTPException(status_code=429, detail="Limite temporário de análises atingido.")
    values = {key: str(value) for key, value in form.items() if key != "csrf_token"}
    try:
        vaga = Vaga(
            titulo=texto_limitado(form.get("titulo"), "Título", 200)
            or "Vaga analisada",
            empresa=texto_limitado(form.get("empresa"), "Empresa", 200)
            or "Não informada",
            localizacao=texto_limitado(form.get("localizacao"), "Localização", 200)
            or "Não informada",
            descricao=texto_limitado(
                form.get("descricao"), "Descrição", 20_000, required=True
            ),
            fonte="analise_publica",
        )
        resultado, requisitos = request.app.state.public.vaga_service.analisar_temporaria(vaga)
    except ValueError as exc:
        return templates.TemplateResponse(
            request,
            "analisar.html",
            contexto(request, private=False, values=values, error=str(exc)),
            status_code=400,
        )
    return templates.TemplateResponse(
        request,
        "analisar.html",
        contexto(
            request,
            private=False,
            values=values,
            vaga=vaga,
            resultado=resultado,
            requisitos=requisitos,
        ),
    )
