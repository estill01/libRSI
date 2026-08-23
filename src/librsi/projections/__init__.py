"""Versioned external outcome and runtime-event projections."""

from .codec import (
    deserialize_projection,
    projection_from_dict,
    projection_to_dict,
    reconstruct_result,
    serialize_projection,
)
from .events import project_event, project_transition
from .outcomes import outcome_for_result, project_result, workflow_for_result
from .records import (
    EVENT_PROJECTION_SCHEMA,
    OUTCOME_PROJECTION_SCHEMA,
    PROJECTION_SCHEMA_VERSION,
    EventProjection,
    OutcomeProjection,
    Projection,
    ResultRecord,
)
from .schemas import (
    EVENT_PROJECTION_JSON_SCHEMA,
    OUTCOME_PROJECTION_JSON_SCHEMA,
    projection_schema,
)
from .store import (
    MemoryProjectionStore,
    ProjectionStore,
    load_projection,
    persist_projection,
)

__all__ = [
    "EVENT_PROJECTION_JSON_SCHEMA",
    "EVENT_PROJECTION_SCHEMA",
    "OUTCOME_PROJECTION_JSON_SCHEMA",
    "OUTCOME_PROJECTION_SCHEMA",
    "PROJECTION_SCHEMA_VERSION",
    "EventProjection",
    "MemoryProjectionStore",
    "OutcomeProjection",
    "Projection",
    "ProjectionStore",
    "ResultRecord",
    "deserialize_projection",
    "load_projection",
    "outcome_for_result",
    "persist_projection",
    "project_event",
    "project_result",
    "project_transition",
    "projection_from_dict",
    "projection_schema",
    "projection_to_dict",
    "reconstruct_result",
    "serialize_projection",
    "workflow_for_result",
]
