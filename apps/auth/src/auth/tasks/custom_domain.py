# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Custom domain provisioning tasks."""

import logging
import os
import socket
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select, update

from auth.celery import celery_app
from auth.config import settings
from auth.db.models.tenant import CustomDomainStatus
from auth.services.custom_domain import DOMAIN_PATTERN

logger = logging.getLogger(__name__)

_SSL_CIPHERS = (
    "ECDHE-ECDSA-AES128-GCM-SHA256:"
    "ECDHE-RSA-AES128-GCM-SHA256:"
    "ECDHE-ECDSA-AES256-GCM-SHA384:"
    "ECDHE-RSA-AES256-GCM-SHA384"
)

# Nginx config template for custom domain
NGINX_TEMPLATE = """# Custom domain configuration for {domain}
# Tenant: {tenant_slug}
# Generated: {timestamp}

upstream {upstream_name} {{
    server unix:{upstream_socket} max_fails=3 fail_timeout=10s;
    keepalive 32;
}}

server {{
    listen {listen_ipv4}:80;
    listen [{listen_ipv6}]:80;
    server_name {domain};

    # ACME challenge for certificate renewal
    location /.well-known/acme-challenge/ {{
        root /var/www/certbot;
        allow all;
    }}

    # Redirect all HTTP to HTTPS
    location / {{
        return 301 https://$host$request_uri;
    }}
}}

server {{
    listen {listen_ipv4}:443 ssl;
    listen [{listen_ipv6}]:443 ssl;
    http2 on;
    server_name {domain};

    # SSL certificates (managed by certbot)
    ssl_certificate /etc/letsencrypt/live/{domain}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{domain}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers {ssl_ciphers};
    ssl_prefer_server_ciphers off;

    # HSTS
    add_header Strict-Transport-Security "max-age=63072000" always;

    # Proxy to auth service via Unix socket
    location / {{
        proxy_pass http://{upstream_name};
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }}
}}
"""

# HTTP-only template for initial certbot setup
NGINX_HTTP_TEMPLATE = """# HTTP-only configuration for certbot setup
# Domain: {domain}
# Tenant: {tenant_slug}
# Generated: {timestamp}
# Upstream: {upstream_name} -> {upstream_socket}

server {{
    listen {listen_ipv4}:80;
    listen [{listen_ipv6}]:80;
    server_name {domain};

    # ACME challenge for certificate provisioning
    location /.well-known/acme-challenge/ {{
        root /var/www/certbot;
        allow all;
    }}

    # Temporary 503 while waiting for SSL
    location / {{
        return 503;
    }}
}}
"""


def _validate_domain(domain: str) -> bool:
    """Validate domain format.

    Args:
        domain: Domain to validate.

    Returns:
        True if valid, False otherwise.
    """
    return bool(DOMAIN_PATTERN.match(domain))


def _check_dns_cname(domain: str, expected_target: str) -> tuple[bool, str]:
    """Check if domain has correct CNAME record.

    Args:
        domain: Domain to check.
        expected_target: Expected CNAME target.

    Returns:
        Tuple of (is_valid, message).
    """
    try:
        import dns.resolver

        try:
            answers = dns.resolver.resolve(domain, "CNAME")
            for rdata in answers:
                cname_target = str(rdata.target).rstrip(".")
                if cname_target.lower() == expected_target.lower():
                    return True, f"CNAME correctly points to {expected_target}"
                # Check if it points to the expected target (may have trailing dot)
                if cname_target.lower() == expected_target.lower().rstrip("."):
                    return True, f"CNAME correctly points to {expected_target}"

            # CNAME exists but points elsewhere
            actual_targets = [str(r.target).rstrip(".") for r in answers]
            return False, f"CNAME points to {', '.join(actual_targets)}, expected {expected_target}"

        except dns.resolver.NoAnswer:
            # No CNAME record, check if A record exists
            try:
                dns.resolver.resolve(domain, "A")
                return (
                    False,
                    f"Domain has A record(s) but no CNAME. "
                    f"Please remove A records and "
                    f"add CNAME to {expected_target}",
                )
            except dns.resolver.NoAnswer:
                return (
                    False,
                    f"No DNS records found. Please add CNAME record pointing to {expected_target}",
                )

        except dns.resolver.NXDOMAIN:
            return (
                False,
                f"Domain does not exist. Please add CNAME record pointing to {expected_target}",
            )

    except ImportError:
        # Fallback: use socket to check if domain resolves
        logger.warning("dnspython not installed, using socket fallback for DNS check")
        try:
            socket.gethostbyname(domain)
            return (
                True,
                "Domain resolves (CNAME verification skipped - install dnspython for full check)",
            )
        except socket.gaierror:
            return (
                False,
                f"Domain does not resolve. Please add CNAME record pointing to {expected_target}",
            )


