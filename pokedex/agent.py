import os

import ollama as ol
from dotenv import load_dotenv

from pokedex.config import settings
from pokedex.coveo import CoveoClient

load_dotenv()

OLLAMA_MODEL    = settings.ollama_model
OLLAMA_BASE_URL = settings.ollama_base_url

_client = ol.Client(host=OLLAMA_BASE_URL)


def _coveo_search(query: str, num_results: int = 5) -> list[dict]:
    """
    Fire a Coveo REST search and return a list of
    {title, excerpt, url} dicts for the top results.
    """
    # The Semantic Encoder (Semantic-PokEncoder) runs automatically via the
    # KNN Ranking Function injected by the pipeline — no mlParameters needed.
    results = CoveoClient().search(query, num=num_results)["results"]
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
