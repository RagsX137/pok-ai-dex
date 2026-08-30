"""
check_qre_override.py
Verifies rankingExpressions actually changes scores by testing threshold=0.80,
0.70, and 0.60 on "electric mouse" and watching Pikachu's KNN score shift.
"""
import os, re, requests
from dotenv import load_dotenv
load_dotenv()

ORG   = os.getenv("COVEO_ORGANIZATION_ID", "")
TOKEN = os.getenv("COVEO_ACCESS_TOKEN", "")
BASE  = f"https://{ORG}.org.coveo.com"

KNN_FIELD = "knn_vector_037690fe_cd91_4e3f_961d_3b5c5f25bfb4_embeddings_vector"
_KNN_RE   = re.compile(r"Ranking functions:\s*(\d+)", re.IGNORECASE)


def qre(t: float) -> str:
    return (
        f"var min_cosine := {t};\n"
        f"var min_r := 100.0;\nvar max_r := 4500.0;\n"
        f"var cos_sim := @{KNN_FIELD};\n"
        f"if (cos_sim >= min_cosine) {{\n"
        f"  var n := (cos_sim - min_cosine) / (1.0 - min_cosine);\n"
        f"  min_r + n * (max_r - min_r)\n}}"
    )


def search(q: str, threshold: float) -> dict:
    body = {
        "q": q, "numberOfResults": 5,
        "searchHub": "PokedexUI", "pipeline": "default",
        "debug": True,
        "rankingExpressions": [{"expression": qre(threshold), "modifier": 0}],
    }
    r = requests.post(
        f"{BASE}/rest/search/v2?organizationId={ORG}", json=body,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


if __name__ == "__main__":
    for t in [0.80, 0.70, 0.60]:
        d = search("electric mouse", t)
        print(f"\nthreshold={t}")
        for r in d["results"][:5]:
            ri  = r.get("rankingInfo", "")
            m   = _KNN_RE.search(ri) if isinstance(ri, str) else None
            knn = int(m.group(1)) if m else 0
            name = r["title"].split(" Pokédex")[0].split(" | ")[0]
            print(f"  [{knn:>4} KNN | {r['score']:>5.0f}]  {name}")
