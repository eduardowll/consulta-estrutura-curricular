from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class CurriculoRepository(ABC):
    """Interface base (Strategy) para operações em qualquer banco de dados."""

    @abstractmethod
    def listar_estruturas(self) -> list[dict[str, Any]]:
        """Retorna todos os cursos e estruturas curriculares cadastrados."""
        pass

    @abstractmethod
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
        """Busca componentes curriculares aplicando filtros combinados."""
        pass

    @abstractmethod
    def buscar_cadeia(self, curso: str, ano: int, codigo: str) -> dict[str, Any]:
        """Retorna a cadeia recursiva de pré-requisitos e dependentes (o que ela libera)."""
        pass

    @abstractmethod
    def salvar_estrutura(self, doc: dict[str, Any]) -> None:
        """Persiste uma nova estrutura curricular a partir do JSON canónico ."""
        pass