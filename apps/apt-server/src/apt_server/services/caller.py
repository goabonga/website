# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Resolve the FastAPI ``AuthContext`` to the ACL-layer :class:`Caller`."""

from apt_server.acl.packages import Caller
from apt_server.auth.dependencies import AuthContext


def caller_from_auth(auth: AuthContext) -> Caller:
    """Return the caller identity used by the ACL checks."""
    scopes = frozenset(auth.scopes or [])
    groups_claim = getattr(auth.user, "groups", None) or []
    if isinstance(groups_claim, str):
        groups_claim = groups_claim.split()
    display_name = (
        getattr(auth.user, "email", None) or getattr(auth.user, "name", None) or auth.user_id
    )
    return Caller(
        sub=auth.user_id,
        scopes=scopes,
        groups=frozenset(groups_claim),
        display_name=str(display_name),
    )
