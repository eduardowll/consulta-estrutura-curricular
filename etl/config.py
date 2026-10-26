"""Lê a configuração dos bancos do arquivo .env da raiz (e das variáveis de ambiente)."""
from __future__ import annotations

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def carregar_env(caminho: Path | None = None) -> dict[str, str]:
    """Parser mínimo de .env (CHAVE=valor, # comentários). Ambiente real tem prioridade."""
    valores: dict[str, str] = {}
    arq = caminho or RAIZ / ".env"
    if arq.exists():
        for linha in arq.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, _, valor = linha.partition("=")
            valores[chave.strip()] = valor.strip().strip('"').strip("'")
    valores.update({k: v for k, v in os.environ.items() if k in valores or k.startswith(("POSTGRES_", "MONGO_", "NEO4J_"))})
    return valores


def postgres() -> dict:
    e = carregar_env()
    return {
        "host": e.get("POSTGRES_HOST", "localhost"),
        "port": int(e.get("POSTGRES_PORT", 5432)),
        "dbname": e.get("POSTGRES_DB", "curriculo"),
        "user": e.get("POSTGRES_USER", "curriculo"),
        "password": e.get("POSTGRES_PASSWORD", "curriculo"),
    }