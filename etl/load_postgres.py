from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402

SCHEMA = config.RAIZ / "db" / "postgres" / "init.sql"
LOGICAS = {"E", "OU"}
TIPOS = {"PRE", "CO", "EQUIV"}
NATUREZAS = {"obrigatoria", "optativa", "atividade_complementar", "outra"}

# Validação

def validar(doc: dict) -> list[str]:
    erros: list[str] = []
    if not isinstance(doc, dict):
        return ["JSON precisa ser um objeto"]
    for chave, tipo in (("curso", dict), ("estrutura", dict), ("componentes", list), ("relacoes", list)):
        if not isinstance(doc.get(chave), tipo):
            return [f"'{chave}' ausente ou com tipo inválido"]
    for chave in ("sigla", "nome"):
        if not isinstance(doc["curso"].get(chave), str) or not doc["curso"][chave].strip():
            erros.append(f"curso.{chave} precisa ser texto não vazio")
    sigla = doc["curso"].get("sigla", "")
    if isinstance(sigla, str) and (sigla != sigla.strip().upper()):
        erros.append("curso.sigla deve estar em maiúsculas, sem espaços nas extremidades")
    if type(doc["estrutura"].get("ano")) is not int:
        erros.append("estrutura.ano precisa ser inteiro")
    for objeto, chave in ((doc["curso"], "instituicao"), (doc["estrutura"], "fonte")):
        if objeto.get(chave) is not None and not isinstance(objeto[chave], str):
            erros.append(f"{chave} precisa ser texto")
    if not doc["componentes"]:
        erros.append("componentes não pode estar vazio")
    for c in doc["componentes"]:
        if not isinstance(c, dict):
            return ["cada componente precisa ser um objeto"]
        for chave in ("codigo", "nome", "natureza"):
            if not isinstance(c.get(chave), str) or not c[chave].strip():
                erros.append(f"componente.{chave} precisa ser texto não vazio")
        codigo = c.get("codigo")
        if isinstance(codigo, str) and codigo != codigo.strip().upper():
            erros.append("código deve estar em maiúsculas, sem espaços nas extremidades")
        for chave, minimo in (("carga", 0), ("periodo", 1)):
            valor = c.get(chave)
            if valor is not None and (type(valor) is not int or valor < minimo):
                erros.append(f"{chave} precisa ser inteiro >= {minimo}")
        if c.get("unidade_carga") is not None and not isinstance(c["unidade_carga"], str):
            erros.append("unidade_carga precisa ser texto")
    for r in doc["relacoes"]:
        if not isinstance(r, dict):
            return ["cada relação precisa ser um objeto"]
        for chave in ("origem", "destino", "tipo", "logica"):
            if chave in r and not isinstance(r[chave], str):
                erros.append(f"relação.{chave} precisa ser texto")
        if not r.get("origem") or not r.get("destino"):
            erros.append("relação precisa de origem e destino")
    if erros:
        return erros

    codigos = [c.get("codigo") for c in doc["componentes"]]
    if len(set(codigos)) != len(codigos):
        repetidos = sorted({c for c in codigos if codigos.count(c) > 1})
        erros.append(f"códigos de componente repetidos: {repetidos}")
    for c in doc["componentes"]:
        if not c.get("codigo") or not c.get("nome"):
            erros.append(f"componente sem codigo/nome: {c}")
        if c.get("natureza") not in NATUREZAS:
            erros.append(f"{c.get('codigo')}: natureza inválida '{c.get('natureza')}'")

    conhecidos = set(codigos)
    arestas: dict[str, set[str]] = {}
    vistos = set()
    for r in doc["relacoes"]:
        o, d = r.get("origem"), r.get("destino")
        if o not in conhecidos or d not in conhecidos:
            erros.append(f"relação referencia componente inexistente: {o} -> {d}")
            continue
        if o == d:
            erros.append(f"relação de {o} com ele mesmo")
        if r.get("tipo", "PRE") not in TIPOS or r.get("logica", "E") not in LOGICAS:
            erros.append(f"tipo/logica inválido em {o} -> {d}: {r}")
        chave = (o, d, r.get("tipo", "PRE"))
        if chave in vistos:
            erros.append(f"relação duplicada: {chave}")
        vistos.add(chave)
        if r.get("tipo", "PRE") == "PRE":
            arestas.setdefault(d, set()).add(o)

    # pré-requisitos formam um DAG: ciclo = erro de extração
    estado: dict[str, int] = {}

    def tem_ciclo(no: str) -> bool:
        estado[no] = 1
        for p in arestas.get(no, ()):
            if estado.get(p) == 1 or (estado.get(p) is None and tem_ciclo(p)):
                return True
        estado[no] = 2
        return False

    if any(estado.get(n) is None and tem_ciclo(n) for n in list(arestas)):
        erros.append("ciclo nos pré-requisitos")
    return erros

# Comandos SQL

ESTRUTURA_ID = """(SELECT e.id FROM estrutura_curricular e
                   JOIN curso cu ON cu.id = e.curso_id
                   WHERE cu.sigla = %(sigla)s AND e.ano = %(ano)s)"""


