from __future__ import annotations

import sys
import logging
from contextlib import contextmanager
from pathlib import Path
from psycopg2.pool import ThreadedConnectionPool
from pymongo import MongoClient
from neo4j import GraphDatabase

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "etl"))

import config  # noqa: E402


class DatabaseManager:
    pg_pool = None
    mongo_client = None
    mongo_db = None
    neo4j_driver = None
    status = {}

    @classmethod
    def connect_all(cls) -> None:
        cls.close_all()
        for name in ("postgres", "mongo", "neo4j"):
            try:
                if name == "postgres":
                    cls.pg_pool = ThreadedConnectionPool(1, 16, **config.postgres(), connect_timeout=3)
                elif name == "mongo":
                    cfg = config.mongo()
                    cls.mongo_client = MongoClient(cfg["uri"], serverSelectionTimeoutMS=3000)
                    cls.mongo_client.admin.command("ping")
                    cls.mongo_db = cls.mongo_client[cfg["dbname"]]
                else:
                    cfg = config.neo4j()
                    cls.neo4j_driver = GraphDatabase.driver(
                        cfg["uri"], auth=(cfg["user"], cfg["password"]),
                        connection_timeout=3, max_transaction_retry_time=3,
                    )
                    cls.neo4j_driver.verify_connectivity()
                cls.status[name] = True
            except Exception:
                logging.getLogger(__name__).warning("Banco %s indisponível na inicialização", name)
                cls.status[name] = False

    @classmethod
    @contextmanager
    def postgres_connection(cls):
        conn = cls.pg_pool.getconn()
        try:
            with conn:
                yield conn
        finally:
            cls.pg_pool.putconn(conn)

    @classmethod
    def close_all(cls) -> None:
        if cls.pg_pool:
            cls.pg_pool.closeall()
        if cls.mongo_client:
            cls.mongo_client.close()
        if cls.neo4j_driver:
            cls.neo4j_driver.close()
        cls.pg_pool = cls.mongo_client = cls.mongo_db = cls.neo4j_driver = None
        cls.status = {}
