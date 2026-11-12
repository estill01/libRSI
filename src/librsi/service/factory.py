"""Explicit process-owner composition for the HTTP and MCP executables."""

from __future__ import annotations

from importlib import import_module

from .facade import LibRSIService
from .records import ServiceLimits


def load_service_factory(
    specification: str, *, data_directory: str, limits: ServiceLimits
) -> LibRSIService:
    """Load trusted startup code. Never expose this operation as a client tool."""
    module, separator, name = specification.partition(":")
    if not separator or not module or not name.isidentifier():
        raise ValueError("service factory must be module:callable")
    factory = getattr(import_module(module), name)
    if not callable(factory):
        raise TypeError("service factory must be callable")
    service = factory(data_directory=data_directory, limits=limits)
    if type(service) is not LibRSIService:
        raise TypeError("service factory must return LibRSIService")
    if service.limits != limits:
        service.close()
        raise ValueError("service factory must preserve configured service limits")
    return service
