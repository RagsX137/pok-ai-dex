"""The one Coveo client.

Search and CRGA streaming previously lived in app.py, agent.py, three probe
scripts and eval_harness/backends.py, in five slightly-divergent copies.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Iterable

import requests

from pokedex.config import Settings, settings as default_settings


@dataclass
class GeneratedAnswer:
    answer: str = ""
    citations: list[dict] = field(default_factory=list)
    stream_id: str | None = None
    answer_generated: bool | None = None
    error: str | None = None


def parse_genqa_stream(lines: Iterable[bytes | str]) -> tuple[str, list[dict], str | None]:
    """Fold an SSE genqa.* stream into (answer, citations, error)."""
    parts: list[str] = []
    citations: list[dict] = []
    for raw in lines:
        if not raw:
            continue
        line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        if not line.startswith("data:"):
            continue
        try:
            event = json.loads(line[len("data:"):].strip())
        except ValueError:
            continue
        if event.get("finishReason") == "ERROR":
            return "".join(parts), citations, event.get("errorMessage", "unknown")
        payload_raw = event.get("payload", "")
        try:
            payload = json.loads(payload_raw) if payload_raw else {}
        except ValueError:
            payload = {}
        ptype = event.get("payloadType", "")
        if ptype == "genqa.messageType":
            delta = payload.get("textDelta", "")
            if delta and delta.strip():
                parts.append(delta)
        elif ptype == "genqa.citationsType":
            citations = payload.get("citations", [])
        elif ptype == "genqa.endOfStreamType" or event.get("finishReason") == "COMPLETED":
            break
    return "".join(parts), citations, None


class CoveoClient:
    """Thin wrapper around the two Coveo REST calls this project makes:
    a plain search and a Relevance Generative Answering (CRGA) round trip.

    `settings` defaults to the module-level `pokedex.config.settings` so
    `CoveoClient()` and `CoveoClient(custom_settings)` are both valid —
    the default keeps call sites terse while remaining injectable for tests.
    """

    def __init__(self, settings: Settings = default_settings):
        self.s = settings

    def search(
        self,
        query: str,
        *,
        num: int = 5,
        first: int = 0,
        extra_body: dict | None = None,
    ) -> dict:
        """POST /rest/search/v2 and return the raw Coveo response body.

        Callers pick `results` / `totalCount` / `extendedResults` themselves.
        """
        url = f"{self.s.coveo_base}/rest/search/v2?organizationId={self.s.coveo_org}"
        hdrs = {
            "Authorization": f"Bearer {self.s.coveo_token}",
            "Content-Type": "application/json",
        }
        body = {
            "q": query,
            "numberOfResults": num,
            "firstResult": first,
            "searchHub": self.s.coveo_search_hub,
            "pipeline": self.s.coveo_pipeline,
        }
        if extra_body:
            body.update(extra_body)
        resp = requests.post(url, json=body, headers=hdrs, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def generated_answer(
        self,
        query: str,
        *,
        num: int = 5,
        attempts: int = 6,
    ) -> GeneratedAnswer:
        """Coveo's Relevance Generative Answering (CRGA / Professor-Oak).

        Flow (matching Coveo Headless GeneratedAnswerAPIClient):
          1. POST /rest/search/v2 with enableGenerativeQuestionAnswering=True
             -> response.extendedResults.generativeQuestionAnsweringId (streamId)
          2. GET /rest/organizations/{org}/machinelearning/streaming/{streamId}
             Accept: */*  -> SSE stream of genqa.* events
          3. Collect textDelta tokens + citations until genqa.endOfStreamType
        """
        hdrs_json = {
            "Authorization": f"Bearer {self.s.coveo_token}",
            "Content-Type": "application/json",
        }

        # ── Step 1: search to obtain the stream ID ────────────────────────
        search_url = f"{self.s.coveo_base}/rest/search/v2?organizationId={self.s.coveo_org}"
        search_body = {
            "q": query,
            "numberOfResults": num,
            "searchHub": self.s.coveo_search_hub,
            "pipeline": self.s.coveo_rga_pipeline,
            "enableGenerativeQuestionAnswering": True,
        }

        stream_id = None
        for _attempt in range(attempts):
            r_search = requests.post(search_url, json=search_body, headers=hdrs_json, timeout=15)
            if r_search.status_code != 200:
                msg = f"Coveo search error: {r_search.status_code}"
                return GeneratedAnswer(
                    answer=f"({msg})", citations=[], stream_id=None,
                    answer_generated=None, error=msg,
                )
            search_data = r_search.json()
            stream_id = search_data.get("extendedResults", {}).get("generativeQuestionAnsweringId")
            if stream_id:
                break
            time.sleep(1)

        if not stream_id:
            # No RGA model fired within the retry budget. The caller (the
            # /api/rga-coveo route) builds the "top search excerpts" fallback
            # text — that is an HTTP-response concern, not this client's job.
            return GeneratedAnswer(
                answer="", citations=[], stream_id=None,
                answer_generated=False, error=None,
            )

        # ── Step 2: consume the SSE stream ─────────────────────────────────
        stream_url = (
            f"{self.s.coveo_base}/rest/organizations/{self.s.coveo_org}"
            f"/machinelearning/streaming/{stream_id}"
        )
        hdrs_sse = {
            "Authorization": f"Bearer {self.s.coveo_token}",
            "Accept": "*/*",
        }

        try:
            r_stream = requests.get(stream_url, headers=hdrs_sse, timeout=45, stream=True)
        except requests.RequestException as exc:
            msg = f"Stream request failed: {exc}"
            return GeneratedAnswer(
                answer=f"({msg})", citations=[], stream_id=stream_id,
                answer_generated=None, error=msg,
            )

        if r_stream.status_code != 200:
            msg = f"CRGA stream error: {r_stream.status_code}"
            return GeneratedAnswer(
                answer=f"({msg})", citations=[], stream_id=stream_id,
                answer_generated=None, error=msg,
            )

        # ── Step 3: parse SSE events ────────────────────────────────────────
        answer_text, citations, stream_error = parse_genqa_stream(r_stream.iter_lines())
        if stream_error is not None:
            msg = f"CRGA error: {stream_error}"
            return GeneratedAnswer(
                answer=f"({msg})", citations=[], stream_id=stream_id,
                answer_generated=None, error=stream_error,
            )

        answer = answer_text.strip() or "(no answer generated)"
        return GeneratedAnswer(
            answer=answer, citations=citations, stream_id=stream_id,
            answer_generated=True, error=None,
        )
