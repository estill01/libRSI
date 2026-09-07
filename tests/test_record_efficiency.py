from __future__ import annotations

import json
from collections import UserDict
from dataclasses import replace

import pytest

import librsi.records as records
from librsi import (
    ArtifactRef,
    Claim,
    Outcome,
    deserialize_record,
    record_from_dict,
    serialize_record,
)
from librsi.identity import FrozenMap, canonical_json


def _shared_outcome():
    artifact = ArtifactRef(
        artifact_id="report", uri="memory://report", metadata={"reader": "first"}
    )
    other_metadata = replace(artifact, metadata={"reader": "second"})
    return Outcome(
        intent=Claim(statement="Shared results remain exact").ref,
        status="supported",
        artifacts=(artifact, artifact, other_metadata, other_metadata),
    )


def test_repeated_nested_records_validate_once_without_conflating_metadata(monkeypatch):
    source = _shared_outcome()
    serialized = serialize_record(source)
    calls = []
    original = ArtifactRef.__post_init__

    def counted(self):
        calls.append(self.uri)
        original(self)

    monkeypatch.setattr(ArtifactRef, "__post_init__", counted)
    decoded = deserialize_record(serialized)
    assert serialize_record(decoded) == serialized
    assert len(calls) == 2
    assert [item.metadata["reader"] for item in decoded.artifacts] == [
        "first",
        "first",
        "second",
        "second",
    ]


def test_same_claimed_root_does_not_hide_changed_nested_data():
    payload = _shared_outcome().to_dict()
    payload["data"]["artifacts"][1]["data"]["uri"] = "memory://forged"
    with pytest.raises(ValueError, match="root does not match"):
        record_from_dict(payload)


def test_decode_reuse_does_not_survive_an_outer_call():
    serialized = serialize_record(_shared_outcome())
    first = deserialize_record(serialized)
    object.__setattr__(first.artifacts[0], "uri", "memory://forged")
    second = deserialize_record(serialized)
    assert second.artifacts[0].uri == "memory://report"
    assert serialize_record(second) == serialized


def test_serialization_reuses_shared_records_without_changing_public_documents(monkeypatch):
    source = _shared_outcome()
    expected = canonical_json(source.to_dict())
    calls = []
    original = records.fields

    def counted(value):
        if isinstance(value, ArtifactRef):
            calls.append(value.artifact_id)
        return original(value)

    monkeypatch.setattr(records, "fields", counted)
    assert serialize_record(source) == expected
    assert len(calls) == 2
    assert serialize_record(source) == expected
    assert len(calls) == 4
    document = source.to_dict()
    document["data"]["artifacts"][0]["metadata"]["reader"] = "changed"
    assert document["data"]["artifacts"][1]["metadata"]["reader"] == "first"
    object.__setattr__(source.artifacts[0], "uri", "memory://changed")
    assert serialize_record(source) != expected


def test_same_root_metadata_preserves_numeric_types_and_signed_zero():
    source = _shared_outcome()
    source = replace(
        source,
        artifacts=tuple(
            replace(source.artifacts[0], metadata={"n": value})
            for value in (True, 1, 1.0, 0.0, -0.0)
        ),
    )
    serialized = serialize_record(source)
    assert serialize_record(deserialize_record(serialized)) == serialized


@pytest.mark.parametrize(
    "value",
    [
        {"unicode": "é\n\t\u2028", "values": [None, True, False, -0.0, 1e-100, 10**100]},
        {"b": [], "a": {"escaped": '\\"'}},
    ],
)
def test_native_canonical_encoding_preserves_exact_bytes(value):
    expected = json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )
    assert canonical_json(value) == expected
    assert canonical_json(FrozenMap(value)) == expected
    assert canonical_json(UserDict(value)) == expected


@pytest.mark.parametrize("value", [{"nested": {1: "coerced"}}, {"nested": {None: "coerced"}}])
def test_native_encoder_cannot_coerce_non_string_keys(value):
    with pytest.raises(TypeError, match="string keys"):
        canonical_json(value)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_native_encoder_rejects_nonfinite_values(value):
    with pytest.raises(ValueError, match="finite"):
        canonical_json({"nested": [value]})


def test_shared_json_containers_are_not_cycles():
    shared = {"x": [1, 2]}
    assert canonical_json([shared, shared]) == '[{"x":[1,2]},{"x":[1,2]}]'
    shared["x"].append(shared)
    with pytest.raises(ValueError, match="cycles"):
        canonical_json(shared)


def test_deep_fallback_preserves_mixed_values():
    leaf = [None, True, False, 7, -0.0, 1.5, "é", [], {"value": 2}]
    value = leaf
    for _ in range(1500):
        value = {"next": value}
    assert canonical_json(value) == '{"next":' * 1500 + canonical_json(leaf) + "}" * 1500


@pytest.mark.parametrize(
    "leaf, error", [(float("inf"), ValueError), ({1: "bad"}, TypeError), (object(), TypeError)]
)
def test_deep_fallback_keeps_rejecting_invalid_values(leaf, error):
    value = leaf
    for _ in range(1500):
        value = {"next": value}
    with pytest.raises(error):
        canonical_json(value)
