"""Utilidades de texto compartilhadas pelos loaders."""
import unicodedata


def normalizar(s: str) -> str:
    """minúsculas e sem acento: 'PROGRAMAÇÃO' -> 'programacao' (para busca por nome)."""
    sem_acento = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in sem_acento if unicodedata.category(c) != "Mn").lower()