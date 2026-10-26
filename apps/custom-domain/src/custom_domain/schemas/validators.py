# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Field validators shared by the request schemas."""

from custom_domain.services.upstream import InvalidUpstreamError, parse_upstream


def validate_upstream(value: str | None) -> str | None:
    """Accept a Unix socket path or ``host:port`` and reject anything else.

    Raises:
        ValueError: If the value is not a valid upstream target (Pydantic turns it
            into a ``422`` answer)
    """
    if value is None:
        return value
    try:
        parse_upstream(value)
    except InvalidUpstreamError as error:
        raise ValueError(str(error)) from error
    return value.strip()
