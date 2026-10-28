from __future__ import annotations

from typing import Any
from backend.database import DatabaseManager
from backend.repositories.base import CurriculoRepository
from texto import normalizar
import load_neo4j


class Neo4jRepository(CurriculoRepository):

    def listar_estruturas(self) -> list[dict[str, Any]]:
        cypher = """
            MATCH (cu:Curso)-[:TEM_ESTRUTURA]->(e:Estrutura)
            OPTIONAL MATCH (e)-[:INCLUI]->(c:Componente)
            OPTIONAL MATCH (c)-[r]->(:Componente)
            RETURN cu.sigla AS curso, cu.nome AS curso_nome, cu.instituicao AS instituicao,
                   e.ano AS ano, e.fonte AS fonte,
                   count(DISTINCT c) AS n_componentes, count(r) AS n_relacoes
            ORDER BY curso, ano
        """
        with DatabaseManager.neo4j_driver.session() as session:
            return [dict(r) for r in session.run(cypher)]

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
        cypher = """
            MATCH (e:Estrutura {id: $est_id})-[:INCLUI]->(c:Componente)
            WHERE ($codigo IS NULL OR c.codigo = $codigo)
              AND ($nome_norm IS NULL OR c.nome_norm CONTAINS $nome_norm)
              AND ($natureza IS NULL OR c.natureza = $natureza)
              AND ($periodo IS NULL OR c.periodo = $periodo)
              AND ($exige_prereq IS NULL OR (c)-[:REQUER]->(:Componente {codigo: $exige_prereq}))
            OPTIONAL MATCH (c)-[r:REQUER|CORREQUER|EQUIVALE]->(pre:Componente)
            WITH c, pre, r ORDER BY pre.codigo
            RETURN c.codigo AS codigo, c.nome AS nome, c.carga AS carga,
                   c.unidade_carga AS unidade_carga, c.natureza AS natureza, c.periodo AS periodo,
                   [x IN collect(
                       CASE WHEN pre IS NOT NULL THEN {
                           codigo: pre.codigo,
                           nome: pre.nome,
                           tipo: CASE type(r) WHEN 'REQUER' THEN 'PRE' WHEN 'CORREQUER' THEN 'CO' ELSE 'EQUIV' END,
                           logica: r.logica
                       } END
                   ) WHERE x IS NOT NULL] AS prerequisitos
            ORDER BY codigo
        """
        params = {
            "est_id": f"{curso.upper()}:{ano}",
            "codigo": codigo.upper() if codigo else None,
            "nome_norm": normalizar(nome) if nome else None,
            "natureza": natureza,
            "periodo": periodo,
            "exige_prereq": exige_prereq.upper() if exige_prereq else None,
        }
        with DatabaseManager.neo4j_driver.session() as session:
            return [dict(r) for r in session.run(cypher, **params)]

    def buscar_cadeia(self, curso: str, ano: int, codigo: str) -> dict[str, Any]:
        cypher = """
            MATCH (alvo:Componente {id: $id})
            OPTIONAL MATCH p_pre = (alvo)-[:REQUER*1..]->(pre:Componente)
            WITH alvo, pre, min(length(p_pre)) AS nivel_pre
            ORDER BY nivel_pre, pre.codigo
            WITH alvo, collect(
                CASE WHEN pre IS NOT NULL THEN {codigo: pre.codigo, nome: pre.nome, nivel: nivel_pre} END
            ) AS prereqs
            OPTIONAL MATCH p_lib = (dep:Componente)-[:REQUER*1..]->(alvo)
            WITH alvo, prereqs, dep, min(length(p_lib)) AS nivel_lib
            ORDER BY nivel_lib, dep.codigo
            RETURN {codigo: alvo.codigo, nome: alvo.nome} AS componente,
                   [x IN prereqs WHERE x IS NOT NULL] AS prerequisitos_cadeia,
                   [y IN collect(
                       CASE WHEN dep IS NOT NULL THEN {codigo: dep.codigo, nome: dep.nome, nivel: nivel_lib} END
                   ) WHERE y IS NOT NULL] AS libera_cadeia
        """
        alvo_id = f"{curso.upper()}:{ano}:{codigo.upper()}"
        with DatabaseManager.neo4j_driver.session() as session:
            rec = session.run(cypher, id=alvo_id).single()
            if not rec:
                return {"componente": None, "prerequisitos_cadeia": [], "libera_cadeia": []}
            return dict(rec)

    def salvar_estrutura(self, doc: dict[str, Any]) -> None:
        with DatabaseManager.neo4j_driver.session() as session:
            session.execute_write(load_neo4j.carregar, load_neo4j.montar(doc))
