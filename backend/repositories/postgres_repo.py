from __future__ import annotations

from typing import Any
from psycopg2.extras import RealDictCursor

from backend.database import DatabaseManager
from backend.repositories.base import CurriculoRepository
import load_postgres  # importado via sys.path configurado no database.py
from texto import normalizar


class PostgresRepository(CurriculoRepository):

    def listar_estruturas(self) -> list[dict[str, Any]]:
        sql = """
            SELECT cu.sigla AS curso, cu.nome AS curso_nome, cu.instituicao,
                   e.ano, e.fonte,
                   (SELECT count(*) FROM estrutura_componente ec WHERE ec.estrutura_id = e.id) AS n_componentes,
                   (SELECT count(*) FROM relacao_componente r WHERE r.estrutura_id = e.id) AS n_relacoes
            FROM estrutura_curricular e
            JOIN curso cu ON cu.id = e.curso_id
            ORDER BY cu.sigla, e.ano
        """
        with DatabaseManager.postgres_connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql)
            return [dict(r) for r in cur.fetchall()]

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
        sql = """
            SELECT c.codigo, ec.nome, ec.carga, ec.unidade_carga, ec.natureza, ec.periodo,
                   COALESCE(
                       json_agg(
                           json_build_object(
                               'codigo', co_orig.codigo,
                               'nome', ec_orig.nome,
                               'tipo', r.tipo,
                               'logica', r.logica
                           ) ORDER BY co_orig.codigo
                       ) FILTER (WHERE co_orig.codigo IS NOT NULL),
                       '[]'::json
                   ) AS prerequisitos
            FROM estrutura_curricular e
            JOIN curso cu ON cu.id = e.curso_id
            JOIN estrutura_componente ec ON ec.estrutura_id = e.id
            JOIN componente c ON c.id = ec.componente_id
            LEFT JOIN relacao_componente r
                   ON r.estrutura_id = e.id AND r.destino_id = c.id
            LEFT JOIN componente co_orig ON co_orig.id = r.origem_id
            LEFT JOIN estrutura_componente ec_orig
                   ON ec_orig.estrutura_id = e.id AND ec_orig.componente_id = co_orig.id
            WHERE cu.sigla = %(curso)s
              AND e.ano = %(ano)s
              AND (%(codigo)s IS NULL OR c.codigo = %(codigo)s)
              AND (%(nome)s IS NULL OR translate(lower(ec.nome), 'áàâãäéèêëíìîïóòôõöúùûüç', 'aaaaaeeeeiiiiooooouuuuc') LIKE %(nome_like)s)
              AND (%(natureza)s IS NULL OR ec.natureza = %(natureza)s)
              AND (%(periodo)s IS NULL OR ec.periodo = %(periodo)s)
              AND (%(exige_prereq)s IS NULL OR EXISTS (
                  SELECT 1 FROM relacao_componente r2
                  JOIN componente c_pre ON c_pre.id = r2.origem_id
                  WHERE r2.estrutura_id = e.id
                    AND r2.destino_id = c.id
                    AND r2.tipo = 'PRE'
                    AND c_pre.codigo = %(exige_prereq)s
              ))
            GROUP BY c.codigo, ec.nome, ec.carga, ec.unidade_carga, ec.natureza, ec.periodo
            ORDER BY c.codigo
        """
        params = {
            "curso": curso.upper(),
            "ano": ano,
            "codigo": codigo.upper() if codigo else None,
            "nome": nome,
            "nome_like": "%" + normalizar(nome).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%" if nome else None,
            "natureza": natureza,
            "periodo": periodo,
            "exige_prereq": exige_prereq.upper() if exige_prereq else None,
        }
        with DatabaseManager.postgres_connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

    def buscar_cadeia(self, curso: str, ano: int, codigo: str) -> dict[str, Any]:
        sql = """
            WITH RECURSIVE
            est AS (
                SELECT e.id AS estrutura_id
                FROM estrutura_curricular e
                JOIN curso cu ON cu.id = e.curso_id
                WHERE cu.sigla = %(curso)s AND e.ano = %(ano)s
            ),
            alvo AS (
                SELECT c.id, c.codigo, ec.nome
                FROM componente c
                JOIN estrutura_componente ec ON ec.componente_id = c.id
                JOIN est ON est.estrutura_id = ec.estrutura_id
                WHERE c.codigo = %(codigo)s
            ),
            prereqs(id, codigo, nome, nivel) AS (
                SELECT c.id, c.codigo, ec.nome, 1
                FROM relacao_componente r
                JOIN est ON est.estrutura_id = r.estrutura_id
                JOIN alvo a ON a.id = r.destino_id
                JOIN componente c ON c.id = r.origem_id
                JOIN estrutura_componente ec ON ec.estrutura_id = est.estrutura_id AND ec.componente_id = c.id
                WHERE r.tipo = 'PRE'
              UNION ALL
                SELECT c.id, c.codigo, ec.nome, p.nivel + 1
                FROM prereqs p
                JOIN est ON true
                JOIN relacao_componente r ON r.estrutura_id = est.estrutura_id AND r.destino_id = p.id
                JOIN componente c ON c.id = r.origem_id
                JOIN estrutura_componente ec ON ec.estrutura_id = est.estrutura_id AND ec.componente_id = c.id
                WHERE r.tipo = 'PRE'
            ),
            libera(id, codigo, nome, nivel) AS (
                SELECT c.id, c.codigo, ec.nome, 1
                FROM relacao_componente r
                JOIN est ON est.estrutura_id = r.estrutura_id
                JOIN alvo a ON a.id = r.origem_id
                JOIN componente c ON c.id = r.destino_id
                JOIN estrutura_componente ec ON ec.estrutura_id = est.estrutura_id AND ec.componente_id = c.id
                WHERE r.tipo = 'PRE'
              UNION ALL
                SELECT c.id, c.codigo, ec.nome, l.nivel + 1
                FROM libera l
                JOIN est ON true
                JOIN relacao_componente r ON r.estrutura_id = est.estrutura_id AND r.origem_id = l.id
                JOIN componente c ON c.id = r.destino_id
                JOIN estrutura_componente ec ON ec.estrutura_id = est.estrutura_id AND ec.componente_id = c.id
                WHERE r.tipo = 'PRE'
            )
            SELECT
                (SELECT json_build_object('codigo', codigo, 'nome', nome) FROM alvo) AS componente,
                COALESCE((
                    SELECT json_agg(x ORDER BY x.nivel, x.codigo)
                    FROM (SELECT codigo, nome, MIN(nivel) AS nivel FROM prereqs GROUP BY codigo, nome) x
                ), '[]'::json) AS prerequisitos_cadeia,
                COALESCE((
                    SELECT json_agg(y ORDER BY y.nivel, y.codigo)
                    FROM (SELECT codigo, nome, MIN(nivel) AS nivel FROM libera GROUP BY codigo, nome) y
                ), '[]'::json) AS libera_cadeia;
        """
        params = {"curso": curso.upper(), "ano": ano, "codigo": codigo.upper()}
        with DatabaseManager.postgres_connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row else {"componente": None, "prerequisitos_cadeia": [], "libera_cadeia": []}

    def salvar_estrutura(self, doc: dict[str, Any]) -> None:
        with DatabaseManager.postgres_connection() as conn, conn.cursor() as cur:
            for sql, params in load_postgres.comandos(doc):
                cur.execute(sql, params)
