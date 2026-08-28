"""
probe_crga.py
=============
Diagnostic tool: verifies the full CRGA pipeline end-to-end.

Correct flow (per Coveo Headless GeneratedAnswerAPIClient):
  1. POST /rest/search/v2 with enableGenerativeQuestionAnswering=True
     → extendedResults.generativeQuestionAnsweringId  (streamId)
  2. GET /rest/organizations/{org}/machinelearning/streaming/{streamId}
     Accept: */*  → SSE stream of genqa.* events

Usage:
    python probe_crga.py                        # default query
    python probe_crga.py "What type is Gengar?" # custom query
"""
import os, sys, json, time, requests
from dotenv import load_dotenv

load_dotenv()

COVEO_ORG   = os.getenv("COVEO_ORGANIZATION_ID", "")
COVEO_TOKEN = os.getenv("COVEO_ACCESS_TOKEN", "")
COVEO_BASE  = f"https://{COVEO_ORG}.org.coveo.com"
QUERY       = sys.argv[1] if len(sys.argv) > 1 else "What type is Pikachu?"

hdrs_json = {
    "Authorization": f"Bearer {COVEO_TOKEN}",
    "Content-Type":  "application/json",
}

print(f"Org:   {COVEO_ORG}")
print(f"Query: {QUERY}\n")

# ── Step 1: Search with enableGenerativeQuestionAnswering ─────────────────────
stream_id = search_uid = None
for attempt in range(1, 8):
    r = requests.post(
        f"{COVEO_BASE}/rest/search/v2?organizationId={COVEO_ORG}",
        json={
            "q":               QUERY,
            "searchHub":       os.getenv("COVEO_SEARCH_HUB", "PokedexUI"),
            "pipeline":        os.getenv("COVEO_PIPELINE", "default"),
            "numberOfResults": 5,
            "enableGenerativeQuestionAnswering": True,
        },
        headers=hdrs_json,
        timeout=15,
    )
    d         = r.json()
    search_uid = d.get("searchUid", "")
    stream_id  = d.get("extendedResults", {}).get("generativeQuestionAnsweringId")
    print(f"Attempt {attempt}: search={r.status_code}  streamId={stream_id or '(none yet)'}")
    if stream_id:
        break
    time.sleep(2)

if not stream_id:
    print("\nERROR: No streamId after retries.")
    print("Check that the RGA model is associated with the pipeline in Coveo Admin.")
    sys.exit(1)

print(f"\nstreamId:  {stream_id}")
print(f"searchUid: {search_uid}")

# ── Step 2: Stream the answer ─────────────────────────────────────────────────
stream_url = (
    f"{COVEO_BASE}/rest/organizations/{COVEO_ORG}"
    f"/machinelearning/streaming/{stream_id}"
)
print(f"\nStreaming from:\n  {stream_url}\n")

r2 = requests.get(
    stream_url,
    headers={"Authorization": f"Bearer {COVEO_TOKEN}", "Accept": "*/*"},
    timeout=45,
    stream=True,
)
print(f"Status: {r2.status_code}  Content-Type: {r2.headers.get('Content-Type', '?')}\n")

if r2.status_code != 200:
    print("ERROR:", r2.text[:400])
    sys.exit(1)

answer_parts = []
citations    = []

for raw_line in r2.iter_lines():
    if not raw_line:
        continue
    line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
    if not line.startswith("data:"):
        continue
    try:
        event = json.loads(line[5:].strip())
    except ValueError:
        continue

    ptype  = event.get("payloadType", "")
    praw   = event.get("payload", "")
    finish = event.get("finishReason")

    print(f"  event: {ptype or finish or '?'}")

    payload = json.loads(praw) if praw else {}

    if ptype == "genqa.messageType":
        delta = payload.get("textDelta", "")
        if delta.strip():
            answer_parts.append(delta)
    elif ptype == "genqa.citationsType":
        citations = payload.get("citations", [])
    elif ptype == "genqa.endOfStreamType" or finish == "COMPLETED":
        break

answer = "".join(answer_parts).strip()

print(f"\n{'='*60}")
print(f"ANSWER:\n{answer}")
print(f"\nCITATIONS ({len(citations)}):")
for c in citations:
    print(f"  - {c.get('title', '')}  ({c.get('uri') or c.get('clickUri', '')})")
print("="*60)
