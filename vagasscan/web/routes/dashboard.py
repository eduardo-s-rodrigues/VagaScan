from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from vagasscan.file_organizer import OrganizadorArquivos
from vagasscan.models import ETAPAS_CANDIDATURA, STATUS_VAGAS, Candidatura, Vaga
from vagasscan.providers import ErroProvedor
from vagasscan.web.common import (
    ConsultaLimitadaError,
    RateRule,
    consulta_da_requisicao,
    contexto,
    exigir_admin,
    flash,
    provedor,
    templates,
    texto_limitado,
    vaga_do_formulario,
    validar_csrf,
)

router = APIRouter(prefix="/dashboard")


def _private(request: Request):
    exigir_admin(request)
    return request.app.state.private


@router.get("")
async def dashboard(request: Request):
    context = _private(request)
    resumo = context.relatorios.resumo()
    vagas = context.vagas.listar(limite=1000)
    candidaturas = context.candidaturas.listar()
    interviews = {"entrevista_rh", "entrevista_tecnica"}
    cards = {
        "total": len(vagas),
        "interessantes": sum(item["status"] == "interessante" for item in vagas),
        "candidaturas": len(candidaturas),
        "entrevistas": sum(item["etapa"] in interviews for item in candidaturas),
        "aguardando": sum(item["etapa"] == "aguardando_resposta" for item in candidaturas),
        "media": resumo["media_compatibilidade"],
    }
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        contexto(
            request,
            cards=cards,
            resumo=resumo,
            recentes=vagas[:10],
        ),
    )


@router.get("/buscar")
async def buscar(request: Request):
    context = _private(request)
    if not request.query_params.get("termo"):
        return templates.TemplateResponse(request, "buscar.html", contexto(request, private=True))
    try:
        consulta = consulta_da_requisicao(request)
        provider_name = str(request.query_params.get("provedor") or "adzuna")
        provider = provedor(request, provider_name, privado=True)
        service = context.vaga_service
        gate = None
        if provider_name in {"adzuna", "http"}:
            settings = request.app.state.settings
            primeira_tentativa = True

            def autorizar() -> None:
                nonlocal primeira_tentativa
                rules = []
                if primeira_tentativa:
                    rules.append(
                        RateRule(
                            "admin-search-hour",
                            str(request.session.get("admin") or "admin"),
                            settings.admin_search_limit_per_hour,
                            60 * 60,
                        )
                    )
                if provider_name == "adzuna":
                    rules.append(
                        RateRule(
                            "adzuna-global",
                            "global",
                            settings.adzuna_global_limit_per_minute,
                            60,
                        )
                    )
                retry_after = request.app.state.rate_limiter.reserve(rules)
                if retry_after:
                    raise ConsultaLimitadaError(retry_after)
                primeira_tentativa = False

            gate = autorizar
        resultado = service.buscar_e_salvar(
            provider,
            consulta,
            autorizar_consulta_externa=gate,
        )
    except ConsultaLimitadaError as exc:
        return templates.TemplateResponse(
            request,
            "buscar.html",
            contexto(
                request,
                private=True,
                error=str(exc),
                retry_after=exc.retry_after,
            ),
            status_code=429,
        )
    except (ValueError, ErroProvedor) as exc:
        return templates.TemplateResponse(
            request,
            "buscar.html",
            contexto(request, private=True, error=str(exc)),
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
            private=True,
        ),
    )


@router.get("/vagas")
async def vagas(request: Request):
    context = _private(request)
    return templates.TemplateResponse(
        request,
        "vagas.html",
        contexto(request, vagas=context.vagas.listar(limite=500)),
    )


@router.get("/vagas/nova")
async def vaga_nova_get(request: Request):
    _private(request)
    return templates.TemplateResponse(
        request, "vaga_form.html", contexto(request, values={})
    )


@router.post("/vagas/nova")
async def vaga_nova_post(request: Request):
    context = _private(request)
    form = await validar_csrf(request)
    values = {key: str(value) for key, value in form.items() if key != "csrf_token"}
    try:
        vaga = vaga_do_formulario(form)
        vaga_id, resultado = context.vaga_service.cadastrar_e_analisar(vaga)
    except ValueError as exc:
        return templates.TemplateResponse(
            request,
            "vaga_form.html",
            contexto(request, values=values, error=str(exc)),
            status_code=400,
        )
    flash(request, f"Vaga #{vaga_id} salva com {resultado.pontuacao:.1f}% de compatibilidade.")
    return RedirectResponse(f"/dashboard/vagas/{vaga_id}", status_code=303)


