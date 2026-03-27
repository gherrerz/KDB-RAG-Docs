"""Provider abstraction with deterministic fallback answerer."""

from __future__ import annotations

import logging
from typing import List

import requests

from coderag.core.models import ChunkRecord
from coderag.core.settings import SETTINGS

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
        provider: str = "local",
        force_fallback: bool = False,
    ) -> str:
        """Generate answer grounded in retrieved chunks."""
        provider_name = provider.strip().lower()
        if force_fallback:
            return self._local_answer(question, chunks)

        if provider_name == "openai":
            output = self._answer_openai(question, chunks)
            if output:
                return output
        elif provider_name == "gemini":
            output = self._answer_gemini(question, chunks)
            if output:
                return output
        elif provider_name in {"vertex", "vertex_ai"}:
            output = self._answer_vertex(question, chunks)
            if output:
                return output

        return self._local_answer(question, chunks)

    def _local_answer(self, question: str, chunks: List[ChunkRecord]) -> str:
        """Return extractive local answer that always works offline."""
        _ = question
        if not chunks:
            return "No se encontro informacion en las fuentes indexadas."

        top = chunks[0]
        snippet = top.text.strip().replace("\n", " ")
        if not snippet:
            return "No se encontro informacion en las fuentes indexadas."

        response = (
            "Basado en la evidencia recuperada: "
            f"{snippet[:500]}"
        )
        return response

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
        chunks: List[ChunkRecord],
    ) -> str | None:
        """Call OpenAI Responses API and return text output."""
        if not SETTINGS.openai_api_key:
            return None
        context = self._context_from_chunks(chunks)
        if not context.strip():
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
                        "Responde solo con evidencia del contexto. "
                        "Si no hay evidencia suficiente, responde: "
                        "No se encontro informacion en las fuentes indexadas."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Pregunta:\n{question}\n\n"
                        f"Contexto:\n{context}"
                    ),
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
            return data.get("output_text")
        except requests.RequestException:
            LOGGER.exception("OpenAI call failed")
            return None

    def _answer_gemini(
        self,
        question: str,
        chunks: List[ChunkRecord],
    ) -> str | None:
        """Call Gemini generateContent API with API key."""
        if not SETTINGS.gemini_api_key:
            return None
        context = self._context_from_chunks(chunks)
        if not context.strip():
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
                            "text": (
                                "Responde solo con evidencia del contexto. "
                                "Si no hay evidencia suficiente, responde: "
                                "No se encontro informacion en las fuentes "
                                "indexadas.\n\n"
                                f"Pregunta:\n{question}\n\n"
                                f"Contexto:\n{context}"
                            )
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
        chunks: List[ChunkRecord],
    ) -> str | None:
        """Call Vertex AI endpoint with API key when configured."""
        if (
            not SETTINGS.vertex_ai_api_key
            or not SETTINGS.vertex_project_id
        ):
            return None
        context = self._context_from_chunks(chunks)
        if not context.strip():
            return None

        model = SETTINGS.vertex_answer_model
        location = SETTINGS.vertex_location
        project_id = SETTINGS.vertex_project_id
        url = (
            "https://"
            f"{location}-aiplatform.googleapis.com/v1/projects/{project_id}"
            "/locations/"
            f"{location}/publishers/google/models/{model}:generateContent"
            f"?key={SETTINGS.vertex_ai_api_key}"
        )
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                "Responde solo con evidencia del contexto. "
                                "Si no hay evidencia suficiente, responde: "
                                "No se encontro informacion en las fuentes "
                                "indexadas.\n\n"
                                f"Pregunta:\n{question}\n\n"
                                f"Contexto:\n{context}"
                            )
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
            LOGGER.exception("Vertex AI call failed")
            return None
