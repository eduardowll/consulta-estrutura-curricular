from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.database import DatabaseManager
from backend.repositories import REPOSITORIES, get_repository
import load_postgres

DatabaseOption = Literal["postgres", "mongo", "neo4j", "all"]
FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        DatabaseManager.connect_all()
        yield
    finally:
        DatabaseManager.close_all()


app = FastAPI(
    title="Consulta de Estrutura Curricular API",
    description="Consulta e comparação entre PostgreSQL, MongoDB e Neo4j.",
    version="1.1.0", lifespan=lifespan,
)


def executar(db: str, metodo: str, *args):
    if not DatabaseManager.status.get(db):
        raise HTTPException(503, f"{db} indisponível. Verifique os containers e reinicie a API.")
    inicio = time.perf_counter()
    try:
        dados = getattr(get_repository(db), metodo)(*args)
    except Exception:
        logger.exception("Falha em %s no banco %s", metodo, db)
        raise HTTPException(503, f"Não foi possível consultar {db}. Verifique a conexão e a carga dos dados.") from None
    return dados, round((time.perf_counter() - inicio) * 1000, 4)


def consultar(db: str, metodo: str, *args):
    if db != "all":
        dados, tempo = executar(db, metodo, *args)
        return {"database": db, "execution_time_ms": tempo, "data": dados}
    resultados, tempos = {}, {}
    for nome_db in REPOSITORIES:
        resultados[nome_db], tempos[nome_db] = executar(nome_db, metodo, *args)
    canonical = [json.dumps(d, sort_keys=True, ensure_ascii=False) for d in resultados.values()]
    return {
        "database": "all", "execution_times_ms": tempos,
        "results_by_database": resultados,
        "results_match": len(set(canonical)) == 1,
        "data": resultados["postgres"],
    }


@app.get("/api/status")
def status():
    return {"databases": DatabaseManager.status, "status_scope": "startup"}


@app.get("/api/estruturas")
def listar_estruturas(db: Literal["postgres", "mongo", "neo4j"] = "postgres"):
    resultado = consultar(db, "listar_estruturas")
    resultado["total"] = len(resultado["data"])
    return resultado


@app.get("/api/componentes")
def consultar_componentes(
    db: DatabaseOption = "postgres", curso: str = "TADS", ano: int = 2019,
    codigo: str | None = None, nome: str | None = None,
    natureza: Literal["obrigatoria", "optativa", "atividade_complementar", "outra"] | None = None,
    periodo: int | None = Query(None, ge=1), exige_prereq: str | None = None,
):
    resultado = consultar(db, "buscar_componentes", curso.strip(), ano,
                          codigo.strip() if codigo else None, nome.strip() if nome else None,
                          natureza, periodo, exige_prereq.strip() if exige_prereq else None)
    resultado["total"] = len(resultado["data"])
    return resultado


@app.get("/api/componentes/{codigo}/cadeia")
def consultar_cadeia_dependencias(codigo: str, db: DatabaseOption = "neo4j", curso: str = "TADS", ano: int = 2019):
    resultado = consultar(db, "buscar_cadeia", curso.strip(), ano, codigo.strip())
    if not resultado["data"].get("componente"):
        raise HTTPException(404, f"Componente '{codigo}' não encontrado em {curso} {ano}.")
    return resultado


@app.post("/api/estruturas", status_code=201)
def cadastrar_estrutura(doc: dict[str, Any] = Body(...)):
    erros = load_postgres.validar(doc)
    if erros:
        raise HTTPException(422, detail={"erros": erros})
    # Detecte bancos ausentes antes de começar uma gravação em múltiplos bancos.
    indisponiveis = [db for db in REPOSITORIES if not DatabaseManager.status.get(db)]
    if indisponiveis:
        raise HTTPException(503, detail={"mensagem": "Importação requer os três bancos disponíveis.", "indisponiveis": indisponiveis})
    tempos = {}
    for db in REPOSITORIES:
        try:
            _, tempos[db] = executar(db, "salvar_estrutura", doc)
        except HTTPException:
            raise HTTPException(503, detail={
                "mensagem": "Importação interrompida. Não há transação distribuída; reenvie o arquivo após corrigir a conexão.",
                "bancos_atualizados": list(tempos), "banco_com_falha": db,
            }) from None
    return {"mensagem": f"Estrutura {doc['curso']['sigla']} ({doc['estrutura']['ano']}) registrada nos 3 bancos.",
            "execution_times_ms": tempos}


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(FRONTEND / "index.html")


app.mount("/assets", StaticFiles(directory=FRONTEND), name="assets")
