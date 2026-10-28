from __future__ import annotations

from typing import Any
import re
from backend.database import DatabaseManager
from backend.repositories.base import CurriculoRepository
from texto import normalizar
import load_mongo


class MongoRepository(CurriculoRepository):

    def listar_estruturas(self) -> list[dict[str, Any]]:
        cursor = (
            DatabaseManager.mongo_db.estruturas
            .find({}, {"_id": 0})
            .sort([("curso", 1), ("ano", 1)])
        )
        return list(cursor)

    def buscar_componentes(
        self,
        curso: str,
        ano: int,
        codigo: str | None = None,
        nome: str | None = None,
        natureza: str | None = None,
        periodo: int | None = None,
        exige_prereq: str | None = None,
    ) -> list[dict[str, Any]]:
        filtro: dict[str, Any] = {"curso": curso.upper(), "ano": ano}

        if codigo:
            filtro["codigo"] = codigo.upper()
        if nome:
            filtro["nome_norm"] = {"$regex": re.escape(normalizar(nome))}
        if natureza:
            filtro["natureza"] = natureza
        if periodo is not None:
            filtro["periodo"] = periodo
        if exige_prereq:
            filtro["prereq_codigos"] = exige_prereq.upper()

        projecao = {
            "_id": 0,
            "codigo": 1,
            "nome": 1,
            "carga": 1,
            "unidade_carga": 1,
            "natureza": 1,
            "periodo": 1,
            "prerequisitos": 1,
        }
        cursor = DatabaseManager.mongo_db.componentes.find(filtro, projecao).sort("codigo", 1)
        return list(cursor)

    def buscar_cadeia(self, curso: str, ano: int, codigo: str) -> dict[str, Any]:
        curso_up = curso.upper()
        codigo_up = codigo.upper()

        pipeline = [
            {"$match": {"_id": f"{curso_up}:{ano}:{codigo_up}"}},
            {
                "$graphLookup": {
                    "from": "componentes",
                    "startWith": "$prereq_codigos",
                    "connectFromField": "prereq_codigos",
                    "connectToField": "codigo",
                    "as": "prereqs_raw",
                    "depthField": "nivel_zero",
                    "restrictSearchWithMatch": {"curso": curso_up, "ano": ano},
                }
            },
            {
                "$graphLookup": {
                    "from": "componentes",
                    "startWith": "$codigo",
                    "connectFromField": "codigo",
                    "connectToField": "prereq_codigos",
                    "as": "libera_raw",
                    "depthField": "nivel_zero",
                    "restrictSearchWithMatch": {"curso": curso_up, "ano": ano},
                }
            },
        ]
        res = list(DatabaseManager.mongo_db.componentes.aggregate(pipeline))
        if not res:
            return {"componente": None, "prerequisitos_cadeia": [], "libera_cadeia": []}

        doc = res[0]
        prereqs = sorted(
            [{"codigo": p["codigo"], "nome": p["nome"], "nivel": p["nivel_zero"] + 1} for p in doc.get("prereqs_raw", [])],
            key=lambda x: (x["nivel"], x["codigo"]),
        )
        libera = sorted(
            [{"codigo": l["codigo"], "nome": l["nome"], "nivel": l["nivel_zero"] + 1} for l in doc.get("libera_raw", [])],
            key=lambda x: (x["nivel"], x["codigo"]),
        )
        return {
            "componente": {"codigo": doc["codigo"], "nome": doc["nome"]},
            "prerequisitos_cadeia": prereqs,
            "libera_cadeia": libera,
        }

    def salvar_estrutura(self, doc: dict[str, Any]) -> None:
        estrutura, componentes = load_mongo.montar(doc)
        DatabaseManager.mongo_db.componentes.delete_many(
            {"curso": estrutura["curso"], "ano": estrutura["ano"]}
        )
        if componentes:
            DatabaseManager.mongo_db.componentes.insert_many(componentes)
        DatabaseManager.mongo_db.estruturas.replace_one(
            {"_id": estrutura["_id"]}, estrutura, upsert=True
        )
