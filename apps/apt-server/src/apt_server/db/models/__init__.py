# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""SQLAlchemy models.

Every model must be imported here so that Alembic autogenerate can discover it
via ``Base.metadata``. Add new models to the imports below as they are created.
"""

from apt_server.db.models.acl import ACLRole, PackageACL
from apt_server.db.models.base import Base
from apt_server.db.models.index_cache import IndexCache
from apt_server.db.models.package import Package, PackageVisibility

__all__ = [
    "ACLRole",
    "Base",
    "IndexCache",
    "Package",
    "PackageACL",
    "PackageVisibility",
]
