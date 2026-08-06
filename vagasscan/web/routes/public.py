from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from vagasscan.analyzers.modality import modalidade_corresponde
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
    tempo_decorrido,
    texto_limitado,
    validar_csrf,
)

router = APIRouter()
LOGGER = logging.getLogger(__name__)

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
        "version": 2,
        "id": f"{fonte}:{externo}",
        "title": str(_valor(vaga, "titulo") or "Vaga sem título")[:200],
        "company": str(_valor(vaga, "empresa") or "Não informada")[:200],
        "location": str(_valor(vaga, "localizacao") or "Não informada")[:200],
        "modality": str(_valor(vaga, "modalidade") or "não informada")[:100],
        "modalityOrigin": str(_valor(vaga, "modalidade_origem") or "não informada")[:30],
        "score": round(float(_valor(vaga, "compatibilidade", 0) or 0), 1),
        "confidence": str(_valor(vaga, "confianca_analise") or "baixa")[:10],
        "source": fonte[:40],
        "publishedAt": str(_valor(vaga, "data_publicacao") or "")[:40],
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
            if modalidade_corresponde(str(item["vaga"].modalidade), esperado)
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
        item["vaga"].confianca_analise = item["analise"].confianca
        item["vaga"].requisitos_identificados = item["analise"].requisitos_identificados
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
        "confianca_media": (
            {1: "baixa", 2: "média", 3: "alta"}.get(
                round(
                    sum(
                        {"baixa": 1, "média": 2, "alta": 3}.get(
                            item["analise"].confianca, 1
                        )
                        for item in itens
                    )
                    / len(itens)
                ),
                "baixa",
            )
            if itens
            else "baixa"
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
        "API + cache"
        if resultado.get("usou_api") and resultado.get("usou_cache")
        else "Cache"
        if resultado.get("usou_cache")
        else "Demonstração"
        if provider_name == "demonstracao"
        else "API"
    )
    resultado["cache_atualizado"] = tempo_decorrido(resultado.get("cache_criado_em"))
    erros_publicos: list[str] = []
    for erro in resultado.get("erros", []):
        if "cache anterior" in erro:
            mensagem = "A fonte está indisponível; resultados anteriores foram preservados."
        elif erro.startswith("Resultado ") and "formato inválido" in erro:
            mensagem = "Um resultado da fonte foi ignorado por estar incompleto."
        elif erro.startswith("Páginas adicionais"):
            mensagem = (
                "A busca foi concluída parcialmente; os resultados disponíveis foram mantidos."
            )
        else:
            mensagem = "Um resultado não pôde ser analisado e foi ignorado."
        if mensagem not in erros_publicos:
            erros_publicos.append(mensagem)
    resultado["erros_publicos"] = erros_publicos
    resultado["resumo"] = resumo
    return resultado


def _autorizar_busca_publica(request: Request):
    settings = request.app.state.settings
    key = client_key(request)

    primeira_tentativa = True

    def autorizar() -> None:
        nonlocal primeira_tentativa
        regras = [
            RateRule(
                "adzuna-global",
                "global",
                settings.adzuna_global_limit_per_minute,
                60,
            )
        ]
        if primeira_tentativa:
            regras.insert(
                0,
                RateRule(
                    "public-search-hour",
                    key,
                    settings.public_search_limit_per_hour,
                    60 * 60,
                    settings.public_search_cooldown_seconds,
                ),
            )
        retry_after = request.app.state.rate_limiter.reserve(
            regras
        )
        if retry_after:
            raise ConsultaLimitadaError(retry_after)
        primeira_tentativa = False

    return autorizar


def _mensagem_publica(exc: ErroProvedor) -> str:
    if exc.codigo in {"configuracao", "autenticacao"}:
        return "A fonte de vagas ainda não está disponível."
    if exc.codigo == "timeout":
        return "A consulta demorou mais do que o esperado. Tente novamente."
    if exc.codigo == "limite":
        return "A fonte de vagas atingiu um limite temporário. Tente novamente mais tarde."
    if exc.codigo == "validacao":
        return "Os filtros enviados não puderam ser usados. Revise a busca e tente novamente."
    return "A busca de vagas está temporariamente indisponível. Tente novamente em alguns minutos."


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
    except ErroProvedor as exc:
        LOGGER.warning("Falha previsível na busca pública: codigo=%s", exc.codigo)
        return templates.TemplateResponse(
            request,
            "busca_publica.html",
            _contexto_busca(request, error=_mensagem_publica(exc)),
            status_code=(
                503
                if exc.transitorio or exc.codigo in {"configuracao", "autenticacao"}
                else 400
            ),
        )
    except ValueError as exc:
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


