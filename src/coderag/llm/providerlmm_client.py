"""Provider abstraction with deterministic fallback answerer."""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from coderag.core.models import ChunkRecord
from coderag.core.settings import SETTINGS
from coderag.core.vertex_auth import build_vertex_request_headers
from coderag.llm.prompts import build_answer_prompt

LOGGER = logging.getLogger(__name__)


class ProviderLlmClient:
    """LLM client abstraction.

    For this end-to-end MVP we keep an extractive local strategy so the system
    works out of the box without external API keys.
    """

    def answer(
        self,
        question: str,
        chunks: List[ChunkRecord],
        context: str | None = None,
        provider: str = "local",
        force_fallback: bool = False,
        strict: bool = False,
        doc_map: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> str:
        """Generate answer grounded in retrieved chunks."""
        provider_name = provider.strip().lower()
        context_block = context or self._context_from_chunks(chunks)

        if force_fallback:
            return self._local_answer(
                question,
                chunks,
                context_block,
                doc_map=doc_map,
            )

        if provider_name == "local":
            return self._local_answer(
                question,
                chunks,
                context_block,
                doc_map=doc_map,
            )

        if not context_block.strip():
            return "No se encontro informacion en las fuentes indexadas."

        if provider_name == "openai":
            output = self._answer_openai(question, context_block)
            if output:
                return output
        elif provider_name == "gemini":
            output = self._answer_gemini(question, context_block)
            if output:
                return output
        elif provider_name in {"vertex", "vertex_ai"}:
            output = self._answer_vertex(question, context_block)
            if output:
                return output
        elif strict:
            raise RuntimeError(
                "Unsupported LLM provider in strict mode: "
                f"{provider_name}"
            )

        if strict:
            raise RuntimeError(
                "LLM provider call failed in strict mode. "
                f"provider={provider_name}"
            )

        return self._local_answer(
            question,
            chunks,
            context_block,
            doc_map=doc_map,
        )

    @staticmethod
    def _resolve_document_name(
        chunk: ChunkRecord,
        doc_map: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> str:
        """Resolve a human-readable document name for citations."""
        doc_map = doc_map or {}
        meta = doc_map.get(chunk.document_id, {})
        path_or_url = str(meta.get("path_or_url") or "").strip()
        filename = ""
        if path_or_url:
            normalized = path_or_url.replace("\\", "/")
            filename = normalized.rsplit("/", 1)[-1].strip()

        title = str(meta.get("title") or "").strip()
        if title:
            if Path(title).suffix:
                return title
            if filename and Path(filename).suffix:
                return filename
            return title

        if filename:
            return filename

        return chunk.document_id

    def _local_answer(
        self,
        question: str,
        chunks: List[ChunkRecord],
        context: str | None = None,
        doc_map: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> str:
        """Return extractive local answer that always works offline."""
        _ = question
        if not chunks:
            return "No se encontro informacion en las fuentes indexadas."

        clean_chunks = [
            chunk for chunk in chunks if chunk.text.strip()
        ]
        if not clean_chunks:
            return "No se encontro informacion en las fuentes indexadas."

        # Keep one high-value finding per document first, then fill by rank.
        findings: List[ChunkRecord] = []
        findings_by_doc: Dict[str, int] = defaultdict(int)
        for chunk in clean_chunks:
            if findings_by_doc[chunk.document_id] >= 1:
                continue
            findings.append(chunk)
            findings_by_doc[chunk.document_id] += 1
            if len(findings) >= 3:
                break

        if len(findings) < 2:
            findings = clean_chunks[:3]

        key_lines: list[str] = []
        for chunk in findings:
            key_lines.append(f"- {chunk.text.strip().replace(chr(10), ' ')[:260]}")

        evidence_lines = []
        for index, chunk in enumerate(clean_chunks[:5], start=1):
            document_name = self._resolve_document_name(chunk, doc_map)
            evidence_lines.append(
                f"- {index}. [{document_name}] {chunk.text.strip()[:220]}"
            )

        graph_lines: list[str] = []
        if context:
            for line in context.splitlines():
                if line.startswith("[GraphPath]"):
                    graph_lines.append(f"- {line[12:].strip()}")
                    if len(graph_lines) >= 3:
                        break

        graph_text = "\n".join(graph_lines) or "- Sin rutas de grafo relevantes."
        evidence_text = "\n".join(evidence_lines)
        findings_text = "\n".join(key_lines)
        covered_docs = len({chunk.document_id for chunk in clean_chunks[:5]})

        response = (
            "## Resumen\n"
            "Basado en la evidencia recuperada, esta es la mejor respuesta "
            "disponible con el contexto indexado.\n\n"
            "## Cobertura\n"
            f"- Documentos considerados en la sintesis local: {covered_docs}.\n\n"
            "## Hallazgos clave\n"
            f"{findings_text}\n\n"
            "## Evidencia\n"
            f"{evidence_text}\n\n"
            "## Relacion de grafo\n"
            f"{graph_text}\n\n"
            "## Limitaciones\n"
            "- Respuesta extractiva local generada sin proveedor remoto."
        )
        return response

    @staticmethod
    def _extract_openai_text(payload: dict) -> str | None:
        """Extract assistant text from OpenAI Responses API payload."""
        direct = payload.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct

        output_items = payload.get("output", [])
        if not isinstance(output_items, list):
            return None

        collected: list[str] = []
        for item in output_items:
            if not isinstance(item, dict):
                continue
            content_items = item.get("content", [])
            if not isinstance(content_items, list):
                continue
            for content in content_items:
                if not isinstance(content, dict):
                    continue
                if content.get("type") != "output_text":
                    continue
                text = content.get("text")
                if isinstance(text, str) and text.strip():
                    collected.append(text)

        if not collected:
            return None
        return "\n".join(collected)

    @staticmethod
    def _context_from_chunks(
        chunks: List[ChunkRecord],
        max_chars: int = 6000,
    ) -> str:
        """Build plain context from top chunks for remote providers."""
        block = "\n\n".join(chunk.text for chunk in chunks[:8])
        return block[:max_chars]

    def _answer_openai(
        self,
        question: str,
        context: str,
    ) -> str | None:
        """Call OpenAI Responses API and return text output."""
        if not SETTINGS.openai_api_key:
            return None

        url = f"{SETTINGS.openai_base_url.rstrip('/')}/responses"
        headers = {
            "Authorization": f"Bearer {SETTINGS.openai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": SETTINGS.openai_answer_model,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "Asistente de RAG corporativo. "
                        "Responde en markdown y solo con evidencia provista."
                    ),
                },
                {
                    "role": "user",
                    "content": build_answer_prompt(question, context),
                },
            ],
        }
        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            return self._extract_openai_text(data)
        except requests.RequestException:
            LOGGER.exception("OpenAI call failed")
            return None

    def _answer_gemini(
        self,
        question: str,
        context: str,
    ) -> str | None:
        """Call Gemini generateContent API with API key."""
        if not SETTINGS.gemini_api_key:
            return None

        model = SETTINGS.gemini_answer_model
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
            f"?key={SETTINGS.gemini_api_key}"
        )
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": build_answer_prompt(question, context)
                        }
                    ],
                }
            ]
        }
        try:
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return None
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                return None
            return parts[0].get("text")
        except requests.RequestException:
            LOGGER.exception("Gemini call failed")
            return None

    def _answer_vertex(
        self,
        question: str,
        context: str,
    ) -> str | None:
        """Call Vertex AI endpoint using service-account OAuth credentials."""
        if not SETTINGS.vertex_project_id:
            return None
        try:
            if not SETTINGS.resolve_vertex_service_account_json():
                return None
        except RuntimeError:
            return None

        model = SETTINGS.vertex_answer_model
        location = SETTINGS.vertex_location
        project_id = SETTINGS.vertex_project_id
        labels = SETTINGS.resolve_vertex_labels(model_name=model)
        url = (
            "https://"
            f"{location}-aiplatform.googleapis.com/v1/projects/{project_id}"
            "/locations/"
            f"{location}/publishers/google/models/{model}:generateContent"
        )
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": build_answer_prompt(question, context)
                        }
                    ],
                }
            ]
        }
        if labels:
            payload["labels"] = labels
        try:
            headers = build_vertex_request_headers(labels)
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return None
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                return None
            return parts[0].get("text")
        except (RuntimeError, requests.RequestException):
            LOGGER.exception("Vertex AI call failed")
            return None
