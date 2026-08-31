"""The one Coveo client.

Search and CRGA streaming previously lived in app.py, agent.py, three probe
scripts and eval_harness/backends.py, in five slightly-divergent copies.
"""
from __future__ import annotations

import html
import json
import re
import time
from dataclasses import dataclass, field
from typing import Iterable

import requests

from pokedex.config import Settings, settings as default_settings


@dataclass(frozen=True)
class Passage:
    """One item from the Passage Retrieval API.

    `text` is markdown, not a sentence: the API returns page-sized chunks,
    several of which usually belong to the same document. Callers either slice
    sections out of it (FactsStore) or run it through `clean_passage_text`
    (the dashboard's evidence panel) — never feed it to a model whole.

    `uri` and `primary_id` are both optional because the two identifiers come
    from different `additionalFields` requests: asking for one does not return
    the other.
    """
    text: str
    score: float
    title: str
    uri: str = ""
    primary_id: str = ""


@dataclass
class GeneratedAnswer:
    answer: str = ""
    citations: list[dict] = field(default_factory=list)
    stream_id: str | None = None
    # True  = SSE stream reached a clean COMPLETED end.
    # False = the search retry loop exhausted all attempts with no stream ID
    #         (the RGA model never fired — NOT the same as Coveo's own
    #         answerGenerated=false abstention flag, which signals retrieval
    #         was too weak to generate a grounded answer).
    # None  = the flow aborted due to a hard transport/HTTP error before a
    #         clean determination could be made either way.
    # DO NOT use this field as a proxy for Coveo's answerGenerated abstention
    # signal; DirectCoveoClient in eval_harness/backends.py extracts that flag
    # from the genqa.endOfStreamType payload directly and is the authoritative
    # source for "did Coveo choose not to answer?"
    stream_completed: bool | None = None
    error: str | None = None


# The corpus is markdown scraped from pokemondb.net, so a passage is as likely
# to be a slice of a moves table or the page's nav list as it is to be prose.
# The cleaner works on the markdown's own structure rather than on flattened
# text: lines separate content from chrome, and "|" separates a table's short
# label cells from the long prose cells that Pokedex flavour entries live in
# ("| Shield | It is said to emerge from darkness... |"). Flattening first
# destroys exactly the boundary needed to tell those apart.
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")   # [Electric](/type/electric) -> Electric
_MD_EMPHASIS = re.compile(r"\*{1,3}([^*]+)\*{1,3}")  # *Pikachu* -> Pikachu
_WHITESPACE = re.compile(r"\s+")
_WORD = re.compile(r"[A-Za-z']+")

# A line of nothing but pipes, dashes and colons is a table's separator row.
_TABLE_RULE = re.compile(r"^[\s|:\-]+$")

# Headings ("## Base stats") and list items ("- [Info](#dex-basics)") are page
# furniture. Dropping list items also excludes the site's related-questions
# lists, which are genuinely prose-shaped and so survive every text-based test.
_FURNITURE_PREFIXES = ("#", "- ", "* ", "-[", "*[")

# Under this many words a cell is a label or a stat, not a sentence.
_MIN_CELL_TOKENS = 6

# Function words separate prose from a flattened table row: measured over live
# passages, real sentences run 37-48% function words and table rows 0-17%.
_FUNCTION_WORDS = frozenset("""
a an and are as at be been but by can for from had has have he her his in into
is it its me my not of on or she that the their them then there these they
this those to was were what when where which who will with you your
""".split())
_MIN_FUNCTION_WORD_RATIO = 0.20

# Site furniture that is genuinely prose and so passes every shape test, but
# is byte-identical on every Pokemon's page and says nothing about the one
# being asked about. It otherwise ranks second for most queries.
_BOILERPLATE_SENTENCES = ("the ranges shown on the right are for a level",)

# Below this many letters there is nothing worth showing regardless of shape.
_MIN_LETTERS = 40


def _is_prose(cell: str) -> bool:
    """True when a table cell or line reads as English, not as a stat or label."""
    tokens = _WORD.findall(cell.lower())
    if len(tokens) < _MIN_CELL_TOKENS:
        return False
    function_words = sum(1 for t in tokens if t in _FUNCTION_WORDS)
    return function_words / len(tokens) >= _MIN_FUNCTION_WORD_RATIO


