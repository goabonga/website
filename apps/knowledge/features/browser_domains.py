# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""The custom-domain service for the browser scenarios."""

from knowledge.services.custom_domain import RegisteredDomain


class CustomDomains:
    """Registers, verifies and deletes domains, recording what the pages ask of it."""

    def __init__(self):
        self.registered: list[tuple[str, str]] = []
        self.verified: list[str] = []
        self.deleted: list[str] = []
        self.error = None

    async def register(self, domain, owner_id):
        if self.error:
            raise self.error
        self.registered.append((domain, owner_id))
        return RegisteredDomain(
            id=f"service-{len(self.registered)}",
            domain=domain,
            status="pending",
            cname_target="cname.example.invalid",
        )

    async def verify(self, domain_id):
        if self.error:
            raise self.error
        self.verified.append(domain_id)
        return "dns_verifying"

    async def delete(self, domain_id):
        if self.error:
            raise self.error
        self.deleted.append(domain_id)
        return True