PAGINAS_INSTITUCIONAIS: dict[str, dict[str, Any]] = {
    "sobre": {
        "titulo": "Sobre o VagaScan",
        "descricao": "Objetivo, tecnologias e natureza educacional do projeto VagaScan.",
        "intro": (
            "Um projeto pessoal e educacional para tornar a leitura de vagas de "
            "tecnologia mais clara."
        ),
        "secoes": [
            (
                "Objetivo",
                [
                    "Ajudar pessoas a buscar vagas, comparar requisitos e identificar "
                    "pontos para estudo sem prometer aprovação."
                ],
            ),
            (
                "Tecnologias",
                [
                    "Python, FastAPI, Jinja2, SQLite, CSS e JavaScript próprios, com "
                    "integração à Adzuna."
                ],
            ),
            (
                "Autor e código",
                [
                    "Desenvolvido por Eduardo Rodrigues. O código e o histórico do "
                    "projeto são públicos no GitHub."
                ],
            ),
        ],
    },
    "como-funciona": {
        "titulo": "Como funciona",
        "descricao": "Entenda fontes, compatibilidade, confiança e limites do VagaScan.",
        "intro": (
            "A análise é determinística, explicável e depende do texto disponibilizado "
            "pela fonte."
        ),
        "secoes": [
            (
                "Fontes e busca",
                [
                    "As vagas reais são fornecidas pela Adzuna. O VagaScan preserva o "
                    "link original e pode usar cache para reduzir consultas."
                ],
            ),
            (
                "Compatibilidade e confiança",
                [
                    "Compatibilidade estima aderência ao perfil de demonstração. "
                    "Confiança indica quanta evidência havia para sustentar a análise."
                ],
            ),
            (
                "Limites",
                [
                    "Descrições podem estar resumidas, a modalidade pode ser inferida "
                    "e nenhuma pontuação substitui a leitura manual da vaga."
                ],
            ),
        ],
    },
    "privacidade": {
        "titulo": "Privacidade",
        "descricao": "Como o VagaScan trata armazenamento local, sessões, logs e dados públicos.",
        "intro": "Este é um projeto pessoal sem cadastro público de usuários.",
        "secoes": [
            (
                "Vagas salvas",
                [
                    "Ficam somente no localStorage deste navegador. Limpar dados do site "
                    "ou trocar de dispositivo remove a lista."
                ],
            ),
            (
                "Cookies e logs",
                [
                    "Cookies de sessão são usados apenas na área administrativa. Logs "
                    "técnicos podem registrar eventos e erros, sem armazenar IP em claro."
                ],
            ),
            (
                "Dados consultados",
                [
                    "Descrições de vagas são dados públicos da fonte. A análise pública "
                    "não cria perfil pessoal nem cadastro de visitante."
                ],
            ),
            (
                "Contato",
                [
                    "Dúvidas podem ser encaminhadas pelos links públicos da página de "
                    "contato."
                ],
            ),
        ],
    },
    "termos": {
        "titulo": "Termos de uso",
        "descricao": "Limites e responsabilidades no uso do VagaScan.",
        "intro": (
            "Este texto descreve o funcionamento de um projeto educacional e não é "
            "consultoria jurídica."
        ),
        "secoes": [
            (
                "Estimativas",
                [
                    "Compatibilidade e confiança são estimativas. Não há garantia de "
                    "aprovação, adequação ou disponibilidade da vaga."
                ],
            ),
            (
                "Vagas e links externos",
                [
                    "A atualização e o conteúdo das vagas pertencem às fontes e "
                    "empregadores. Verifique sempre a publicação original antes de agir."
                ],
            ),
            (
                "Adzuna",
                [
                    "Vagas reais são fornecidas pela Adzuna e permanecem sujeitas aos "
                    "termos da fonte."
                ],
            ),
            (
                "Responsabilidade",
                [
                    "O usuário decide como interpretar a análise e deve confirmar "
                    "requisitos, prazos e condições diretamente na vaga original."
                ],
            ),
        ],
    },
    "contato": {
        "titulo": "Contato",
        "descricao": "Links públicos para falar com o autor do VagaScan.",
        "intro": "Não há formulário de contato nem coleta de mensagens neste site.",
        "secoes": [
            (
                "Canais",
                [
                    "Use o portfólio para conhecer outros projetos, o LinkedIn para "
                    "contato profissional ou o GitHub para questões técnicas sobre o código."
                ],
            ),
        ],
        "links": [
            ("Portfólio", "https://eduardosrodriguesdev.com.br/"),
            ("LinkedIn", "https://www.linkedin.com/in/eduardo-rodrigues-402181193"),
            ("GitHub", "https://github.com/eduardo-s-rodrigues"),
        ],
    },
}


@router.get("/sobre")
@router.get("/como-funciona")
@router.get("/privacidade")
@router.get("/termos")
@router.get("/contato")
async def pagina_institucional(request: Request):
    pagina = request.url.path.lstrip("/")
    conteudo = PAGINAS_INSTITUCIONAIS.get(pagina)
    if not conteudo:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request,
        "institucional.html",
        contexto(request, pagina=pagina, conteudo=conteudo),
    )


@router.get("/robots.txt", include_in_schema=False)
async def robots(request: Request) -> Response:
    base = str(request.app.state.settings.base_url).rstrip("/")
    return Response(
        (
            "User-agent: *\nAllow: /\nDisallow: /dashboard\nDisallow: /login\n"
            f"Sitemap: {base}/sitemap.xml\n"
        ),
        media_type="text/plain",
    )


@router.get("/sitemap.xml", include_in_schema=False)
async def sitemap(request: Request) -> Response:
    base = str(request.app.state.settings.base_url).rstrip("/")
    caminhos = (
        "/",
        "/buscar",
        "/vagas-salvas",
        "/analisar",
        "/sobre",
        "/como-funciona",
        "/privacidade",
        "/termos",
        "/contato",
    )
    urls = "".join(f"<url><loc>{base}{caminho}</loc></url>" for caminho in caminhos)
    return Response(
        f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>',
        media_type="application/xml",
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
    retry_after = limiter.reserve(
        [
            RateRule(
                "public-analysis-minute",
                client_key(request),
                request.app.state.settings.public_analysis_limit_per_minute,
                60,
            )
        ]
    )
    if retry_after:
        raise HTTPException(
            status_code=429,
            detail=f"Limite temporário de análises atingido. Tente em {retry_after} segundos.",
        )
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
