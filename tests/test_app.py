import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend.main import app
from backend.database import DatabaseManager
from backend.repositories import REPOSITORIES
import load_postgres

ROOT = Path(__file__).resolve().parents[1]
DOC = json.loads((ROOT / 'data/processed/tads_2019.json').read_text(encoding='utf-8'))


class ValidationTests(unittest.TestCase):
    def test_real_matrices(self):
        for path in (ROOT / 'data/processed').glob('*.json'):
            self.assertEqual(load_postgres.validar(json.loads(path.read_text(encoding='utf-8'))), [])

    def test_malformed_shapes(self):
        for invalid in [None, [], {}, {'curso': []}, {**DOC, 'componentes': [None]},
                        {**DOC, 'relacoes': [True]}, {**DOC, 'estrutura': {'ano': True}},
                        {**DOC, 'curso': {'sigla': [], 'nome': 'Teste'}}]:
            with self.subTest(invalid=invalid):
                self.assertTrue(load_postgres.validar(invalid))
        for field, value in [('codigo', []), ('natureza', {}), ('carga', -1), ('periodo', '2')]:
            doc = copy.deepcopy(DOC)
            doc['componentes'][0][field] = value
            self.assertTrue(load_postgres.validar(doc))

    def test_cycles_duplicates_missing_references(self):
        for relations in [
            [{'origem': 'TAD0001', 'destino': 'TAD0102'}, {'origem': 'TAD0102', 'destino': 'TAD0001'}],
            [{'origem': 'MISSING', 'destino': 'TAD0001'}],
            [DOC['relacoes'][0], DOC['relacoes'][0]],
        ]:
            doc = copy.deepcopy(DOC); doc['relacoes'] = relations
            self.assertTrue(load_postgres.validar(doc))


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_frontend_and_assets(self):
        for path in ['/', '/assets/styles.css', '/assets/app.js', '/assets/favicon.svg']:
            self.assertEqual(self.client.get(path).status_code, 200)

    def test_invalid_payload_and_queries(self):
        for payload in [{}, {**DOC, 'componentes': [None]}, {**DOC, 'relacoes': [1]}]:
            self.assertEqual(self.client.post('/api/estruturas', json=payload).status_code, 422)
        for query in ['db=missing', 'periodo=0', 'natureza=missing', 'ano=wrong']:
            self.assertEqual(self.client.get('/api/componentes?' + query).status_code, 422)

    def test_unavailable_database_is_503(self):
        with patch.object(DatabaseManager, 'status', {}):
            self.assertEqual(self.client.get('/api/componentes').status_code, 503)
            self.assertEqual(self.client.post('/api/estruturas', json=DOC).status_code, 503)

    def test_compare_preserves_each_result(self):
        with patch.object(DatabaseManager, 'status', dict.fromkeys(REPOSITORIES, True)):
            with patch.object(REPOSITORIES['postgres'], 'buscar_componentes', return_value=[{'codigo': 'A'}]), \
                 patch.object(REPOSITORIES['mongo'], 'buscar_componentes', return_value=[]), \
                 patch.object(REPOSITORIES['neo4j'], 'buscar_componentes', return_value=[{'codigo': 'B'}]):
                response = self.client.get('/api/componentes?db=all').json()
                self.assertFalse(response['results_match'])
                self.assertEqual(response['data'], [{'codigo': 'A'}])
                self.assertEqual(response['results_by_database']['neo4j'], [{'codigo': 'B'}])


if __name__ == '__main__':
    unittest.main()
