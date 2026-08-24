"""Transport-only bearer authorization for the optional HTTP projection."""

from __future__ import annotations

import hmac
from dataclasses import dataclass

HTTP_PERMISSIONS = frozenset({"read", "mutate", "apply"})


@dataclass(frozen=True)
class HTTPTokenCredential:
    """One process configuration secret and its non-semantic permissions."""

    token: str
    permissions: frozenset[str]

    def __post_init__(self) -> None:
        if type(self.token) is not str or not self.token:
            raise ValueError("HTTP bearer token is required")
        permissions = frozenset(self.permissions)
        if not permissions or not permissions.issubset(HTTP_PERMISSIONS):
            raise ValueError("HTTP bearer token permissions are invalid")
        object.__setattr__(self, "permissions", permissions)


class HTTPTokenPolicy:
    """Fail-closed token policy kept outside canonical records and responses."""

    def __init__(self, credentials: tuple[HTTPTokenCredential, ...]) -> None:
        items = tuple(credentials)
        if not items or any(type(item) is not HTTPTokenCredential for item in items):
            raise TypeError("HTTP token policy requires credentials")
        if len({item.token for item in items}) != len(items):
            raise ValueError("HTTP bearer tokens must be unique")
        self._credentials = items

    @classmethod
    def from_tokens(
        cls,
        *,
        read_token: str | None = None,
        mutate_token: str | None = None,
        apply_token: str | None = None,
    ) -> HTTPTokenPolicy:
        combined: dict[str, set[str]] = {}
        for token, permissions in (
            (read_token, {"read"}),
            (mutate_token, {"read", "mutate"}),
            (apply_token, {"read", "mutate", "apply"}),
        ):
            if token is not None:
                if type(token) is not str or not token:
                    raise ValueError("configured HTTP bearer tokens cannot be empty")
                combined.setdefault(token, set()).update(permissions)
        return cls(
            tuple(
                HTTPTokenCredential(token, frozenset(permissions))
                for token, permissions in combined.items()
            )
        )

    def authorize(self, authorization: str | None, permission: str) -> None:
        if permission not in HTTP_PERMISSIONS:
            raise ValueError("unsupported HTTP permission")
        if authorization is None or not authorization.startswith("Bearer "):
            raise PermissionError("bearer authorization is required")
        supplied = authorization.removeprefix("Bearer ")
        for credential in self._credentials:
            if hmac.compare_digest(supplied, credential.token):
                if permission not in credential.permissions:
                    raise PermissionError("bearer token lacks the required permission")
                return
        raise PermissionError("bearer authorization is invalid")
