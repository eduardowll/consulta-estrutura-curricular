from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware

from backend.database import DatabaseManager
from backend.repositories import REPOSITORIES, get_repository
import load_postgres  # usado para validar o DAG no POST

DatabaseOption = Literal["postgres", "mongo", "neo4j", "all"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    DatabaseManager.connect_all()
    yield
    DatabaseManager.close_all()


app = FastAPI(
    title="Consulta de Estrutura Curricular API",
    description="Backend comparativo entre PostgreSQL, MongoDB e Neo4j usando Strategy + Repository Pattern.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/estruturas")
def listar_estruturas(
    db: Literal["postgres", "mongo", "neo4j"] = Query("postgres", description="Banco de dados alvo")
):
    repo = get_repository(db)
    t0 = time.perf_counter()
    dados = repo.listar_estruturas()
    tempo_ms = round((time.perf_counter() - t0) * 1000, 4)

    return {
        "database": db,
        "execution_time_ms": tempo_ms,
        "total": len(dados),
        "data": dados,
    }


@app.get("/api/componentes")
def consultar_componentes(
    db: DatabaseOption = Query("postgres", description="postgres, mongo, neo4j ou all"),
    curso: str = Query("TADS", description="Sigla do curso (ex: TADS)"),
    ano: int = Query(2019, description="Ano da estrutura (ex: 2015, 2019)"),
    codigo: str | None = Query(None, description="Código exato (ex: TAD0029)"),
    nome: str | None = Query(None, description="Busca parcial por nome (ex: banco)"),
    natureza: str | None = Query(None, description="obrigatoria, optativa, atividade_complementar"),
    periodo: int | None = Query(None, description="Período/Semestre"),
    exige_prereq: str | None = Query(None, description="Código do pré-requisito direto exigido"),
):
    if db == "all":
        tempos = {}
        dados = []
        for nome_db, repo in REPOSITORIES.items():
            t0 = time.perf_counter()
            dados = repo.buscar_componentes(curso, ano, codigo, nome, natureza, periodo, exige_prereq)
            tempos[nome_db] = round((time.perf_counter() - t0) * 1000, 4)
        return {
            "database": "all",
            "execution_times_ms": tempos,
            "total": len(dados),
            "data": dados,
        }

    repo = get_repository(db)
    t0 = time.perf_counter()
    dados = repo.buscar_componentes(curso, ano, codigo, nome, natureza, periodo, exige_prereq)
    tempo_ms = round((time.perf_counter() - t0) * 1000, 4)

    return {
        "database": db,
        "execution_time_ms": tempo_ms,
        "total": len(dados),
        "data": dados,
    }


@app.get("/api/componentes/{codigo}/cadeia")
def consultar_cadeia_dependencias(
    codigo: str,
    db: DatabaseOption = Query("neo4j", description="postgres, mongo, neo4j ou all"),
    curso: str = Query("TADS", description="Sigla do curso"),
    ano: int = Query(2019, description="Ano da estrutura"),
):
    if db == "all":
        tempos = {}
        dados = {}
        for nome_db, repo in REPOSITORIES.items():
            t0 = time.perf_counter()
            dados = repo.buscar_cadeia(curso, ano, codigo)
            tempos[nome_db] = round((time.perf_counter() - t0) * 1000, 4)
        if not dados.get("componente"):
            raise HTTPException(status_code=404, detail=f"Componente '{codigo}' não encontrado em {curso} {ano}.")
        return {
            "database": "all",
            "execution_times_ms": tempos,
            "data": dados,
        }

    repo = get_repository(db)
    t0 = time.perf_counter()
    dados = repo.buscar_cadeia(curso, ano, codigo)
    tempo_ms = round((time.perf_counter() - t0) * 1000, 4)

    if not dados.get("componente"):
        raise HTTPException(status_code=404, detail=f"Componente '{codigo}' não encontrado em {curso} {ano}.")

    return {
        "database": db,
        "execution_time_ms": tempo_ms,
        "data": dados,
    }


@app.post("/api/estruturas", status_code=201)
def cadastrar_estrutura(doc: dict[str, Any] = Body(..., description="JSON canónico de qualquer curso")):
    """Item 4: Cadastra a estrutura curricular de qualquer curso nos 3 bancos."""
    erros = load_postgres.validar(doc)
    if erros:
        raise HTTPException(status_code=422, detail={"erros": erros})

    tempos = {}
    for nome_db, repo in REPOSITORIES.items():
        t0 = time.perf_counter()
        repo.salvar_estrutura(doc)
        tempos[nome_db] = round((time.perf_counter() - t0) * 1000, 4)

    return {
        "mensagem": f"Estrutura {doc['curso']['sigla']} ({doc['estrutura']['ano']}) registada nos 3 bancos.",
        "execution_times_ms": tempos,
    }