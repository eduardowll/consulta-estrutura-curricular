from __future__ import annotations
 
import argparse
import json
import sys
from pathlib import Path
 
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
from load_postgres import validar  
from texto import normalizar  # noqa: E402
 
 
def montar(doc: dict) -> tuple[dict, list[dict]]:
    """Função pura: JSON canônico -> (doc da estrutura, docs dos componentes)."""
    sigla, ano = doc["curso"]["sigla"], doc["estrutura"]["ano"]
    por_codigo = {c["codigo"]: c for c in doc["componentes"]}
 
    prereqs: dict[str, list[dict]] = {c: [] for c in por_codigo}
    for r in doc["relacoes"]:
        tipo = r.get("tipo", "PRE")
        prereqs[r["destino"]].append({
            "codigo": r["origem"],
            "nome": por_codigo[r["origem"]]["nome"],
            "tipo": tipo,
            "logica": r.get("logica", "E"),
        })
 
    componentes = []
    for c in doc["componentes"]:
        lista = sorted(prereqs[c["codigo"]], key=lambda p: p["codigo"])
        componentes.append({
            "_id": f"{sigla}:{ano}:{c['codigo']}",
            "curso": sigla,
            "ano": ano,
            "codigo": c["codigo"],
            "nome": c["nome"],
            "nome_norm": normalizar(c["nome"]),
            "carga": c.get("carga"),
            "unidade_carga": c.get("unidade_carga"),
            "natureza": c["natureza"],
            "periodo": c.get("periodo"),
            "prerequisitos": lista,
            "prereq_codigos": [p["codigo"] for p in lista if p["tipo"] == "PRE"],
        })
 
    estrutura = {
        "_id": f"{sigla}:{ano}",
        "curso": sigla,
        "curso_nome": doc["curso"]["nome"],
        "instituicao": doc["curso"].get("instituicao"),
        "ano": ano,
        "fonte": doc["estrutura"].get("fonte"),
        "n_componentes": len(componentes),
        "n_relacoes": len(doc["relacoes"]),
    }
    return estrutura, componentes
 
 
INDICES = [
    ([("curso", 1), ("ano", 1), ("codigo", 1)], {"unique": True, "name": "uq_curso_ano_codigo"}),
    ([("curso", 1), ("ano", 1), ("nome_norm", 1)], {"name": "ix_nome"}),
    ([("curso", 1), ("ano", 1), ("prereq_codigos", 1)], {"name": "ix_prereq_codigos"}),   # multikey
    ([("curso", 1), ("ano", 1), ("natureza", 1)], {"name": "ix_natureza"}),
]
 
 
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
 
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError
 
    cfg = config.mongo()
    client = MongoClient(cfg["uri"], serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
    except PyMongoError as e:
        print(f"Não conectou no Mongo em {cfg['destino']}. Confira o .env e o `docker compose ps`.\n{e}",
              file=sys.stderr)
        return 2
    db = client[cfg["dbname"]]
 
    for chave, opcoes in INDICES:
        db.componentes.create_index(chave, **opcoes)
    for arq, doc in docs:
        estrutura, componentes = montar(doc)
        db.componentes.delete_many({"curso": estrutura["curso"], "ano": estrutura["ano"]})
        db.componentes.insert_many(componentes)
        db.estruturas.replace_one({"_id": estrutura["_id"]}, estrutura, upsert=True)
        print(f"carregado: {arq}")
 
    print("\ncurso  ano  componentes  relações (prerequisitos embutidos)")
    for e in db.estruturas.find().sort([("curso", 1), ("ano", 1)]):
        n_c = db.componentes.count_documents({"curso": e["curso"], "ano": e["ano"]})
        agg = list(db.componentes.aggregate([
            {"$match": {"curso": e["curso"], "ano": e["ano"]}},
            {"$group": {"_id": None, "n": {"$sum": {"$size": "$prerequisitos"}}}}]))
        print(f"{e['curso']:<6} {e['ano']}  {n_c:>11}  {agg[0]['n'] if agg else 0:>8}")
    client.close()
    return 0
 
 
if __name__ == "__main__":
    sys.exit(main())