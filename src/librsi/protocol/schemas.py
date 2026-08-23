"""Closed JSON Schemas shared by CLI and later transport projections."""

from __future__ import annotations

from typing import Any

from ..runtime import Action
from .records import TargetAdmission

EXTERNAL_AGENT_SCHEMA = "librsi.external-agent/v1"
EXTERNAL_ERROR_SCHEMA = "librsi.external-error/v1"
EXTERNAL_AGENT_SCHEMA_VERSION = 1
_DRAFT = "https://json-schema.org/draft/2020-12/schema"
_ROOT = {"type": "string", "pattern": "^[0-9a-f]{64}$"}

_SUCCESS_CONTRACTS: dict[
    str,
    tuple[str, str, tuple[str, ...], tuple[str, ...]],
] = {
    "validation-evidence": (
        "batch",
        "validation_evidence_batch",
        ("request", "disposition", "evidence", "reason"),
        ("validation_evidence_batch",),
    ),
    "investigation-reason": (
        "result",
        "reasoning_result",
        ("request", "kind", "content", "narration"),
        ("reasoning_result",),
    ),
    "investigation-experiment": (
        "batch",
        "investigation_evidence_batch",
        ("request", "disposition", "evidence", "reason"),
        ("investigation_evidence_batch",),
    ),
    "improvement-cycle": (
        "proposal",
        "improvement_cycle_proposal",
        ("request", "investigation", "batches"),
        ("improvement_cycle_proposal",),
    ),
    "evaluate-self-change-history": (
        "evaluation",
        "self_change_evaluation",
        ("request", "stage", "action", "batch", "assessment", "disposition", "reason"),
        ("self_change_evaluation", "candidate_trial_batch", "candidate_assessment"),
    ),
    "evaluate-self-change-shadow": (
        "evaluation",
        "self_change_evaluation",
        ("request", "stage", "action", "batch", "assessment", "disposition", "reason"),
        ("self_change_evaluation", "candidate_trial_batch", "candidate_assessment"),
    ),
    "review-self-change": (
        "review",
        "self_change_review",
        ("request", "forward_evaluation", "action", "review", "disposition", "reason"),
        ("self_change_review", "candidate_review"),
    ),
    "apply-selected-candidate": (
        "receipt",
        "application_receipt",
        ("request", "action", "candidate", "prior_snapshot", "produced_snapshot"),
        ("application_receipt", "target_snapshot"),
    ),
    "verify-applied-target": (
        "verification",
        "application_verification",
        (
            "request",
            "application",
            "action",
            "observed_snapshot",
            "disposition",
            "reason",
            "assessment",
            "operational_failure",
        ),
        ("application_verification", "target_snapshot"),
    ),
    "rollback-applied-target": (
        "rollback",
        "rollback_receipt",
        ("request", "application", "verification", "action", "restored_snapshot"),
        ("rollback_receipt", "target_snapshot"),
    ),
}


def _record_ref(record_type: str | None = None) -> dict[str, Any]:
    record_type_schema: dict[str, Any] = (
        {"type": "string", "minLength": 1} if record_type is None else {"const": record_type}
    )
    return {
        "type": "object",
        "required": ["$schema", "record_type", "root"],
        "properties": {
            "$schema": {"const": "librsi.ref/v1"},
            "record_type": record_type_schema,
            "root": _ROOT,
        },
        "additionalProperties": False,
    }


def _plain_value() -> dict[str, Any]:
    return {
        "anyOf": [
            {"type": ["null", "boolean", "number", "string"]},
            {"type": "array", "items": {"$ref": "#/$defs/plainValue"}},
            {
                "type": "object",
                "additionalProperties": {"$ref": "#/$defs/plainValue"},
            },
        ]
    }


def _canonical_map(*, amounts: bool = False) -> dict[str, Any]:
    item_schema: dict[str, Any] = (
        {"type": "number", "minimum": 0} if amounts else {"$ref": "#/$defs/canonicalValue"}
    )
    return {
        "type": "object",
        "required": ["$schema", "items"],
        "properties": {
            "$schema": {"const": "librsi.map/v1"},
            "items": {"type": "object", "additionalProperties": item_schema},
        },
        "additionalProperties": False,
    }


def _record_envelope(
    record_type: str,
    data: dict[str, Any],
    *,
    root: str | None = None,
) -> dict[str, Any]:
    root_schema: dict[str, Any] = _ROOT if root is None else {"const": root}
    return {
        "type": "object",
        "required": ["$schema", "record_type", "schema_version", "root", "data", "metadata"],
        "properties": {
            "$schema": {"const": "librsi.record/v1"},
            "record_type": {"const": record_type},
            "schema_version": {"const": 1},
            "root": root_schema,
            "data": data,
            "metadata": {
                "type": "object",
                "additionalProperties": {"$ref": "#/$defs/plainValue"},
            },
        },
        "additionalProperties": False,
    }