def clean_passage_text(raw: str) -> str:
    """Render a raw CPR passage as plain prose, or "" if it is only markup.

    Returning "" rather than a best-effort string is deliberate: the caller
    filters on it, and half-parsed table rows in the dashboard's
    recommendation card read as a rendering bug.
    """
    if not raw:
        return ""

    kept: list[str] = []
    for line in html.unescape(raw).split("\n"):
        stripped = line.strip()
        if not stripped or _TABLE_RULE.match(stripped):
            continue
        if stripped.startswith(_FURNITURE_PREFIXES):
            continue
        for cell in stripped.split("|"):
            cell = _MD_EMPHASIS.sub(r"\1", _MD_LINK.sub(r"\1", cell))
            cell = _WHITESPACE.sub(" ", cell).strip()
            if any(b in cell.lower() for b in _BOILERPLATE_SENTENCES):
                continue
            if _is_prose(cell):
                kept.append(cell)

    out = " ".join(kept).strip()
    if sum(c.isalpha() for c in out) < _MIN_LETTERS:
        return ""
    return out


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


    def retrieve_passages(
        self,
        query: str,
        *,
        max_passages: int = 5,
        timeout: int = 20,
        clean: bool = True,
    ) -> list[Passage]:
        """POST /rest/search/v3/passages/retrieve — Coveo Passage Retrieval.

        A separate API from `search`, not a flag on it, and it requires a CPR
        model *and* a Semantic Encoder model on the pipeline the request
        resolves to. It also insists the body's searchHub match the one bound
        to the API key, hence `coveo_passage_hub`.

        Never raises. Every failure — no CPR model on the pipeline (422), the
        5 calls/s org quota (429), a hub mismatch (400), a timeout — returns
        an empty list. Both callers are supplementary: the dashboard's
        evidence panel must not break the page it decorates, and Coach falls
        through to CRGA when no facts come back.

        `clean=False` returns the API's text verbatim and keeps every item.
        Cleaning drops headings and short table cells, which is right for the
        panel's prose card and fatal for FactsStore: '## Training' and
        '| Egg Groups | Grass, Monster |' are exactly what it slices on. The
        junk filter goes with it, because a chunk that is only a moves table
        cleans to '' yet is precisely what a moves question needs.
        """
        if not query or not query.strip():
            return []

        url = f"{self.s.coveo_base}/rest/search/v3/passages/retrieve"
        hdrs = {
            "Authorization": f"Bearer {self.s.coveo_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        body = {
            "query": query.strip(),
            "searchHub": self.s.coveo_passage_hub,
            "localization": {"locale": "en-US", "timezone": "America/New_York"},
            "maxPassages": max_passages,
            "additionalFields": ["title", "uri"],
        }

        try:
            resp = requests.post(url, json=body, headers=hdrs, timeout=timeout)
        except requests.RequestException:
            return []
        if resp.status_code != 200:
            return []
        try:
            data = resp.json()
        except ValueError:
            return []

        passages: list[Passage] = []
        for item in data.get("items") or []:
            raw = item.get("text") or ""
            text = clean_passage_text(raw) if clean else raw
            if clean and not text:
                continue
            doc = item.get("document") or {}
            passages.append(
                Passage(
                    text=text,
                    score=float(item.get("relevanceScore") or 0.0),
                    title=doc.get("title") or "",
                    uri=doc.get("uri") or "",
                )
            )
        return passages

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
                    stream_completed=None, error=msg,
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
                stream_completed=False, error=None,
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
                stream_completed=None, error=msg,
            )

        if r_stream.status_code != 200:
            msg = f"CRGA stream error: {r_stream.status_code}"
            return GeneratedAnswer(
                answer=f"({msg})", citations=[], stream_id=stream_id,
                stream_completed=None, error=msg,
            )

        # ── Step 3: parse SSE events ────────────────────────────────────────
        answer_text, citations, stream_error = parse_genqa_stream(r_stream.iter_lines())
        if stream_error is not None:
            msg = f"CRGA error: {stream_error}"
            return GeneratedAnswer(
                answer=f"({msg})", citations=[], stream_id=stream_id,
                stream_completed=None, error=stream_error,
            )

        answer = answer_text.strip() or "(no answer generated)"
        return GeneratedAnswer(
            answer=answer, citations=citations, stream_id=stream_id,
            stream_completed=True, error=None,
        )
