"""Lê a configuração dos bancos do arquivo .env da raiz (e das variáveis de ambiente)."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote_plus

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


def mongo() -> dict:
    e = carregar_env()
    user, senha = quote_plus(e.get("MONGO_USER", "curriculo")), quote_plus(e.get("MONGO_PASSWORD", "curriculo"))
    host, porta = e.get("MONGO_HOST", "localhost"), e.get("MONGO_PORT", "27017")
    return {
        # o usuário root criado pelo container mora no banco "admin"
        "uri": f"mongodb://{user}:{senha}@{host}:{porta}/?authSource=admin",
        "dbname": e.get("MONGO_DB", "curriculo"),
        "destino": f"{host}:{porta}",
    }


def neo4j() -> dict:
    e = carregar_env()
    host, porta = e.get("NEO4J_HOST", "localhost"), e.get("NEO4J_BOLT_PORT", "7687")
    return {
        "uri": f"bolt://{host}:{porta}",
        "user": e.get("NEO4J_USER", "neo4j"),
        "password": e.get("NEO4J_PASSWORD", "curriculo123"),
    }