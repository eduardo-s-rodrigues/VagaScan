from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from vagasscan.models import Vaga
from vagasscan.providers import ErroProvedor
from vagasscan.utils.text import normalizar_texto
from vagasscan.utils.validation import url_http_segura
from vagasscan.web.common import (
    ConsultaLimitadaError,
    RateRule,
    client_key,
    consulta_da_requisicao,
    contexto,
    provedor,
    templates,
    texto_limitado,
    validar_csrf,
)

router = APIRouter()

MODALIDADES_PUBLICAS = {"", "presencial", "hibrido", "remoto"}
ORDENS_PUBLICAS = {"compatibilidade", "recentes", "titulo", "empresa"}
CATEGORIAS_TECNICAS = {
    "linguagens",
    "bancos de dados",
    "ferramentas",
    "cloud",
    "frameworks",
    "análise de dados",
    "suporte e infraestrutura",
    "metodologias",
    "integrações e dados",
}


def _valor(vaga: Vaga | dict[str, Any], campo: str, padrao: Any = "") -> Any:
    return vaga.get(campo, padrao) if isinstance(vaga, dict) else getattr(vaga, campo, padrao)


def _payload_salvar(vaga: Vaga | dict[str, Any], vaga_id: int | None) -> dict[str, Any]:
    fonte = str(_valor(vaga, "fonte") or "publica")
    externo = str(_valor(vaga, "identificador_externo") or vaga_id or "")
    return {
        "version": 1,
        "id": f"{fonte}:{externo}",
        "title": str(_valor(vaga, "titulo") or "Vaga sem título")[:200],
        "company": str(_valor(vaga, "empresa") or "Não informada")[:200],
        "location": str(_valor(vaga, "localizacao") or "Não informada")[:200],
        "modality": str(_valor(vaga, "modalidade") or "não informada")[:100],
        "score": round(float(_valor(vaga, "compatibilidade", 0) or 0), 1),
        "originalUrl": url_http_segura(_valor(vaga, "link")),
        "detailUrl": f"/vagas/{vaga_id}" if vaga_id is not None else "",
    }


def _experiencia_resultados(
    resultado: dict[str, Any], modalidade: str, ordem: str, provider_name: str
) -> dict[str, Any]:
    if modalidade not in MODALIDADES_PUBLICAS:
        raise ValueError("Modalidade inválida.")
    if ordem not in ORDENS_PUBLICAS:
        raise ValueError("Ordenação inválida.")
    itens = list(resultado["itens"])
    if modalidade:
        esperado = "híbrido" if modalidade == "hibrido" else modalidade
        itens = [
            item
            for item in itens
            if normalizar_texto(str(item["vaga"].modalidade)) == normalizar_texto(esperado)
        ]
    if ordem == "compatibilidade":
        itens.sort(key=lambda item: float(item["analise"].pontuacao or 0), reverse=True)
    elif ordem == "recentes":
        itens.sort(key=lambda item: str(item["vaga"].data_publicacao or ""), reverse=True)
    elif ordem == "titulo":
        itens.sort(key=lambda item: normalizar_texto(item["vaga"].titulo))
    else:
        itens.sort(key=lambda item: normalizar_texto(item["vaga"].empresa))

    tecnologias: Counter[str] = Counter()
    for item in itens:
        score = float(item["analise"].pontuacao or 0)
        item["score_bucket"] = min(100, max(0, round(score / 5) * 5))
        item["salvar_payload"] = _payload_salvar(item["vaga"], item["vaga_id"])
        for requisito in item.get("requisitos", []):
            if requisito.categoria in CATEGORIAS_TECNICAS:
                tecnologias[requisito.requisito] += 1
    maiores = tecnologias.most_common(5)
    maximo = maiores[0][1] if maiores else 1
    resumo = {
        "total": len(itens),
        "alta_compatibilidade": sum(
            float(item["analise"].pontuacao or 0) >= 80 for item in itens
        ),
        "remotas": sum(
            normalizar_texto(item["vaga"].modalidade) == "remoto" for item in itens
        ),
        "hibridas": sum(
            normalizar_texto(item["vaga"].modalidade) == "hibrido" for item in itens
        ),
        "tecnologias": [
            {"nome": nome, "quantidade": quantidade, "percentual": quantidade / maximo * 100}
            for nome, quantidade in maiores
        ],
    }
    resultado = dict(resultado)
    resultado["itens"] = itens
    resultado["exibidas"] = len(itens)
    resultado["origem"] = (
        "Cache"
        if resultado["veio_cache"]
        else "Demonstração"
        if provider_name == "demonstracao"
        else "API"
    )
    resultado["resumo"] = resumo
    return resultado


def _autorizar_busca_publica(request: Request):
    settings = request.app.state.settings
    key = client_key(request)

    def autorizar() -> None:
        retry_after = request.app.state.rate_limiter.reserve(
            [
                RateRule(
                    "public-search-hour",
                    key,
                    settings.public_search_limit_per_hour,
                    60 * 60,
                    settings.public_search_cooldown_seconds,
                ),
                RateRule("adzuna-global", "global", 10, 60),
            ]
        )
        if retry_after:
            raise ConsultaLimitadaError(retry_after)

    return autorizar


def _contexto_busca(request: Request, **values: Any) -> dict[str, Any]:
    defaults = {
        "resultado": None,
        "error": None,
        "retry_after": 0,
        "modalidade": str(request.query_params.get("modalidade") or ""),
        "ordem": str(request.query_params.get("ordem") or "compatibilidade"),
        "provider_name": str(request.query_params.get("provedor") or "adzuna"),
    }
    defaults.update(values)
    return contexto(request, **defaults)


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
            request, "busca_publica.html", _contexto_busca(request)
        )
    try:
        consulta = consulta_da_requisicao(request)
        modalidade = str(request.query_params.get("modalidade") or "")
        ordem = str(request.query_params.get("ordem") or "compatibilidade")
        provider_name = str(request.query_params.get("provedor") or "adzuna")
        provider = provedor(request, provider_name)
        gate = _autorizar_busca_publica(request) if provider_name == "adzuna" else None
        resultado = request.app.state.public.vaga_service.buscar_e_salvar(
            provider,
            consulta,
            autorizar_consulta_externa=gate,
        )
        resultado = _experiencia_resultados(resultado, modalidade, ordem, provider_name)
    except ConsultaLimitadaError as exc:
        return templates.TemplateResponse(
            request,
            "busca_publica.html",
            _contexto_busca(request, error=str(exc), retry_after=exc.retry_after),
            status_code=429,
        )
    except (ValueError, ErroProvedor) as exc:
        return templates.TemplateResponse(
            request,
            "busca_publica.html",
            _contexto_busca(request, error=str(exc)),
            status_code=400,
        )
    return templates.TemplateResponse(
        request,
        "busca_publica.html",
        _contexto_busca(
            request,
            resultado=resultado,
            consulta=consulta,
            modalidade=modalidade,
            ordem=ordem,
            provider_name=provider_name,
        ),
    )


@router.get("/vagas-salvas")
async def vagas_salvas(request: Request):
    return templates.TemplateResponse(request, "vagas_salvas.html", contexto(request))


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
            salvar_payload=_payload_salvar(vaga, vaga_id),
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
            titulo=texto_limitado(form.get("titulo"), "Título", 200) or "Vaga analisada",
            empresa=texto_limitado(form.get("empresa"), "Empresa", 200) or "Não informada",
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
