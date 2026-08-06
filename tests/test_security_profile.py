from __future__ import annotations

import json
from pathlib import Path

import pytest

from vagasscan.security import gerar_hash_senha, gerar_segredo_sessao, verificar_senha
from vagasscan.services.profile import PerfilService


def profile() -> dict[str, object]:
    return {
        "conhecimentos": ["Python", "SQL"],
        "areas_desejadas": ["backend"],
        "experiencias": ["Projeto pessoal"],
        "localidades_desejadas": ["Remoto"],
        "modalidades_desejadas": ["remoto"],
        "idiomas": ["Português"],
        "niveis_desejados": ["júnior"],
        "formacao": "ADS cursando",
        "nivel_profissional": "júnior",
        "experiencia_anos": 1,
    }


def test_hash_scrypt_e_segredo() -> None:
    password_hash = gerar_hash_senha("Senha forte de teste 123!")
    assert password_hash.startswith("scrypt$v1$")
    assert verificar_senha("Senha forte de teste 123!", password_hash)
    assert not verificar_senha("senha errada", password_hash)
    assert len(gerar_segredo_sessao()) >= 48
    with pytest.raises(ValueError, match="12 caracteres"):
        gerar_hash_senha("curta")


def test_perfil_cria_backup_e_escrita_valida(tmp_path: Path) -> None:
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(profile()), encoding="utf-8")
    service = PerfilService(path)
    updated = profile()
    updated["conhecimentos"] = ["Python", "FastAPI"]
    backup = service.salvar(updated)
    assert backup is not None and backup.exists()
    assert json.loads(backup.read_text(encoding="utf-8"))["conhecimentos"] == [
        "Python",
        "SQL",
    ]
    assert service.carregar()["conhecimentos"] == ["Python", "FastAPI"]
    assert list(tmp_path.glob("*.tmp")) == []


def test_perfil_rejeita_dados_invalidos() -> None:
    invalid = profile()
    invalid["conhecimentos"] = []
    with pytest.raises(ValueError, match="ao menos um"):
        PerfilService.validar(invalid)