def _action_payload(action: Action, name: str) -> dict[str, Any]:
    payload = action.to_dict()["data"]["payload"]["items"].get(name)
    if not isinstance(payload, dict):
        raise ValueError(f"{action.kind} action lost its exact {name} payload")
    return payload


def _encoded_record_data(document: dict[str, Any]) -> dict[str, Any]:
    try:
        data = document["items"]["data"]["items"]
    except (KeyError, TypeError) as exc:
        raise ValueError("external action payload lost its encoded canonical record") from exc
    if not isinstance(data, dict):
        raise ValueError("external action payload record data must be canonical")
    return data


def _success_field_constants(action: Action) -> dict[str, Any]:
    if action.kind in {
        "validation-evidence",
        "investigation-reason",
        "investigation-experiment",
        "improvement-cycle",
    }:
        return {"request": _action_payload(action, "request")}
    if action.kind in {
        "evaluate-self-change-history",
        "evaluate-self-change-shadow",
        "review-self-change",
        "apply-selected-candidate",
    }:
        command = _action_payload(action, "command")
        command_data = _encoded_record_data(command)
        constants = {"request": command_data["request"]}
        if action.kind == "review-self-change":
            constants["forward_evaluation"] = command_data["forward_evaluation"]
        return constants
    if action.kind == "verify-applied-target":
        application = _action_payload(action, "application")
        application_data = _encoded_record_data(application)
        return {
            "request": application_data["request"],
            "application": application,
        }
    if action.kind == "rollback-applied-target":
        verification = _action_payload(action, "verification")
        verification_data = _encoded_record_data(verification)
        application = verification_data["application"]
        application_data = _encoded_record_data(application)
        return {
            "request": application_data["request"],
            "application": application,
            "verification": verification,
        }
    raise ValueError(f"unsupported external action kind: {action.kind}")


def _typed_semantic_record(
    record_type: str,
    fields: tuple[str, ...],
    constants: dict[str, Any],
) -> dict[str, Any]:
    names = ("lineage", *fields)
    arrays = {"lineage", "evidence", "batches"}
    optional_text = {"reason", "narration"}
    text = {"disposition", "kind", "stage"}
    properties = {
        name: (
            {"const": constants[name]}
            if name in constants
            else {"type": "array"}
            if name in arrays
            else {"type": ["string", "null"]}
            if name in optional_text
            else {"type": "string"}
            if name in text
            else {"type": ["object", "null"]}
            if name in {"assessment", "operational_failure"}
            else {"type": "object"}
        )
        for name in names
    }
    return {
        "type": "object",
        "required": ["$schema", "items"],
        "properties": {
            "$schema": {"const": "librsi.map/v1"},
            "items": {
                "type": "object",
                "required": [
                    "$schema",
                    "record_type",
                    "schema_version",
                    "root",
                    "data",
                    "metadata",
                ],
                "properties": {
                    "$schema": {"const": "librsi.record/v1"},
                    "record_type": {"const": record_type},
                    "schema_version": {"const": 1},
                    "root": _ROOT,
                    "data": {
                        "type": "object",
                        "required": ["$schema", "items"],
                        "properties": {
                            "$schema": {"const": "librsi.map/v1"},
                            "items": {
                                "type": "object",
                                "required": list(names),
                                "properties": properties,
                                "additionalProperties": False,
                            },
                        },
                        "additionalProperties": False,
                    },
                    "metadata": {
                        "type": "object",
                        "required": ["$schema", "items"],
                        "properties": {
                            "$schema": {"const": "librsi.map/v1"},
                            "items": {"type": "object"},
                        },
                        "additionalProperties": False,
                    },
                },
                "additionalProperties": False,
            },
        },
        "additionalProperties": False,
    }


def _output_refs(record_types: tuple[str, ...]) -> dict[str, Any]:
    return {
        "type": "array",
        "minItems": len(record_types),
        "maxItems": len(record_types),
        "prefixItems": [_record_ref(record_type) for record_type in record_types],
        "items": False,
    }


def _payload_map(name: str, record_schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["$schema", "items"],
        "properties": {
            "$schema": {"const": "librsi.map/v1"},
            "items": {
                "type": "object",
                "required": [name],
                "properties": {name: record_schema},
                "additionalProperties": False,
            },
        },
        "additionalProperties": False,
    }


def _empty_payload_map() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["$schema", "items"],
        "properties": {
            "$schema": {"const": "librsi.map/v1"},
            "items": {"type": "object", "maxProperties": 0},
        },
        "additionalProperties": False,
    }


def _resource_usage_schema(action: Action) -> dict[str, Any]:
    if action.kind != "improvement-cycle":
        return {"$ref": "#/$defs/amountMap"}
    limit = action.budget_reservation.get("units")
    if not isinstance(limit, (int, float)):
        raise ValueError("improvement action lost its exact resource reservation")
    return {
        "type": "object",
        "required": ["$schema", "items"],
        "properties": {
            "$schema": {"const": "librsi.map/v1"},
            "items": {
                "type": "object",
                "required": ["units"],
                "properties": {"units": {"type": "number", "minimum": 0, "maximum": limit}},
                "additionalProperties": False,
            },
        },
        "additionalProperties": False,
    }


