from __future__ import annotations
 
import argparse
import json
import sys
from pathlib import Path
 
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
from load_postgres import validar  # noqa: E402
from texto import normalizar  # noqa: E402
 
TIPO_REL = {"PRE": "REQUER", "CO": "CORREQUER", "EQUIV": "EQUIVALE"}   # whitelist (tipo de aresta não é parâmetro)
 
SCHEMA = [
    "CREATE CONSTRAINT curso_sigla IF NOT EXISTS FOR (c:Curso) REQUIRE c.sigla IS UNIQUE",
    "CREATE CONSTRAINT estrutura_id IF NOT EXISTS FOR (e:Estrutura) REQUIRE e.id IS UNIQUE",
    "CREATE CONSTRAINT componente_id IF NOT EXISTS FOR (c:Componente) REQUIRE c.id IS UNIQUE",
    "CREATE INDEX componente_chave IF NOT EXISTS FOR (c:Componente) ON (c.curso, c.ano, c.codigo)",
    "CREATE TEXT INDEX componente_nome_txt IF NOT EXISTS FOR (c:Componente) ON (c.nome_norm)",
]
 
 
def montar(doc: dict) -> dict:
    """Função pura: JSON canônico -> parâmetros das queries Cypher."""
    sigla, ano = doc["curso"]["sigla"], doc["estrutura"]["ano"]
    nid = lambda codigo: f"{sigla}:{ano}:{codigo}"
 
    nos = [{
        "id": nid(c["codigo"]), "curso": sigla, "ano": ano, "codigo": c["codigo"],
        "nome": c["nome"], "nome_norm": normalizar(c["nome"]),
        "carga": c.get("carga"), "unidade_carga": c.get("unidade_carga"),
        "natureza": c["natureza"], "periodo": c.get("periodo"),
    } for c in doc["componentes"]]
 
    rels: dict[str, list[dict]] = {}
    for r in doc["relacoes"]:
        tipo = TIPO_REL[r.get("tipo", "PRE")]
        # aresta sai da disciplina que EXIGE e aponta para o pré-requisito
        rels.setdefault(tipo, []).append({
            "de": nid(r["destino"]), "para": nid(r["origem"]), "logica": r.get("logica", "E")})
 
    return {
        "curso": {"sigla": sigla, "nome": doc["curso"]["nome"], "instituicao": doc["curso"].get("instituicao")},
        "estrutura": {"id": f"{sigla}:{ano}", "curso": sigla, "ano": ano, "fonte": doc["estrutura"].get("fonte")},
        "nos": nos,
        "rels": rels,
    }
 
 
def carregar(tx, p: dict) -> None:
    tx.run("MATCH (c:Componente {curso: $sigla, ano: $ano}) DETACH DELETE c",
           sigla=p["estrutura"]["curso"], ano=p["estrutura"]["ano"])
    tx.run("""MERGE (cu:Curso {sigla: $curso.sigla})
              SET cu.nome = $curso.nome, cu.instituicao = $curso.instituicao
              MERGE (e:Estrutura {id: $est.id})
              SET e.curso = $est.curso, e.ano = $est.ano, e.fonte = $est.fonte
              MERGE (cu)-[:TEM_ESTRUTURA]->(e)""", curso=p["curso"], est=p["estrutura"])
    tx.run("""MATCH (e:Estrutura {id: $eid})
              UNWIND $nos AS n
              CREATE (c:Componente) SET c = n
              CREATE (e)-[:INCLUI]->(c)""", eid=p["estrutura"]["id"], nos=p["nos"])
    for tipo, lista in p["rels"].items():            # `tipo` vem da whitelist TIPO_REL
        tx.run(f"""UNWIND $rels AS r
                   MATCH (a:Componente {{id: r.de}}), (b:Componente {{id: r.para}})
                   CREATE (a)-[:{tipo} {{logica: r.logica}}]->(b)""", rels=lista)
 
 
RESUMO = """
MATCH (e:Estrutura)-[:INCLUI]->(c:Componente)
OPTIONAL MATCH (c)-[r]->(:Componente)      // sem citar tipos: CORREQUER/EQUIVALE podem nem existir
RETURN e.curso AS curso, e.ano AS ano, count(DISTINCT c) AS componentes, count(r) AS relacoes
ORDER BY curso, ano
"""
 
 
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("json", nargs="+", help="arquivos JSON canônicos")
    args = ap.parse_args()
 
    docs = []
    for arq in args.json:
        doc = json.loads(Path(arq).read_text(encoding="utf-8"))
        erros = validar(doc)
        if erros:
            print(f"{arq}: JSON inválido:", *erros, sep="\n  - ", file=sys.stderr)
            return 1
        docs.append((arq, doc))
 
    from neo4j import GraphDatabase
    from neo4j.exceptions import DriverError, Neo4jError
 
    cfg = config.neo4j()
    driver = GraphDatabase.driver(cfg["uri"], auth=(cfg["user"], cfg["password"]))
    try:
        driver.verify_connectivity()
    except (DriverError, Neo4jError, OSError) as e:      # DriverError cobre ServiceUnavailable e SessionExpired
        print(f"Não conectou no Neo4j em {cfg['uri']}. Ele demora ~1 min para ficar healthy; "
              f"confira o .env e o `docker compose ps`.\n{e}", file=sys.stderr)
        return 2
 
    with driver.session() as sessao:
        for cmd in SCHEMA:                              # esquema fora da transação de escrita
            sessao.run(cmd).consume()
        for arq, doc in docs:
            sessao.execute_write(carregar, montar(doc))
            print(f"carregado: {arq}")
        print("\ncurso  ano  componentes  relações")
        for r in sessao.run(RESUMO):
            print(f"{r['curso']:<6} {r['ano']}  {r['componentes']:>11}  {r['relacoes']:>8}")
    driver.close()
    return 0
 
 
if __name__ == "__main__":
    sys.exit(main())