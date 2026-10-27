from __future__ import annotations

import sys
from pathlib import Path
import psycopg2
from pymongo import MongoClient
from neo4j import GraphDatabase

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "etl"))

import config  # noqa: E402


class DatabaseManager:
    pg_conn = None
    mongo_client = None
    mongo_db = None
    neo4j_driver = None

    @classmethod
    def connect_all(cls) -> None:
        # 1. PostgreSQL
        pg_cfg = config.postgres()
        cls.pg_conn = psycopg2.connect(**pg_cfg)
        cls.pg_conn.autocommit = True

        # 2. MongoDB
        m_cfg = config.mongo()
        cls.mongo_client = MongoClient(m_cfg["uri"])
        cls.mongo_db = cls.mongo_client[m_cfg["dbname"]]

        # 3. Neo4j
        n_cfg = config.neo4j()
        cls.neo4j_driver = GraphDatabase.driver(
            n_cfg["uri"], auth=(n_cfg["user"], n_cfg["password"])
        )

    @classmethod
    def close_all(cls) -> None:
        if cls.pg_conn:
            cls.pg_conn.close()
        if cls.mongo_client:
            cls.mongo_client.close()
        if cls.neo4j_driver:
            cls.neo4j_driver.close()