from __future__ import annotations

import hashlib
import secrets

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1


def gerar_hash_senha(senha: str) -> str:
    if len(senha) < 12:
        raise ValueError("A senha administrativa deve ter ao menos 12 caracteres.")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        senha.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32
    )
    return f"scrypt$v1${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def verificar_senha(senha: str, hash_armazenado: str) -> bool:
    try:
        partes = hash_armazenado.split("$")
        if len(partes) == 7:
            algoritmo, versao, n, r, p, salt_hex, digest_hex = partes
        elif len(partes) == 6:
            algoritmo, n, r, p, salt_hex, digest_hex = partes
            versao = "legado"
        else:
            return False
        if algoritmo != "scrypt" or versao not in {"v1", "legado"}:
            return False
        parametros = (int(n), int(r), int(p))
        salt = bytes.fromhex(salt_hex)
        esperado = bytes.fromhex(digest_hex)
        if parametros != (SCRYPT_N, SCRYPT_R, SCRYPT_P):
            return False
        if len(salt) != 16 or len(esperado) != 32:
            return False
        digest = hashlib.scrypt(
            senha.encode("utf-8"),
            salt=salt,
            n=parametros[0],
            r=parametros[1],
            p=parametros[2],
            dklen=len(esperado),
        )
    except (TypeError, ValueError):
        return False
    return secrets.compare_digest(digest.hex(), digest_hex)


def gerar_segredo_sessao() -> str:
    return secrets.token_urlsafe(48)