def external_response_schema() -> dict[str, Any]:
    """Return the closed common envelope for every successful CLI response."""

    return {
        "$schema": _DRAFT,
        "$id": EXTERNAL_AGENT_SCHEMA,
        "type": "object",
        "required": ["$schema", "schema_version", "operation", "run_id", "state_root", "data"],
        "properties": {
            "$schema": {"const": EXTERNAL_AGENT_SCHEMA},
            "schema_version": {"const": EXTERNAL_AGENT_SCHEMA_VERSION},
            "operation": {"type": "string", "minLength": 1},
            "run_id": {"type": ["string", "null"]},
            "state_root": {"anyOf": [_ROOT, {"type": "null"}]},
            "data": {"type": "object"},
        },
        "additionalProperties": False,
    }


def target_admission_schema(admission: TargetAdmission) -> dict[str, Any]:
    """Return an exact schema for one already-canonical target admission."""

    if type(admission) is not TargetAdmission:
        raise TypeError("target-admission schemas require an exact TargetAdmission")
    return {
        "$schema": _DRAFT,
        "$id": f"librsi.target-admission/v1/{admission.root}",
        "const": admission.to_dict(),
    }


def action_result_schema(action: Action) -> dict[str, Any]:
    """Return a closed result schema bound to one exact pending Action."""

    if type(action) is not Action:
        raise TypeError("action-result schemas require an exact Action")
    try:
        payload_name, record_type, fields, output_types = _SUCCESS_CONTRACTS[action.kind]
    except KeyError as exc:
        raise ValueError(f"unsupported external action kind: {action.kind}") from exc
    success_record = _typed_semantic_record(
        record_type,
        fields,
        _success_field_constants(action),
    )
    failure_data = {
        "type": "object",
        "required": ["lineage", "classification", "message", "retryable", "details"],
        "properties": {
            "lineage": {"type": "array", "items": {"$ref": "#/$defs/recordRef"}},
            "classification": {
                "enum": [
                    "transient",
                    "invalid-result",
                    "execution",
                    "budget-exhausted",
                    "cancelled",
                    "internal",
                ]
            },
            "message": {"type": "string", "minLength": 1},
            "retryable": {"type": "boolean"},
            "details": {"$ref": "#/$defs/canonicalMap"},
        },
        "additionalProperties": False,
    }
    result_data = {
        "type": "object",
        "required": [
            "lineage",
            "action",
            "disposition",
            "output_refs",
            "payload",
            "resource_usage",
            "failure",
        ],
        "properties": {
            "lineage": {"type": "array", "items": {"$ref": "#/$defs/recordRef"}},
            "action": {"const": action.to_dict()},
            "disposition": (
                {"const": "succeeded"}
                if action.kind == "verify-applied-target"
                else {"enum": ["succeeded", "failed", "cancelled"]}
            ),
            "output_refs": {
                "type": "array",
                "uniqueItems": True,
                "items": {"$ref": "#/$defs/recordRef"},
            },
            "payload": {"type": "object"},
            "resource_usage": _resource_usage_schema(action),
            "failure": {"anyOf": [{"type": "null"}, {"$ref": "#/$defs/runtimeFailure"}]},
        },
        "allOf": [
            {
                "if": {"properties": {"disposition": {"const": "succeeded"}}},
                "then": {
                    "properties": {
                        "output_refs": _output_refs(output_types),
                        "payload": _payload_map(payload_name, success_record),
                        "failure": {"type": "null"},
                    }
                },
                "else": {
                    "properties": {
                        "output_refs": {"type": "array", "maxItems": 0},
                        "payload": _empty_payload_map(),
                        "failure": {"$ref": "#/$defs/runtimeFailure"},
                    }
                },
            },
            {
                "if": {"properties": {"disposition": {"const": "cancelled"}}},
                "then": {
                    "properties": {
                        "failure": {
                            "allOf": [
                                {"$ref": "#/$defs/runtimeFailure"},
                                {
                                    "properties": {
                                        "data": {
                                            "properties": {"classification": {"const": "cancelled"}}
                                        }
                                    }
                                },
                            ]
                        }
                    }
                },
            },
        ],
        "additionalProperties": False,
    }
    return {
        "$schema": _DRAFT,
        "$id": f"librsi.action-result/v1/{action.root}",
        **_record_envelope("action_result", result_data),
        "$defs": {
            "plainValue": _plain_value(),
            "canonicalValue": {
                "anyOf": [
                    {"type": ["null", "boolean", "number", "string"]},
                    {
                        "type": "array",
                        "items": {"$ref": "#/$defs/canonicalValue"},
                    },
                    {"$ref": "#/$defs/canonicalMap"},
                ]
            },
            "canonicalMap": _canonical_map(),
            "amountMap": _canonical_map(amounts=True),
            "recordRef": _record_ref(),
            "runtimeFailure": _record_envelope("runtime_failure", failure_data),
        },
    }