@router.get("/vagas/{vaga_id}")
async def vaga_detalhe(request: Request, vaga_id: int):
    context = _private(request)
    vaga = context.vagas.obter(vaga_id)
    if not vaga:
        raise HTTPException(status_code=404)
    modelo = Vaga(**{key: value for key, value in vaga.items() if key in Vaga.__dataclass_fields__})
    analise, _ = context.vaga_service.analisar_temporaria(modelo)
    return templates.TemplateResponse(
        request,
        "vaga_detalhe.html",
        contexto(
            request,
            vaga=vaga,
            requisitos=context.vagas.listar_requisitos(vaga_id),
            analise=analise,
            historico=context.vagas.historico(vaga_id),
            private=True,
            statuses=STATUS_VAGAS,
        ),
    )


@router.post("/vagas/{vaga_id}/status")
async def vaga_status(request: Request, vaga_id: int):
    context = _private(request)
    form = await validar_csrf(request)
    status = str(form.get("status") or "")
    observacao = texto_limitado(form.get("observacao"), "Observação", 1000)
    context.vagas.atualizar_status(vaga_id, status, observacao)
    flash(request, "Status atualizado.")
    return RedirectResponse(f"/dashboard/vagas/{vaga_id}", status_code=303)


@router.post("/vagas/{vaga_id}/interessante")
async def vaga_interessante(request: Request, vaga_id: int):
    context = _private(request)
    await validar_csrf(request)
    context.vagas.atualizar_status(vaga_id, "interessante", "Marcada pela interface web")
    flash(request, "Vaga marcada como interessante.")
    return RedirectResponse(f"/dashboard/vagas/{vaga_id}", status_code=303)


@router.get("/analisar")
async def analisar_get(request: Request):
    _private(request)
    return templates.TemplateResponse(
        request, "analisar.html", contexto(request, private=True, values={})
    )


@router.post("/analisar")
async def analisar_post(request: Request):
    context = _private(request)
    form = await validar_csrf(request)
    values = {key: str(value) for key, value in form.items() if key != "csrf_token"}
    try:
        vaga = Vaga(
            titulo=texto_limitado(form.get("titulo"), "Título", 200) or "Vaga importada",
            empresa=texto_limitado(form.get("empresa"), "Empresa", 200) or "Não informada",
            localizacao=texto_limitado(form.get("localizacao"), "Localização", 200)
            or "Não informada",
            descricao=texto_limitado(form.get("descricao"), "Descrição", 20_000, required=True),
        )
        if form.get("action") == "save":
            vaga_id, resultado = context.vaga_service.cadastrar_e_analisar(vaga)
            flash(request, f"Vaga #{vaga_id} salva.")
            return RedirectResponse(f"/dashboard/vagas/{vaga_id}", status_code=303)
        resultado, requisitos = context.vaga_service.analisar_temporaria(vaga)
    except ValueError as exc:
        return templates.TemplateResponse(
            request,
            "analisar.html",
            contexto(request, private=True, values=values, error=str(exc)),
            status_code=400,
        )
    return templates.TemplateResponse(
        request,
        "analisar.html",
        contexto(
            request,
            private=True,
            values=values,
            vaga=vaga,
            resultado=resultado,
            requisitos=requisitos,
        ),
    )


@router.get("/candidaturas")
async def candidaturas(request: Request):
    context = _private(request)
    return templates.TemplateResponse(
        request,
        "candidaturas.html",
        contexto(
            request,
            candidaturas=context.candidaturas.listar(),
            vagas=context.vagas.listar(limite=500),
            etapas=ETAPAS_CANDIDATURA,
            today=date.today().isoformat(),
        ),
    )


@router.post("/candidaturas")
async def candidatura_nova(request: Request):
    context = _private(request)
    form = await validar_csrf(request)
    candidatura = Candidatura(
        vaga_id=int(str(form.get("vaga_id") or "0")),
        data_candidatura=str(form.get("data_candidatura") or date.today().isoformat()),
        etapa=str(form.get("etapa") or "candidatura_enviada"),
        proxima_acao=texto_limitado(form.get("proxima_acao"), "Próxima ação", 1000),
        data_proxima_acao=str(form.get("data_proxima_acao") or "") or None,
        observacoes=texto_limitado(form.get("observacoes"), "Observações", 5000),
    )
    context.candidaturas.registrar(candidatura)
    flash(request, "Candidatura registrada.")
    return RedirectResponse("/dashboard/candidaturas", status_code=303)


