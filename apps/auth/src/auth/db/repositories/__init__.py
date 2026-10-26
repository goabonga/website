# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Data access repositories.

Repositories encapsulate SQL queries and basic persistence operations
(select, insert, delete) for one model at a time. Repositories:

- Return SQLAlchemy model instances (not DTOs) so callers can mutate them
  and benefit from ORM relationships.
- Never commit the transaction. The caller (typically a service) owns the
  commit boundary.
- Are stateless and receive the ``AsyncSession`` as an argument on every
  call, so a single instance can be shared across requests.
- Contain no business logic, validation, hashing, or webhook dispatch —
  that is the service layer's responsibility.

Handlers should not import repositories directly; they call services which
in turn delegate SQL access to repositories.
"""
