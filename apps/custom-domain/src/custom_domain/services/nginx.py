# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Nginx configuration management service."""

from custom_domain.config import require_setting, settings
from custom_domain.logging import get_logger
from custom_domain.models.domain import CustomDomain
from custom_domain.models.template import NginxTemplate
from custom_domain.services.privileged import run_privileged, stage_file
from custom_domain.services.template import template_service
from custom_domain.services.upstream import parse_upstream

logger = get_logger(__name__)


class NginxManager:
    """Service for managing Nginx configurations.

    Files are never written to the sites directory by this process: the rendered
    configuration is staged and the privileged helper installs it, removes it,
    tests nginx and reloads it (see :mod:`custom_domain.services.privileged`).
    """

    def _config_filename(self, domain: str) -> str:
        """Generate the configuration filename for a domain."""
        return f"{settings.nginx_config_prefix}{domain}.conf"

    def _get_template_context(self, domain: CustomDomain) -> dict:
        """Build the template context for a domain.

        Args:
            domain: The CustomDomain instance

        Returns:
            Dictionary with template variables

        Raises:
            ConfigurationError: If the webroot or the certificate directory is not set
            InvalidUpstreamError: If the domain's upstream is neither a socket nor host:port
        """
        certificate_dir = f"{require_setting('letsencrypt_dir', settings)}/live/{domain.domain}"
        certbot_webroot = require_setting("certbot_webroot", settings)
        upstream = parse_upstream(domain.upstream_target)
        return {
            "domain": domain.domain,
            "upstream_target": domain.upstream_target,
            "upstream_server": upstream.nginx_server,
            "upstream_type": upstream.kind,
            "certbot_webroot": certbot_webroot,
            "ssl_certificate": f"{certificate_dir}/fullchain.pem",
            "ssl_certificate_key": f"{certificate_dir}/privkey.pem",
            "nginx_ipv4": settings.nginx_ipv4,
            "nginx_ipv6": settings.nginx_ipv6,
            "client_id": domain.client_id,
            "owner_id": domain.owner_id,
            "metadata": domain.metadata_ or {},
        }

    async def generate_http_config(
        self,
        domain: CustomDomain,
        template: NginxTemplate | None = None,
    ) -> str:
        """Generate HTTP-only nginx configuration for ACME challenge.

        Args:
            domain: The CustomDomain instance
            template: Optional custom template

        Returns:
            Rendered nginx configuration
        """
        context = self._get_template_context(domain)

        if template and template.http_template:
            return template_service.render_template(
                template.http_template,
                context,
            )

        return template_service.render_default_http(context)

    async def generate_https_config(
        self,
        domain: CustomDomain,
        template: NginxTemplate | None = None,
    ) -> str:
        """Generate full HTTPS nginx configuration.

        Args:
            domain: The CustomDomain instance
            template: Optional custom template

        Returns:
            Rendered nginx configuration
        """
        context = self._get_template_context(domain)

        if template and template.https_template:
            return template_service.render_template(
                template.https_template,
                context,
            )

        return template_service.render_default_https(context)

    async def write_config(self, domain: str, config: str) -> None:
        """Install the nginx configuration of a domain in the sites directory.

        Args:
            domain: The domain name
            config: The nginx configuration content

        Raises:
            RuntimeError: If the helper refuses or fails to install the file
        """
        logger.info("Installing nginx config for %s", domain)

        staged = stage_file(self._config_filename(domain), config)
        try:
            result = await run_privileged("write-config", domain)
        finally:
            staged.unlink(missing_ok=True)

        if not result.ok:
            raise RuntimeError(f"Failed to write nginx config: {result.stderr or 'Unknown error'}")

    async def remove_config(self, domain: str) -> None:
        """Remove nginx configuration for a domain.

        Args:
            domain: The domain name

        Raises:
            RuntimeError: If the helper fails to remove the file
        """
        logger.info("Removing nginx config for %s", domain)

        result = await run_privileged("remove-config", domain)
        if not result.ok:
            raise RuntimeError(f"Failed to remove nginx config: {result.stderr or 'Unknown error'}")

    async def test_config(self) -> tuple[bool, str]:
        """Test nginx configuration.

        Returns:
            Tuple of (is_valid, error_message)
        """
        result = await run_privileged("test-nginx")

        if not result.ok:
            error = result.stderr or "Unknown error"
            logger.error("Nginx config test failed: %s", error)
            return False, error

        logger.debug("Nginx config test passed")
        return True, ""

    async def reload(self) -> None:
        """Reload nginx configuration.

        Raises:
            RuntimeError: If the configuration test or the reload fails
        """
        # First test the configuration
        valid, error = await self.test_config()
        if not valid:
            raise RuntimeError(f"Nginx config test failed: {error}")

        result = await run_privileged("reload-nginx")
        if not result.ok:
            raise RuntimeError(f"Failed to reload nginx: {result.stderr or 'Unknown error'}")

        logger.info("Nginx reloaded successfully")


nginx_manager = NginxManager()