@router.post("/candidaturas/{candidatura_id}")
async def candidatura_atualizar(request: Request, candidatura_id: int):
    context = _private(request)
    form = await validar_csrf(request)
    context.candidaturas.atualizar_etapa(
        candidatura_id,
        str(form.get("etapa") or ""),
        texto_limitado(form.get("proxima_acao"), "Próxima ação", 1000),
        str(form.get("data_proxima_acao") or "") or None,
        texto_limitado(form.get("observacoes"), "Observações", 5000),
    )
    flash(request, "Candidatura atualizada.")
    return RedirectResponse("/dashboard/candidaturas", status_code=303)


@router.get("/relatorios")
async def relatorios(request: Request):
    context = _private(request)
    return templates.TemplateResponse(
        request,
        "relatorios.html",
        contexto(request, resumo=context.relatorios.resumo()),
    )


@router.get("/perfil")
async def perfil_get(request: Request):
    context = _private(request)
    return templates.TemplateResponse(
        request,
        "perfil.html",
        contexto(request, perfil=context.perfil_service.carregar()),
    )


@router.post("/perfil")
async def perfil_post(request: Request):
    context = _private(request)
    form = await validar_csrf(request)
    atual = context.perfil_service.carregar()
    for field in (
        "areas_desejadas", "conhecimentos", "experiencias", "localidades_desejadas",
        "modalidades_desejadas", "idiomas", "niveis_desejados",
    ):
        atual[field] = [
            line.strip()
            for line in str(form.get(field) or "").splitlines()
            if line.strip()
        ]
    atual["formacao"] = str(form.get("formacao") or "")
    atual["nivel_profissional"] = str(form.get("nivel_profissional") or "")
    atual["experiencia_anos"] = str(form.get("experiencia_anos") or "0")
    context.perfil_service.salvar(atual)
    flash(request, "Perfil salvo com backup. As vagas não foram reanalisadas automaticamente.")
    return RedirectResponse("/dashboard/perfil", status_code=303)


@router.post("/perfil/reanalisar")
async def perfil_reanalisar(request: Request):
    context = _private(request)
    await validar_csrf(request)
    sucessos = 0
    erros = 0
    for vaga in context.vagas.listar(limite=1000):
        try:
            context.vaga_service.analisar_existente(int(vaga["id"]))
            sucessos += 1
        except (ValueError, TypeError):
            erros += 1
    flash(request, f"Reanálise concluída: {sucessos} vaga(s), {erros} erro(s).")
    return RedirectResponse("/dashboard/perfil", status_code=303)


@router.get("/documentos")
async def documentos(request: Request):
    _private(request)
    settings = request.app.state.settings
    if not (
        settings.enable_file_organizer_web
        and settings.file_organizer_source
        and settings.file_organizer_destination
    ):
        raise HTTPException(status_code=404)
    organizer = OrganizadorArquivos(
        settings.database_path.parent / "movimentacoes.json",
        caminhos_protegidos=(settings.database_path.parent.parent,),
    )
    movements = organizer.planejar(
        settings.file_organizer_source, settings.file_organizer_destination
    )
    return templates.TemplateResponse(
        request, "documentos.html", contexto(request, movements=movements)
    )


@router.post("/documentos")
async def documentos_confirmar(request: Request):
    _private(request)
    await validar_csrf(request)
    settings = request.app.state.settings
    if not (
        settings.enable_file_organizer_web
        and settings.file_organizer_source
        and settings.file_organizer_destination
    ):
        raise HTTPException(status_code=404)
    organizer = OrganizadorArquivos(
        settings.database_path.parent / "movimentacoes.json",
        caminhos_protegidos=(settings.database_path.parent.parent,),
    )
    movements = organizer.planejar(
        settings.file_organizer_source, settings.file_organizer_destination
    )
    count = organizer.executar(movements, simular=False)
    flash(request, f"{count} arquivo(s) organizado(s).")
    return RedirectResponse("/dashboard/documentos", status_code=303)
