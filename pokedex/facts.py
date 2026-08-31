"""PokemonDB page markdown -> structured facts -> rendered prose.

Pure by design: no network, no disk, and no imports from the rest of the
project. Everything here is a function of the text handed to it, so the whole
module is testable against a captured passage with no server running — which is
what `make test-unit` guarantees.

The input is a raw Coveo passage (`retrieve_passages(..., clean=False)`), i.e.
markdown scraped from pokemondb.net. `clean_passage_text` in coveo.py is the
opposite transformation: it keeps prose and throws away headings and short
table cells. This module needs exactly what that one discards.

Answers are rendered from the parsed dataclass rather than generated, the way
eval_harness/reference.py renders off the type chart. An ability name is a
fact; passing it through a model to be restated only adds a way to get it
wrong, and another thing for coach_api's grader to have to catch.
"""
from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass, field, asdict

# [Overgrow](/ability/overgrow) -> Overgrow
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MD_EMPHASIS = re.compile(r"\*{1,3}([^*]+)\*{1,3}")
_WHITESPACE = re.compile(r"\s+")
# A line of nothing but pipes, dashes and colons is a table separator row.
_TABLE_RULE = re.compile(r"^[\s|:\-]+$")
_HEADING = re.compile(r"^(#{2,3})\s+(.+?)\s*$", re.M)

