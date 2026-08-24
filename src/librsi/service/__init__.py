"""Transport-independent managed service projection."""

from .codec import (
    canonical_record_from_dict,
    knowledge_query_from_dict,
    knowledge_query_to_dict,
    require_json_size,
)
from .facade import LibRSIService, ServiceRequest
from .managed import ManagedServiceRunner
from .records import (
    SERVICE_SCHEMA,
    SERVICE_SCHEMA_VERSION,
    ManagedBounds,
    ManagedExecution,
    ServiceLimits,
)

__all__ = [
    "SERVICE_SCHEMA",
    "SERVICE_SCHEMA_VERSION",
    "LibRSIService",
    "ManagedBounds",
    "ManagedExecution",
    "ManagedServiceRunner",
    "ServiceLimits",
    "ServiceRequest",
    "canonical_record_from_dict",
    "knowledge_query_from_dict",
    "knowledge_query_to_dict",
    "require_json_size",
]
