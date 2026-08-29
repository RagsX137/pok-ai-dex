"""
The systems under test.

`app-coveo` and `app-ollama:*` go through the running Flask app, so they see
exactly what a trainer in the browser sees. `direct-coveo` replays the same
CRGA flow straight against Coveo in order to capture telemetry the app
currently discards - most importantly the `answerGenerated` abstention flag.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field

import requests


@dataclass
class TurnResult:
    backend: str
    answer: str = ""
    citations: list[dict] = field(default_factory=list)
    search_titles: list[str] = field(default_factory=list)
    total_hits: int | None = None
    latency_ms: int = 0
    # None when the backend cannot report it (the app does not surface it today)
    answer_generated: bool | None = None
    error: str | None = None
    raw: dict = field(default_factory=dict)


class AppClient:
    """Talks to the Flask app under test."""

    def __init__(self, base_url: str, timeout: int = 180):
        self.base = base_url.rstrip("/")
        self.timeout = timeout

    def health(self) -> bool:
        try:
            return requests.get(self.base + "/", timeout=10).status_code == 200
        except requests.RequestException:
            return False

    def search(self, query: str, num: int = 5, first: int = 0) -> list[dict]:
        r = requests.post(
            f"{self.base}/api/coveo-proxy",
            json={
                "method": "POST",
                "path": "/rest/search/v2",
                "body": {
                    "q": query,
                    "numberOfResults": num,
                    "firstResult": first,
                    "searchHub": os.getenv("COVEO_SEARCH_HUB", "PokedexUI"),
                    "pipeline": os.getenv("COVEO_PIPELINE", "default"),
                },
            },
            timeout=60,
        )
        r.raise_for_status()
        return r.json().get("results", [])

    def search_full(self, query: str, num: int = 5) -> tuple[list[dict], int | None]:
        r = requests.post(
            f"{self.base}/api/coveo-proxy",
            json={
                "method": "POST",
                "path": "/rest/search/v2",
                "body": {
                    "q": query,
                    "numberOfResults": num,
                    "searchHub": os.getenv("COVEO_SEARCH_HUB", "PokedexUI"),
                    "pipeline": os.getenv("COVEO_PIPELINE", "default"),
                },
            },
            timeout=60,
        )
        r.raise_for_status()
        d = r.json()
        return d.get("results", []), d.get("totalCount")

    # ── backends ─────────────────────────────────────────────────────────────
    def ask_coveo(self, query: str) -> TurnResult:
        """The UI default: 'Professor-Oak (Coveo)'."""
        res = TurnResult(backend="app-coveo")
        results, total = self._safe_search(res, query)
        t0 = time.time()
        try:
            r = requests.post(
                f"{self.base}/api/rga-coveo", json={"query": query}, timeout=self.timeout
            )
            res.latency_ms = int((time.time() - t0) * 1000)
            if r.status_code != 200:
                res.error = f"HTTP {r.status_code}"
                return res
            d = r.json()
            res.answer = d.get("answer", "")
            res.citations = d.get("citations", [])
            res.raw = d
        except requests.RequestException as exc:
            res.latency_ms = int((time.time() - t0) * 1000)
            res.error = f"{type(exc).__name__}: {exc}"
        return res

    def ask_ollama(self, query: str, model: str) -> TurnResult:
        """The UI's local-model path: top-5 search excerpts as RAG context."""
        res = TurnResult(backend=f"app-ollama:{model}")
        results, total = self._safe_search(res, query)
        context = [
            {"title": r.get("title", ""), "excerpt": r.get("excerpt", "")}
            for r in results[:5]
        ]
        t0 = time.time()
        try:
            requests.post(
                f"{self.base}/api/set-model", json={"model": model}, timeout=15
            )
            r = requests.post(
                f"{self.base}/api/rga",
                json={"query": query, "context": context},
                timeout=self.timeout,
            )
            res.latency_ms = int((time.time() - t0) * 1000)
            if r.status_code != 200:
                # The app returns a Werkzeug HTML debugger page on failure.
                res.error = f"HTTP {r.status_code}: {_first_line(r.text)}"
                return res
            d = r.json()
            res.answer = d.get("answer", "")
            res.raw = d
        except requests.RequestException as exc:
            res.latency_ms = int((time.time() - t0) * 1000)
            res.error = f"{type(exc).__name__}: {exc}"
        return res

    def _safe_search(self, res: TurnResult, query: str):
        try:
            results, total = self.search_full(query)
            res.search_titles = [r.get("title", "") for r in results]
            res.total_hits = total
            return results, total
        except requests.RequestException as exc:
            res.error = f"search failed: {exc}"
            return [], None


