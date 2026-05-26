"""Presenter helpers for query UI validation and payload building."""

from __future__ import annotations


class QueryPresenter:
    """Encapsula validaciones y payload de consultas de la UI."""

    @staticmethod
    def safe_int(raw: str) -> int | None:
        """Parse integer safely from user-provided text input."""
        try:
            return int(raw)
        except ValueError:
            return None

    def validate_inputs(self, *, question: str, hops_raw: str) -> tuple[str | None, set[str]]:
        """Validate query form fields and return message plus invalid keys."""
        if not question.strip():
            return "La pregunta es obligatoria.", {"question"}

        parsed_hops = self.safe_int(hops_raw.strip())
        is_invalid_hops = parsed_hops is None or parsed_hops < 1 or parsed_hops > 6
        if is_invalid_hops:
            return "Los saltos de grafo deben ser un entero entre 1 y 6.", {"hops"}
        return None, set()

    def build_payload(
        self,
        *,
        question: str,
        source_id: str,
        document_ids: list[str],
        hops_raw: str,
        include_llm_answer: bool,
    ) -> dict[str, object]:
        """Build normalized query payload for backend invocation."""
        hops = self.safe_int(hops_raw.strip())
        return {
            "question": question.strip(),
            "source_id": source_id.strip() or None,
            "document_ids": document_ids,
            "hops": hops,
            "include_llm_answer": include_llm_answer,
        }

    @staticmethod
    def build_actionable_error(result: dict) -> str:
        """Compose a readable, actionable error message for failed queries."""
        detail = str(result.get("detail") or result.get("error") or "").strip()
        if not detail:
            detail = "La consulta no pudo completarse por un error desconocido."
        return (
            "La consulta fallo.\n"
            f"Detalle: {detail}\n"
            "Accion sugerida: verifica API activa, parametros de entrada y estado de indices."
        )