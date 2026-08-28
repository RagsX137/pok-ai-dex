import pandas as pd
from pathlib import Path

_CSV = Path(__file__).parent / "pokemon_db.csv"

_GEN_MAP = {
    1: (1, 151), 2: (152, 251), 3: (252, 386), 4: (387, 493),
    5: (494, 649), 6: (650, 721), 7: (722, 809), 8: (810, 905), 9: (906, 1025),
}


def _load_df() -> pd.DataFrame:
    df = pd.read_csv(_CSV)
    df["pokedex_num"] = df["pokedex_num"].astype(str).str.zfill(4)
    return df


def _row_to_dict(row: pd.Series) -> dict:
    name = row["pokemon"].lower().replace(" ", "-")
    return {
        "name":      row["pokemon"],
        "number":    row["pokedex_num"],
        "type1":     row["elem_1"],
        "type2":     row["elem_2"] if pd.notna(row["elem_2"]) else None,
        "species":   row["species"],
        "hp":        int(row["hp"]),
        "attack":    int(row["attack"]),
        "defense":   int(row["defense"]),
        "sp_atk":    int(row["sp_atk"]),
        "sp_def":    int(row["sp_def"]),
        "speed":     int(row["speed"]),
        "total":     int(row["total"]),
        "image_url": f"/images/{name}_image.jpg",
    }


def look_up_by_type(type: str, limit: int = 20) -> list[dict]:
    """Return Pokémon whose primary or secondary type matches `type`."""
    df = _load_df()
    t  = type.strip().capitalize()
    mask = (
        df["elem_1"].str.upper() == t.upper()
    ) | (
        df["elem_2"].fillna("").str.upper() == t.upper()
    )
    return [_row_to_dict(r) for _, r in df[mask].head(limit).iterrows()]


def look_up_by_generation(generation: int, limit: int = 20) -> list[dict]:
    """Return Pokémon in the given generation (1–9)."""
    lo, hi = _GEN_MAP.get(generation, (1, 151))
    df = _load_df()
    df = df.copy()
    df["num_int"] = df["pokedex_num"].astype(int)
    mask = (df["num_int"] >= lo) & (df["num_int"] <= hi)
    return [_row_to_dict(r) for _, r in df[mask].head(limit).iterrows()]


def get_pokemon_detail(name: str) -> dict | None:
    """Return full details for a single named Pokémon, or None if not found."""
    df   = _load_df()
    mask = df["pokemon"].str.lower() == name.strip().lower()
    rows = df[mask]
    if rows.empty:
        return None
    return _row_to_dict(rows.iloc[0])