class DirectCoveoClient:
    """
    Replays app.py's CRGA flow against Coveo directly.

    Exists purely to capture what the app throws away: the `answerGenerated`
    flag on genqa.endOfStreamType, which distinguishes 'the model abstained
    because retrieval was too weak' from 'something broke'.
    """

    def __init__(self, org: str, token: str, timeout: int = 60):
        self.org = org
        self.token = token
        self.base = f"https://{org}.org.coveo.com" if org else "https://platform.cloud.coveo.com"
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.org and self.token)

    def ask(self, query: str, attempts: int = 6) -> TurnResult:
        res = TurnResult(backend="direct-coveo")
        hdrs = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        body = {
            "q": query,
            "numberOfResults": 5,
            "searchHub": os.getenv("COVEO_SEARCH_HUB", "PokedexUI"),
            "pipeline": os.getenv("COVEO_RGA_PIPELINE", os.getenv("COVEO_PIPELINE", "default")),
            "enableGenerativeQuestionAnswering": True,
        }
        t0 = time.time()
        stream_id = None
        try:
            for _ in range(attempts):
                r = requests.post(
                    f"{self.base}/rest/search/v2?organizationId={self.org}",
                    json=body, headers=hdrs, timeout=20,
                )
                if r.status_code != 200:
                    res.error = f"search HTTP {r.status_code}"
                    return res
                d = r.json()
                res.search_titles = [x.get("title", "") for x in d.get("results", [])]
                res.total_hits = d.get("totalCount")
                stream_id = d.get("extendedResults", {}).get("generativeQuestionAnsweringId")
                if stream_id:
                    break
                time.sleep(1)

            if not stream_id:
                res.answer_generated = False
                res.error = "no generativeQuestionAnsweringId (RGA did not trigger)"
                res.latency_ms = int((time.time() - t0) * 1000)
                return res

            events, parts, cits, generated = [], [], [], None
            rs = requests.get(
                f"{self.base}/rest/organizations/{self.org}/machinelearning/streaming/{stream_id}",
                headers={"Authorization": f"Bearer {self.token}", "Accept": "*/*"},
                timeout=self.timeout, stream=True,
            )
            if rs.status_code != 200:
                res.error = f"stream HTTP {rs.status_code}"
                res.latency_ms = int((time.time() - t0) * 1000)
                return res

            for raw_line in rs.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
                if not line.startswith("data:"):
                    continue
                try:
                    ev = json.loads(line[5:].strip())
                except ValueError:
                    continue
                ptype = ev.get("payloadType", "")
                try:
                    payload = json.loads(ev.get("payload", "") or "{}")
                except ValueError:
                    payload = {}
                events.append({"payloadType": ptype, "finishReason": ev.get("finishReason")})

                if ev.get("finishReason") == "ERROR":
                    res.error = f"CRGA error: {ev.get('errorMessage', 'unknown')}"
                    break
                if ptype == "genqa.messageType":
                    delta = payload.get("textDelta", "")
                    if delta and delta.strip():
                        parts.append(delta)
                elif ptype == "genqa.citationsType":
                    cits = payload.get("citations", [])
                elif ptype == "genqa.endOfStreamType":
                    generated = payload.get("answerGenerated")
                    break

            res.answer = "".join(parts).strip()
            res.citations = cits
            res.answer_generated = generated if generated is not None else bool(parts)
            res.raw = {"stream_id": stream_id, "events": events}
        except requests.RequestException as exc:
            res.error = f"{type(exc).__name__}: {exc}"
        res.latency_ms = int((time.time() - t0) * 1000)
        return res


def _first_line(text: str) -> str:
    for ln in text.splitlines():
        ln = ln.strip()
        if ln and "<" not in ln:
            return ln[:200]
    return text[:120].replace("\n", " ")