def comandos(doc: dict) -> list[tuple[str, dict]]:
    p = {
        "sigla": doc["curso"]["sigla"],
        "nome": doc["curso"]["nome"],
        "instituicao": doc["curso"].get("instituicao"),
        "ano": doc["estrutura"]["ano"],
        "fonte": doc["estrutura"].get("fonte"),
        "componentes": json.dumps(doc["componentes"], ensure_ascii=False),
        "relacoes": json.dumps(doc["relacoes"], ensure_ascii=False),
    }
    return [
        # 1. curso
        ("""INSERT INTO curso (sigla, nome, instituicao)
            VALUES (%(sigla)s, %(nome)s, %(instituicao)s)
            ON CONFLICT (sigla) DO UPDATE
              SET nome = EXCLUDED.nome, instituicao = EXCLUDED.instituicao""", p),
        # 2. estrutura (curso + ano)
        ("""INSERT INTO estrutura_curricular (curso_id, ano, fonte)
            SELECT id, %(ano)s, %(fonte)s FROM curso WHERE sigla = %(sigla)s
            ON CONFLICT (curso_id, ano) DO UPDATE SET fonte = EXCLUDED.fonte""", p),
        # 3. limpa a versão anterior desta estrutura (as relações saem em cascata)
        (f"DELETE FROM estrutura_componente WHERE estrutura_id = {ESTRUTURA_ID}", p),
        # 4. identidade dos componentes no curso
        ("""INSERT INTO componente (curso_id, codigo)
            SELECT cu.id, x.codigo
            FROM curso cu,
                 jsonb_to_recordset(%(componentes)s::jsonb) AS x(codigo text)
            WHERE cu.sigla = %(sigla)s
            ON CONFLICT (curso_id, codigo) DO NOTHING""", p),
        # 5. atributos dos componentes nesta estrutura
        (f"""INSERT INTO estrutura_componente
               (estrutura_id, componente_id, nome, carga, unidade_carga, natureza, periodo)
            SELECT {ESTRUTURA_ID}, c.id, x.nome, x.carga, x.unidade_carga, x.natureza, x.periodo
            FROM curso cu
            CROSS JOIN jsonb_to_recordset(%(componentes)s::jsonb)
                 AS x(codigo text, nome text, carga int, unidade_carga text,
                      natureza text, periodo int)
            JOIN componente c ON c.curso_id = cu.id AND c.codigo = x.codigo
            WHERE cu.sigla = %(sigla)s""", p),
        # 6. relações (pré-requisitos)
        (f"""INSERT INTO relacao_componente
               (estrutura_id, origem_id, destino_id, tipo, logica)
            SELECT {ESTRUTURA_ID}, o.id, d.id, COALESCE(r.tipo, 'PRE'), COALESCE(r.logica, 'E')
            FROM curso cu
            CROSS JOIN jsonb_to_recordset(%(relacoes)s::jsonb)
                 AS r(origem text, destino text, tipo text, logica text)
            JOIN componente o ON o.curso_id = cu.id AND o.codigo = r.origem
            JOIN componente d ON d.curso_id = cu.id AND d.codigo = r.destino
            WHERE cu.sigla = %(sigla)s""", p),
    ]


RESUMO = """
SELECT cu.sigla, e.ano,
       (SELECT count(*) FROM estrutura_componente ec WHERE ec.estrutura_id = e.id),
       (SELECT count(*) FROM relacao_componente  r  WHERE r.estrutura_id  = e.id)
FROM estrutura_curricular e JOIN curso cu ON cu.id = e.curso_id
ORDER BY cu.sigla, e.ano
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("json", nargs="*", help="arquivos JSON canônicos")
    ap.add_argument("--so-schema", action="store_true", help="só cria as tabelas")
    args = ap.parse_args()

    docs = []
    for arq in args.json:
        doc = json.loads(Path(arq).read_text(encoding="utf-8"))
        erros = validar(doc)
        if erros:
            print(f"{arq}: JSON inválido:", *erros, sep="\n  - ", file=sys.stderr)
            return 1
        docs.append((arq, doc))
    if not docs and not args.so_schema:
        ap.error("informe ao menos um JSON (ou --so-schema)")

    import psycopg2  # import tardio: validar/comandos funcionam sem o driver

    cfg = config.postgres()
    try:
        conn = psycopg2.connect(**cfg)
    except psycopg2.OperationalError as e:
        print(f"Não conectou em {cfg['host']}:{cfg['port']}/{cfg['dbname']} "
              f"(usuário {cfg['user']}). Confira o .env e o `docker compose ps`.\n{e}", file=sys.stderr)
        return 2
    with conn:                               # uma transação só
        with conn.cursor() as cur:
            cur.execute(SCHEMA.read_text(encoding="utf-8"))
            for arq, doc in docs:
                for sql, params in comandos(doc):
                    cur.execute(sql, params)
                print(f"carregado: {arq}")
            cur.execute(RESUMO)
            print("\ncurso  ano  componentes  relações")
            for sigla, ano, n_c, n_r in cur.fetchall():
                print(f"{sigla:<6} {ano}  {n_c:>11}  {n_r:>8}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())