# Pokedex pages spell it "Pokédex". Matching on "pokedex" without folding the
# accent silently finds nothing — this cost a full round of false negatives
# while probing section coverage.
def fold(text: str) -> str:
    """Lowercase and strip accents, so 'Pokédex' matches 'pokedex'."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def strip_markup(text: str) -> str:
    """Unwrap markdown links and emphasis, unescape entities, collapse spaces."""
    out = html.unescape(text or "")
    out = _MD_LINK.sub(r"\1", out)
    out = _MD_EMPHASIS.sub(r"\1", out)
    out = _WHITESPACE.sub(" ", out)
    # Link-separated lists arrive as "Grass , Monster": the space belonged to
    # the markup that was just removed, not to the sentence.
    return re.sub(r"\s+([,;:])", r"\1", out).strip()


def _section_key(heading: str, name: str) -> str:
    """'## Moves learned by Bulbasaur' -> 'moves learned'.

    The Pokemon's own name appears inside several headings, so it is removed to
    give one stable key per section across every page.
    """
    key = fold(strip_markup(heading))
    key = key.replace(fold(name), " ")
    key = _WHITESPACE.sub(" ", key).strip()
    return re.sub(r"\s+by$", "", key).strip()


def split_sections(text: str, name: str) -> dict[str, str]:
    """Split a passage into {section key: body}, keyed by normalised heading.

    Later chunks win ties only when they carry more text: passages overlap, and
    a section can appear truncated in one chunk and whole in the next.
    """
    sections: dict[str, str] = {}
    matches = list(_HEADING.finditer(text or ""))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        key = _section_key(m.group(2), name)
        if not key:
            continue
        body = text[m.end():end].strip()
        if len(body) > len(sections.get(key, "")):
            sections[key] = body
    return sections


def table_rows(section: str, *, strip: bool = True) -> list[list[str]]:
    """Every pipe-table row in a section, as lists of cells.

    `strip=False` keeps the markdown. Two fields need it: the type cell
    separates its types only by being two separate /type/ links, and the
    abilities cell separates its entries only by a double space. Collapsing
    whitespace and unwrapping links — which is what strip_markup does — turns
    both into one indivisible string.
    """
    rows: list[list[str]] = []
    for line in (section or "").split("\n"):
        line = line.strip()
        if not line.startswith("|") or _TABLE_RULE.match(line):
            continue
        cells = [strip_markup(c) if strip else c.strip() for c in line.strip("|").split("|")]
        if any(cells):
            rows.append(cells)
    return rows


def kv_table(section: str, *, strip: bool = True) -> dict[str, str]:
    """A two-column table as {folded label: value}.

    The key is always folded and stripped; `strip` controls the value only.
    """
    out: dict[str, str] = {}
    for cells in table_rows(section, strip=strip):
        if len(cells) >= 2 and cells[0]:
            out.setdefault(fold(strip_markup(cells[0])), cells[1])
    return out


# ── field parsers ────────────────────────────────────────────────────────────

def parse_abilities(cell: str) -> tuple[list[str], str | None]:
    """'1. Overgrow  Chlorophyll (hidden ability)' -> (['Overgrow'], 'Chlorophyll').

    Takes the *raw* cell. PokemonDB separates ability entries with a double
    space and numbers only the normal ones, so a Pokemon with one normal and
    one hidden ability renders as '1. X  Y (hidden ability)' with no '2.'.
    Running strip_markup first collapses that double space and leaves the two
    names welded into one; splitting on the numbering instead then swallows the
    hidden ability into the normal list.
    """
    text = html.unescape(cell or "").replace("\xa0", " ")
    text = _MD_EMPHASIS.sub(r"\1", _MD_LINK.sub(r"\1", text))
    parts = [p.strip() for p in re.split(r"\s{2,}", text.strip()) if p.strip()]

    normal: list[str] = []
    hidden: str | None = None
    for part in parts:
        is_hidden = re.search(r"\(hidden ability\)", part, re.I) is not None
        name = re.sub(r"\(hidden ability\)", "", part, flags=re.I)
        name = re.sub(r"^\d+\.\s*", "", name).strip()
        if not name:
            continue
        if is_hidden:
            hidden = name
        else:
            normal.append(name)
    return normal, hidden


def parse_evolution(section: str) -> list[tuple[str, str | None]]:
    """-> [('Bulbasaur', 'Level 16'), ('Ivysaur', 'Level 32'), ('Venusaur', None)].

    Stage names come from their /pokedex/ links rather than the bare text
    lines, which also carry types and sprite alt text. The condition attached
    to a stage is the one that produces the *next* stage.
    """
    stages: list[str] = []
    conditions: list[str] = []
    for raw_line in (section or "").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        link = re.search(r"\[([^\]]+)\]\(/pokedex/[^)]+\)", line)
        if link:
            nm = link.group(1).strip()
            if not stages or stages[-1] != nm:
                stages.append(nm)
                # Keep the two lists aligned: a stage with no condition yet.
                while len(conditions) < len(stages) - 1:
                    conditions.append("")
            continue
        cond = re.fullmatch(r"\((.+)\)", strip_markup(line))
        if cond and len(conditions) < len(stages):
            conditions.append(cond.group(1).strip())
    out: list[tuple[str, str | None]] = []
    for i, stage in enumerate(stages):
        out.append((stage, conditions[i] if i < len(conditions) and conditions[i] else None))
    return out


def parse_entries(section: str) -> list[tuple[str, str]]:
    """Pokedex flavour text as [(games, text)], in page order."""
    return [
        (cells[0], cells[1])
        for cells in table_rows(section)
        if len(cells) >= 2 and cells[0] and cells[1]
    ]


def parse_level_up_moves(section: str) -> list[tuple[str, str]]:
    """The level-up move table as [(level, move)], header row excluded."""
    out: list[tuple[str, str]] = []
    for cells in table_rows(section):
        if len(cells) < 2:
            continue
        level, move = cells[0].strip(), cells[1].strip()
        if not level or not move or fold(level).startswith("lv"):
            continue
        out.append((level, move))
    return out


# ── the model ────────────────────────────────────────────────────────────────

@dataclass
class PokemonFacts:
    name: str
    types: list[str] = field(default_factory=list)
    species: str = ""
    height: str = ""
    weight: str = ""
    abilities: list[str] = field(default_factory=list)
    hidden_ability: str | None = None
    ev_yield: str = ""
    catch_rate: str = ""
    base_exp: str = ""
    growth_rate: str = ""
    friendship: str = ""
    egg_groups: list[str] = field(default_factory=list)
    egg_cycles: str = ""
    gender: str = ""
    evolution: list[tuple[str, str | None]] = field(default_factory=list)
    entries: list[tuple[str, str]] = field(default_factory=list)
    level_up_moves: list[tuple[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PokemonFacts":
        """Rebuild from JSON, where every tuple has become a list."""
        d = dict(data)
        d["evolution"] = [(s, c) for s, c in d.get("evolution") or []]
        d["entries"] = [(g, t) for g, t in d.get("entries") or []]
        d["level_up_moves"] = [(lv, mv) for lv, mv in d.get("level_up_moves") or []]
        allowed = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in allowed})


def _split_list(cell: str) -> list[str]:
    """'Grass , Monster' -> ['Grass', 'Monster'] — the tables use loose commas."""
    return [p.strip() for p in re.split(r",|\s{2,}", cell or "") if p.strip()]


def build_facts(name: str, chunks: list[str]) -> PokemonFacts:
    """Merge a document's passages and parse every v1 section out of them.

    Missing sections are left at their defaults rather than raising: retrieval
    is query-driven and cannot guarantee which chunks come back, so partial
    facts are the normal case, not an error.
    """
    merged: dict[str, str] = {}
    for chunk in chunks:
        for key, body in split_sections(chunk, name).items():
            if len(body) > len(merged.get(key, "")):
                merged[key] = body

    facts = PokemonFacts(name=name)

    dex = kv_table(merged.get("pokedex data", ""))
    raw_dex = kv_table(merged.get("pokedex data", ""), strip=False)
    if dex:
        type_cell = raw_dex.get("type", "")
        facts.types = (re.findall(r"\[([^\]]+)\]\(/type/[^)]*\)", type_cell)
                       or _split_list(dex.get("type", "")))
        facts.species = dex.get("species", "")
        facts.height = dex.get("height", "")
        facts.weight = dex.get("weight", "")
        facts.abilities, facts.hidden_ability = parse_abilities(raw_dex.get("abilities", ""))

    training = kv_table(merged.get("training", ""))
    if training:
        facts.ev_yield = training.get("ev yield", "")
        facts.catch_rate = training.get("catch rate", "")
        facts.base_exp = training.get("base exp.", "") or training.get("base exp", "")
        facts.growth_rate = training.get("growth rate", "")
        facts.friendship = training.get("base friendship", "")

    breeding = kv_table(merged.get("breeding", ""))
    if breeding:
        facts.egg_groups = _split_list(breeding.get("egg groups", ""))
        facts.egg_cycles = breeding.get("egg cycles", "")
        facts.gender = breeding.get("gender", "")

    facts.evolution = parse_evolution(merged.get("evolution chart", ""))
    facts.entries = parse_entries(merged.get("pokedex entries", ""))
    facts.level_up_moves = parse_level_up_moves(merged.get("moves learnt by level up", ""))
    return facts


# ── rendering ────────────────────────────────────────────────────────────────

TOPICS = ("abilities", "evolution", "training", "breeding", "entries", "moves")

_MAX_MOVES = 8
_MAX_ENTRY_CHARS = 300


def _join(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def _display(name: str) -> str:
    """'ho-oh' -> 'Ho-Oh'. Names are stored lowercase by the resolver."""
    return re.sub(r"(^|[\s\-'])([a-z])", lambda m: m.group(1) + m.group(2).upper(), name)


def render_answer(topic: str, facts: PokemonFacts) -> str | None:
    """Render `topic` as prose, or None when the facts do not cover it.

    None is the important half of the contract: it means "I do not know",
    and coach_api turns that into a fall-through to CRGA rather than a guess.
    """
    if facts is None:
        return None
    name = _display(facts.name)

    if topic == "abilities":
        if not facts.abilities and not facts.hidden_ability:
            return None
        parts = []
        if facts.abilities:
            verb = "abilities are" if len(facts.abilities) > 1 else "ability is"
            parts.append(f"{name}'s {verb} {_join(facts.abilities)}.")
        if facts.hidden_ability:
            parts.append(f"Its hidden ability is {facts.hidden_ability}.")
        elif facts.abilities:
            parts.append("It has no hidden ability.")
        return " ".join(parts)

    if topic == "evolution":
        if not facts.evolution:
            return None
        if len(facts.evolution) == 1:
            return f"{name} does not evolve."
        steps = []
        for i in range(len(facts.evolution) - 1):
            _, condition = facts.evolution[i]
            nxt, _ = facts.evolution[i + 1]
            steps.append(f"{nxt}{f' at {condition}' if condition else ''}")
        line = f"{facts.evolution[0][0]} evolves into " + ", then into ".join(steps) + "."
        return line

    if topic == "training":
        bits = []
        if facts.ev_yield:
            bits.append(f"it yields {facts.ev_yield}")
        if facts.catch_rate:
            bits.append(f"its catch rate is {facts.catch_rate}")
        if facts.base_exp:
            bits.append(f"it gives {facts.base_exp} base experience")
        if facts.growth_rate:
            bits.append(f"its growth rate is {facts.growth_rate}")
        if not bits:
            return None
        return f"For training {name}: " + _join(bits) + "."

    if topic == "breeding":
        bits = []
        if facts.egg_groups:
            bits.append(f"it is in the {_join(facts.egg_groups)} egg group"
                        f"{'s' if len(facts.egg_groups) > 1 else ''}")
        if facts.egg_cycles:
            bits.append(f"it takes {facts.egg_cycles} egg cycles to hatch")
        if facts.gender:
            bits.append(f"its gender ratio is {facts.gender}")
        if not bits:
            return None
        return f"For breeding {name}: " + _join(bits) + "."

    if topic == "entries":
        if not facts.entries:
            return None
        # The newest entry is the last row, and is the one written in modern
        # prose — the Gen 1 entries are shouty ("BULBASAUR can be seen...").
        games, text = facts.entries[-1]
        if len(text) > _MAX_ENTRY_CHARS:
            text = text[:_MAX_ENTRY_CHARS].rsplit(" ", 1)[0] + "…"
        return f"{name}, the {facts.species or 'Pokémon'}. From Pokémon {games}: “{text}”"

    if topic == "moves":
        if not facts.level_up_moves:
            return None
        shown = facts.level_up_moves[:_MAX_MOVES]
        listed = _join([f"{mv} (Lv. {lv})" for lv, mv in shown])
        more = len(facts.level_up_moves) - len(shown)
        tail = f" It learns {more} more by level up." if more > 0 else ""
        return f"{name} learns {listed} by level up.{tail}"

    return None
