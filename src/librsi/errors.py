class RSITransitionError(RuntimeError):
    """A requested improvement transition violates a safety invariant."""


class RSICapabilityError(RuntimeError):
    """Capability resolution or execution violated the dispatch contract."""
