"""Testes reais: exigem os três bancos iniciados e as duas matrizes carregadas."""
import copy
import os
import unittest
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from backend.main import app
from backend.database import DatabaseManager
from backend.repositories import REPOSITORIES


@unittest.skipUnless(os.environ.get('RUN_INTEGRATION') == '1', 'Defina RUN_INTEGRATION=1 para usar os bancos locais')
class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()
        if not all(DatabaseManager.status.values()) or len(DatabaseManager.status) != 3:
            cls.client.__exit__(None, None, None)
            raise RuntimeError('Os três bancos precisam estar disponíveis')

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def test_matrices_and_every_dependency_chain(self):
        for year, count in [(2015, 34), (2019, 37)]:
            response = self.client.get(f'/api/componentes?db=all&ano={year}')
            self.assertEqual(response.status_code, 200, response.text)
            result = response.json()
            self.assertEqual(result['total'], count)
            self.assertTrue(result['results_match'])
            for item in result['data']:
                with self.subTest(year=year, code=item['codigo']):
                    chain = self.client.get(f"/api/componentes/{item['codigo']}/cadeia?db=all&ano={year}")
                    self.assertEqual(chain.status_code, 200, chain.text)
                    self.assertTrue(chain.json()['results_match'], chain.text)

    def test_combined_filters_and_literal_search(self):
        for query in ['nome=programacao', 'nome=PROGRAMAÇÃO', 'nome=banco&natureza=obrigatoria',
                      'codigo=tad0029', 'exige_prereq=tad0102', 'nome=%25', 'nome=%5B', 'nome=.', 'periodo=1']:
            with self.subTest(query=query):
                response = self.client.get('/api/componentes?db=all&' + query)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertTrue(response.json()['results_match'], response.text)
        self.assertEqual(self.client.get('/api/componentes/INEXISTENTE/cadeia?db=all').status_code, 404)

    def test_parallel_postgres_reads(self):
        def query(_):
            return self.client.get('/api/componentes?db=postgres').status_code
        with ThreadPoolExecutor(max_workers=8) as executor:
            self.assertEqual(list(executor.map(query, range(24))), [200] * 24)

    def test_import_idempotence_relation_types_and_long_chain(self):
        # Sigla exclusiva para nunca sobrescrever uma matriz do usuário.
        import uuid
        course = 'TEST_' + uuid.uuid4().hex.upper()
        doc = {'curso': {'sigla': course, 'nome': 'Curso temporário'}, 'estrutura': {'ano': 2026},
               'componentes': [{'codigo': f'C{i:02}', 'nome': f'Programação {i}', 'natureza': 'obrigatoria',
                                'carga': 4, 'unidade_carga': 'creditos', 'periodo': i + 1} for i in range(13)],
               'relacoes': [{'origem': f'C{i:02}', 'destino': f'C{i+1:02}'} for i in range(12)]}
        doc['relacoes'].extend([{'origem': 'C00', 'destino': 'C12', 'tipo': 'CO'},
                                {'origem': 'C01', 'destino': 'C12', 'tipo': 'EQUIV'}])
        try:
            for _ in range(2):
                response = self.client.post('/api/estruturas', json=doc)
                self.assertEqual(response.status_code, 201, response.text)
            response = self.client.get(f'/api/componentes/C12/cadeia?db=all&curso={course}&ano=2026')
            self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue(response.json()['results_match'], response.text)
            self.assertEqual(len(response.json()['data']['prerequisitos_cadeia']), 12)
            response = self.client.get(f'/api/componentes?db=all&curso={course}&ano=2026&exige_prereq=C00')
            self.assertTrue(response.json()['results_match'], response.text)
            self.assertEqual([c['codigo'] for c in response.json()['data']], ['C01'])
            # Uma falha no meio da gravação precisa reverter as alterações do PostgreSQL.
            bad_doc = copy.deepcopy(doc)
            bad_doc['componentes'][0]['natureza'] = 'INVALIDA'
            with self.assertRaises(Exception):
                REPOSITORIES['postgres'].salvar_estrutura(bad_doc)
            response = self.client.get(f'/api/componentes?db=all&curso={course}&ano=2026')
            self.assertTrue(response.json()['results_match'], response.text)
            self.assertEqual(response.json()['total'], 13)
        finally:
            with DatabaseManager.postgres_connection() as conn, conn.cursor() as cur:
                cur.execute('DELETE FROM curso WHERE sigla = %s', (course,))
            DatabaseManager.mongo_db.componentes.delete_many({'curso': course})
            DatabaseManager.mongo_db.estruturas.delete_many({'curso': course})
            with DatabaseManager.neo4j_driver.session() as session:
                session.run('MATCH (n) WHERE n.curso = $curso OR n.sigla = $curso DETACH DELETE n', curso=course).consume()


if __name__ == '__main__':
    unittest.main()