def _write_nginx_config(domain: str, tenant_slug: str, ssl_ready: bool = False) -> tuple[bool, str]:
    """Write nginx configuration for domain.

    Args:
        domain: Domain to configure.
        tenant_slug: Tenant slug for comments.
        ssl_ready: Whether SSL certificate is ready.

    Returns:
        Tuple of (success, message).
    """
    sites_dir = Path(settings.custom_domain_nginx_sites_dir)
    if not sites_dir.exists():
        return False, f"Nginx sites directory does not exist: {sites_dir}"

    # Get server IPs from settings
    listen_ipv4 = settings.custom_domain_nginx_ipv4
    listen_ipv6 = settings.custom_domain_nginx_ipv6

    if not listen_ipv4 or not listen_ipv6:
        return (
            False,
            "Nginx server IPs not configured (custom_domain_nginx_ipv4, custom_domain_nginx_ipv6)",
        )

    # Get upstream socket
    upstream_socket = settings.custom_domain_upstream_socket
    if not upstream_socket:
        return False, "Upstream socket not configured (custom_domain_upstream_socket)"

    # Generate unique upstream name from domain (replace dots/dashes with underscores)
    upstream_name = f"custom_{domain.replace('.', '_').replace('-', '_')}"

    config_path = sites_dir / f"custom-domain-{domain}.conf"
    timestamp = datetime.now(UTC).isoformat()

    template = NGINX_TEMPLATE if ssl_ready else NGINX_HTTP_TEMPLATE
    config_content = template.format(
        domain=domain,
        tenant_slug=tenant_slug,
        timestamp=timestamp,
        listen_ipv4=listen_ipv4,
        listen_ipv6=listen_ipv6,
        upstream_name=upstream_name,
        upstream_socket=upstream_socket,
        ssl_ciphers=_SSL_CIPHERS,
    )

    try:
        # Write to temp file first, then use sudo to move it
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as tmp:
            tmp.write(config_content)
            tmp_path = tmp.name

        # Use sudo to copy the file to nginx sites directory
        result = subprocess.run(
            ["/usr/bin/sudo", "cp", tmp_path, str(config_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        os.unlink(tmp_path)  # Clean up temp file

        if result.returncode != 0:
            return False, f"Failed to write nginx config: {result.stderr}"

        logger.info(f"Wrote nginx config to {config_path}")
        return True, f"Nginx configuration written to {config_path}"
    except OSError as e:
        return False, f"Failed to write nginx config: {e}"


def _reload_nginx() -> tuple[bool, str]:
    """Reload nginx configuration.

    Returns:
        Tuple of (success, message).
    """
    try:
        # Test configuration first (requires sudo)
        result = subprocess.run(
            ["/usr/bin/sudo", "/usr/sbin/nginx", "-t"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return False, f"Nginx config test failed: {result.stderr}"

        # Reload nginx (requires sudo)
        result = subprocess.run(
            ["/usr/bin/sudo", "/usr/bin/systemctl", "reload", "nginx"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return False, f"Nginx reload failed: {result.stderr}"

        return True, "Nginx reloaded successfully"
    except subprocess.TimeoutExpired:
        return False, "Nginx command timed out"
    except FileNotFoundError:
        return False, "sudo, nginx or systemctl command not found"
    except Exception as e:
        return False, f"Nginx reload error: {e}"


def _run_certbot(domain: str, email: str) -> tuple[bool, str]:
    """Run certbot to obtain SSL certificate.

    Args:
        domain: Domain to get certificate for.
        email: Email for certbot notifications.

    Returns:
        Tuple of (success, message).
    """
    if not email:
        return False, "Certbot email not configured"

    # Ensure certbot webroot exists (may need sudo if doesn't exist)
    webroot = Path("/var/www/certbot")
    if not webroot.exists():
        subprocess.run(["/usr/bin/sudo", "mkdir", "-p", "/var/www/certbot"], check=False)

    try:
        result = subprocess.run(
            [
                "/usr/bin/sudo",
                "/usr/bin/certbot",
                "certonly",
                "--webroot",
                "-w",
                "/var/www/certbot",
                "-d",
                domain,
                "--email",
                email,
                "--agree-tos",
                "--non-interactive",
                "--keep-until-expiring",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode == 0:
            return True, "SSL certificate obtained successfully"

        # Check for common errors
        stderr = result.stderr.lower()
        if "rate limit" in stderr:
            return False, "Certbot rate limit exceeded. Please try again later."
        if "unauthorized" in stderr or "invalid response" in stderr:
            return False, "Domain verification failed. Ensure DNS is correctly configured."
        if "connection refused" in stderr:
            return False, "Certbot could not connect. Ensure nginx is running."

        return False, f"Certbot failed: {result.stderr}"

    except subprocess.TimeoutExpired:
        return False, "Certbot command timed out"
    except FileNotFoundError:
        return False, "certbot command not found. Please install certbot."
    except Exception as e:
        return False, f"Certbot error: {e}"


def _update_tenant_status(
    tenant_id: str,
    status: CustomDomainStatus,
    error: str | None = None,
    dns_verified: bool = False,
    ssl_provisioned: bool = False,
) -> None:
    """Update tenant custom domain status in database.

    Args:
        tenant_id: Tenant UUID.
        status: New status.
        error: Error message (if failed).
        dns_verified: Set dns verified timestamp.
        ssl_provisioned: Set ssl provisioned timestamp.
    """
    # Import here to avoid circular imports and celery issues
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from auth.core.database import get_sync_database_url
    from auth.db.models.tenant import Tenant

    # Create sync engine for Celery task
    engine = create_engine(get_sync_database_url(settings.database_url))

    with Session(engine) as session:
        now = datetime.now(UTC)
        update_values: dict[str, Any] = {
            "custom_domain_status": status,
            "custom_domain_checked_at": now,
            "custom_domain_error": error,
        }

        if dns_verified:
            update_values["custom_domain_verified_at"] = now

        if ssl_provisioned:
            update_values["custom_domain_ssl_at"] = now

        stmt = update(Tenant).where(Tenant.id == tenant_id).values(**update_values)
        session.execute(stmt)
        session.commit()


@celery_app.task(name="verify_custom_domain_dns", bind=True, max_retries=3, ignore_result=True)
def verify_custom_domain_dns(
    self,
    tenant_id: str,
    domain: str,
    tenant_slug: str,
) -> dict[str, Any]:
    """Verify DNS configuration for custom domain.

    Args:
        tenant_id: Tenant UUID.
        domain: Custom domain to verify.
        tenant_slug: Tenant slug for logging.

    Returns:
        Dict with status and details.
    """
    logger.info(f"Verifying DNS for domain {domain} (tenant: {tenant_slug})")

    # Validate domain format
    if not _validate_domain(domain):
        error_msg = f"Invalid domain format: {domain}"
        logger.error(error_msg)
        _update_tenant_status(tenant_id, CustomDomainStatus.FAILED, error=error_msg)
        return {"status": "failed", "error": error_msg}

    # Get expected CNAME target
    cname_target = settings.custom_domain_cname_target
    if not cname_target:
        error_msg = "CNAME target not configured"
        logger.error(error_msg)
        _update_tenant_status(tenant_id, CustomDomainStatus.FAILED, error=error_msg)
        return {"status": "failed", "error": error_msg}

    # Update status to verifying
    _update_tenant_status(tenant_id, CustomDomainStatus.DNS_VERIFYING)

    # Check DNS
    dns_valid, dns_message = _check_dns_cname(domain, cname_target)
    logger.info(f"DNS check for {domain}: valid={dns_valid}, message={dns_message}")

    if not dns_valid:
        # DNS not ready yet, schedule retry
        _update_tenant_status(tenant_id, CustomDomainStatus.PENDING, error=dns_message)
        try:
            # Retry in 5 minutes with exponential backoff
            countdown = 300 * (2**self.request.retries)
            self.retry(countdown=countdown)
        except self.MaxRetriesExceededError:
            logger.warning(f"Max retries exceeded for DNS verification of {domain}")
            _update_tenant_status(
                tenant_id,
                CustomDomainStatus.PENDING,
                error=f"{dns_message}. Automatic verification stopped - please verify manually.",
            )
        return {"status": "pending", "message": dns_message}

    # DNS verified! Update status and trigger SSL provisioning
    logger.info(f"DNS verified for {domain}")
    _update_tenant_status(tenant_id, CustomDomainStatus.DNS_VERIFIED, dns_verified=True)

    # Trigger SSL provisioning
    provision_custom_domain_ssl.delay(tenant_id, domain, tenant_slug)

    return {"status": "dns_verified", "message": dns_message}


@celery_app.task(name="provision_custom_domain_ssl", bind=True, max_retries=2, ignore_result=True)
def provision_custom_domain_ssl(
    self,
    tenant_id: str,
    domain: str,
    tenant_slug: str,
) -> dict[str, Any]:
    """Provision SSL certificate for custom domain.

    Args:
        tenant_id: Tenant UUID.
        domain: Custom domain to provision.
        tenant_slug: Tenant slug for logging.

    Returns:
        Dict with status and details.
    """
    logger.info(f"Provisioning SSL for domain {domain} (tenant: {tenant_slug})")

    # Update status
    _update_tenant_status(tenant_id, CustomDomainStatus.SSL_PROVISIONING)

    # Step 1: Write HTTP-only nginx config for certbot
    success, message = _write_nginx_config(domain, tenant_slug, ssl_ready=False)
    if not success:
        logger.error(f"Failed to write nginx HTTP config: {message}")
        _update_tenant_status(tenant_id, CustomDomainStatus.FAILED, error=message)
        return {"status": "failed", "error": message}

    # Step 2: Reload nginx
    success, message = _reload_nginx()
    if not success:
        logger.error(f"Failed to reload nginx: {message}")
        _update_tenant_status(tenant_id, CustomDomainStatus.FAILED, error=message)
        return {"status": "failed", "error": message}

    # Step 3: Run certbot (if enabled)
    if settings.custom_domain_certbot_enabled:
        success, message = _run_certbot(domain, settings.custom_domain_certbot_email)
        if not success:
            logger.error(f"Certbot failed: {message}")
            # Retry with backoff
            try:
                countdown = 300 * (2**self.request.retries)
                self.retry(countdown=countdown)
            except self.MaxRetriesExceededError:
                _update_tenant_status(tenant_id, CustomDomainStatus.FAILED, error=message)
            return {"status": "failed", "error": message}

        # Step 4: Write full nginx config with SSL
        success, message = _write_nginx_config(domain, tenant_slug, ssl_ready=True)
        if not success:
            logger.error(f"Failed to write nginx SSL config: {message}")
            _update_tenant_status(tenant_id, CustomDomainStatus.FAILED, error=message)
            return {"status": "failed", "error": message}

        # Step 5: Reload nginx again
        success, message = _reload_nginx()
        if not success:
            logger.error(f"Failed to reload nginx after SSL: {message}")
            _update_tenant_status(tenant_id, CustomDomainStatus.FAILED, error=message)
            return {"status": "failed", "error": message}

    # Success!
    logger.info(f"Custom domain {domain} fully provisioned")
    _update_tenant_status(tenant_id, CustomDomainStatus.ACTIVE, ssl_provisioned=True)

    return {"status": "active", "message": f"Domain {domain} is now active"}


@celery_app.task(name="check_pending_custom_domains", ignore_result=True)
def check_pending_custom_domains() -> dict[str, Any]:
    """Check all pending custom domains for DNS verification.

    This is called periodically by celery beat.

    Returns:
        Dict with status and count of domains checked.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from auth.core.database import get_sync_database_url
    from auth.db.models.tenant import Tenant

    logger.info("Checking pending custom domains")

    # Create sync engine
    engine = create_engine(get_sync_database_url(settings.database_url))

    checked_count = 0
    with Session(engine) as session:
        # Find tenants with pending custom domains
        stmt = select(Tenant).where(
            Tenant.custom_domain.isnot(None),
            Tenant.custom_domain_status.in_(
                [
                    CustomDomainStatus.PENDING,
                    CustomDomainStatus.DNS_VERIFYING,
                ]
            ),
            Tenant.is_active.is_(True),
        )
        tenants = session.execute(stmt).scalars().all()

        for tenant in tenants:
            # Check if we should skip (checked recently)
            if tenant.custom_domain_checked_at:
                minutes_since_check = (
                    datetime.now(UTC) - tenant.custom_domain_checked_at
                ).total_seconds() / 60
                if minutes_since_check < settings.custom_domain_dns_check_interval_minutes:
                    continue

            logger.info(f"Triggering DNS check for {tenant.custom_domain} (tenant: {tenant.slug})")
            verify_custom_domain_dns.delay(
                str(tenant.id),
                tenant.custom_domain,
                tenant.slug,
            )
            checked_count += 1

    logger.info(f"Triggered DNS check for {checked_count} pending domains")
    return {"status": "completed", "checked_count": checked_count}


@celery_app.task(name="remove_custom_domain_config", bind=True, max_retries=2, ignore_result=True)
def remove_custom_domain_config(
    self,
    domain: str,
    tenant_slug: str,
) -> dict[str, Any]:
    """Remove nginx configuration for a custom domain.

    Called when a custom domain is removed from a tenant.

    Args:
        domain: Custom domain to remove.
        tenant_slug: Tenant slug for logging.

    Returns:
        Dict with status and details.
    """
    logger.info(f"Removing custom domain config for {domain} (tenant: {tenant_slug})")

    sites_dir = Path(settings.custom_domain_nginx_sites_dir)
    config_path = sites_dir / f"custom-domain-{domain}.conf"

    try:
        if config_path.exists():
            # Use sudo to remove the file
            result = subprocess.run(
                ["/usr/bin/sudo", "rm", "-f", str(config_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                logger.warning(f"Failed to remove nginx config: {result.stderr}")
            else:
                logger.info(f"Removed nginx config: {config_path}")

            # Reload nginx
            success, message = _reload_nginx()
            if not success:
                logger.warning(f"Failed to reload nginx after removing config: {message}")

        return {"status": "removed", "domain": domain}

    except Exception as e:
        logger.error(f"Failed to remove config for {domain}: {e}")
        import contextlib

        with contextlib.suppress(self.MaxRetriesExceededError):
            self.retry(countdown=60)
        return {"status": "failed", "error": str(e)}
