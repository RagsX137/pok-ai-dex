import json
import os

import ollama as ol

OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "llama3")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

_client = ol.Client(host=OLLAMA_BASE_URL)


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
    Agentic tool-calling loop. Uses Ollama's tool-call API with three
    Pokédex tools, then returns {message, pokemon_list}.
    """
    from pokedex_tools import look_up_by_type, look_up_by_generation, get_pokemon_detail

    tools = [
        {
            "type": "function",
            "function": {
                "name": "look_up_by_type",
                "description": "Find Pokémon by elemental type",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "description": "Pokémon type e.g. fire, water"},
                        "limit": {"type": "integer", "default": 20},
                    },
                    "required": ["type"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "look_up_by_generation",
                "description": "Find Pokémon by game generation (1–9)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "generation": {"type": "integer"},
                        "limit": {"type": "integer", "default": 20},
                    },
                    "required": ["generation"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_pokemon_detail",
                "description": "Get full details for a single named Pokémon",
                "parameters": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            },
        },
    ]

    messages = [{"role": "user", "content": query}]
    resp = _client.chat(
        model=os.getenv("OLLAMA_MODEL", OLLAMA_MODEL),
        messages=messages,
        tools=tools,
    )

    pokemon_list = []
    message = resp["message"]

    if message.get("tool_calls"):
        for call in message["tool_calls"]:
            fn   = call["function"]["name"]
            args = call["function"]["arguments"]
            if fn == "look_up_by_type":
                pokemon_list = look_up_by_type(**args)
            elif fn == "look_up_by_generation":
                pokemon_list = look_up_by_generation(**args)
            elif fn == "get_pokemon_detail":
                result = get_pokemon_detail(**args)
                pokemon_list = [result] if result else []

        messages.append(message)
        messages.append({
            "role": "tool",
            "content": json.dumps(pokemon_list),
        })
        final = _client.chat(
            model=os.getenv("OLLAMA_MODEL", OLLAMA_MODEL),
            messages=messages,
        )
        prose = final["message"]["content"]
    else:
        prose = message.get("content", "")

    return {"message": prose, "pokemon_list": pokemon_list}
