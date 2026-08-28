import os

import ollama as ol
import requests as req_lib
from dotenv import load_dotenv

load_dotenv()

OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "llama3")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

_client = ol.Client(host=OLLAMA_BASE_URL)

COVEO_ORG   = os.getenv("COVEO_ORGANIZATION_ID", "")
COVEO_TOKEN = os.getenv("COVEO_ACCESS_TOKEN", "")
COVEO_BASE  = f"https://{COVEO_ORG}.org.coveo.com" if COVEO_ORG else "https://platform.cloud.coveo.com"


def _coveo_search(query: str, num_results: int = 5) -> list[dict]:
    """
    Fire a Coveo REST search and return a list of
    {title, excerpt, url} dicts for the top results.
    """
    url  = f"{COVEO_BASE}/rest/search/v2?organizationId={COVEO_ORG}"
    hdrs = {
        "Authorization": f"Bearer {COVEO_TOKEN}",
        "Content-Type":  "application/json",
    }
    body = {
        "q":               query,
        "numberOfResults": num_results,
        "searchHub":       os.getenv("COVEO_SEARCH_HUB", "PokedexUI"),
        "pipeline":        os.getenv("COVEO_PIPELINE", "default"),
        # The Semantic Encoder (Semantic-PokEncoder) runs automatically via the
        # KNN Ranking Function injected by the pipeline — no mlParameters needed.
    }
    resp = req_lib.post(url, json=body, headers=hdrs, timeout=15)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return [
        {
            "title":   r.get("title", ""),
            "excerpt": r.get("excerpt", ""),
            "url":     r.get("clickUri", ""),
        }
        for r in results
    ]


def generate_rga_answer(query: str, context: list[dict]) -> str:
    """
    Given a user query and a list of Coveo result snippets,
    ask Ollama to generate a grounded answer (RGA / RAG style).

    context items: [{"title": str, "excerpt": str}, ...]
    Returns: answer string
    """
    snippets = "\n\n".join(
        f"[{i+1}] {c.get('title', '')}\n{c.get('excerpt', '')}"
        for i, c in enumerate(context[:5])
    )
    prompt = (
        f"You are the Pokédex AI. A trainer asked: \"{query}\"\n\n"
        f"Here are relevant Pokédex entries:\n{snippets}\n\n"
        f"Answer the trainer's question concisely using only the information above. "
        f"Do not make up stats. If you don't know, say so."
    )
    resp = _client.chat(
        model=os.getenv("OLLAMA_MODEL", OLLAMA_MODEL),
        messages=[{"role": "user", "content": prompt}],
    )
    return resp["message"]["content"]


def run_agent(query: str) -> dict:
    """
    Agentic loop. Searches Coveo for relevant Pokémon entries, then uses
    Ollama to generate a grounded answer from those results.
    Returns {message, results} where results are the raw Coveo hits.
    """
    results = _coveo_search(query)

    context = [
        {"title": r["title"], "excerpt": r["excerpt"]}
        for r in results
    ]
    answer = generate_rga_answer(query, context)

    return {"message": answer, "pokemon_list": results}
