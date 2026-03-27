"""Prompt templates for grounded answering and verification."""

from __future__ import annotations


def build_answer_prompt(question: str, context: str) -> str:
    """Build grounded answer prompt with anti-hallucination policy."""
    return (
        "Responde solo con evidencia del contexto. "
        "No inventes datos ni supongas informacion ausente. "
        "Si no hay evidencia suficiente, responde exactamente: "
        "No se encontro informacion en las fuentes indexadas.\n\n"
        "Si hay evidencia, usa markdown con estas secciones en este orden:\n"
        "## Resumen\n"
        "## Hallazgos clave\n"
        "## Evidencia\n"
        "## Relacion de grafo\n"
        "## Limitaciones\n\n"
        f"Pregunta:\n{question}\n\n"
        f"Contexto:\n{context}\n"
    )
