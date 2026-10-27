from __future__ import annotations

from backend.repositories.base import CurriculoRepository
from backend.repositories.postgres_repo import PostgresRepository
from backend.repositories.mongo_repo import MongoRepository
from backend.repositories.neo4j_repo import Neo4jRepository

REPOSITORIES: dict[str, CurriculoRepository] = {
    "postgres": PostgresRepository(),
    "mongo": MongoRepository(),
    "neo4j": Neo4jRepository(),
}


def get_repository(db_name: str) -> CurriculoRepository:
    repo = REPOSITORIES.get(db_name.lower())
    if not repo:
        raise ValueError(f"Banco '{db_name}' não suportado. Opções: {list(REPOSITORIES.keys())}")
    return repo