"""External-agent admission, schemas, durable bindings, and controller."""

from .codec import error_document, response_document, serialize_response
from .controller import ExternalAgentController
from .records import CapabilityBinding, RunAdmissionBinding, TargetAdmission
from .schemas import (
    EXTERNAL_AGENT_SCHEMA,
    EXTERNAL_AGENT_SCHEMA_VERSION,
    EXTERNAL_ERROR_SCHEMA,
    action_result_schema,
    external_response_schema,
    target_admission_schema,
)
from .sqlite import AgentRunBinding, SQLiteAgentStore

__all__ = [
    "EXTERNAL_AGENT_SCHEMA",
    "EXTERNAL_AGENT_SCHEMA_VERSION",
    "EXTERNAL_ERROR_SCHEMA",
    "AgentRunBinding",
    "CapabilityBinding",
    "ExternalAgentController",
    "RunAdmissionBinding",
    "SQLiteAgentStore",
    "TargetAdmission",
    "action_result_schema",
    "error_document",
    "external_response_schema",
    "response_document",
    "serialize_response",
    "target_admission_schema",
]
