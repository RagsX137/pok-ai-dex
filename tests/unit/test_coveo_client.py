import json


def _event(payload_type, payload, **extra):
    return "data: " + json.dumps(
        {"payloadType": payload_type, "payload": json.dumps(payload), **extra}
    )


def test_parses_text_deltas_in_order():
    from pokedex.coveo import parse_genqa_stream
    lines = [
        _event("genqa.messageType", {"textDelta": "Pikachu is "}),
        _event("genqa.messageType", {"textDelta": "an Electric-type."}),
        _event("genqa.endOfStreamType", {}),
    ]
    answer, citations, error = parse_genqa_stream(lines)
    assert answer == "Pikachu is an Electric-type."
    assert citations == []
    assert error is None


def test_collects_citations():
    from pokedex.coveo import parse_genqa_stream
    lines = [
        _event("genqa.citationsType",
               {"citations": [{"title": "Pikachu", "clickUri": "https://x/pikachu"}]}),
        _event("genqa.endOfStreamType", {}),
    ]
    _, citations, _ = parse_genqa_stream(lines)
    assert citations[0]["title"] == "Pikachu"


def test_surfaces_error_finish_reason():
    from pokedex.coveo import parse_genqa_stream
    lines = ['data: ' + json.dumps(
        {"finishReason": "ERROR", "errorMessage": "model unavailable"})]
    answer, _, error = parse_genqa_stream(lines)
    assert error == "model unavailable"
    assert answer == ""


def test_ignores_non_data_lines_and_bad_json():
    from pokedex.coveo import parse_genqa_stream
    lines = [
        "",
        ": keep-alive",
        "data: {not json",
        _event("genqa.messageType", {"textDelta": "ok"}),
        _event("genqa.endOfStreamType", {}),
    ]
    answer, _, error = parse_genqa_stream(lines)
    assert answer == "ok"
    assert error is None


def test_accepts_bytes_lines():
    from pokedex.coveo import parse_genqa_stream
    lines = [
        _event("genqa.messageType", {"textDelta": "hi"}).encode(),
        _event("genqa.endOfStreamType", {}).encode(),
    ]
    answer, _, _ = parse_genqa_stream(lines)
    assert answer == "hi"


def test_stops_at_end_of_stream():
    from pokedex.coveo import parse_genqa_stream
    lines = [
        _event("genqa.messageType", {"textDelta": "first"}),
        _event("genqa.endOfStreamType", {}),
        _event("genqa.messageType", {"textDelta": " LEAKED"}),
    ]
    answer, _, _ = parse_genqa_stream(lines)
    assert answer == "first"
