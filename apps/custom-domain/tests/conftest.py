# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Pytest configuration and fixtures."""

import asyncio
from collections.abc import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from custom_domain.auth.models import User
from custom_domain.database import get_db
from custom_domain.main import app
from httpx import ASGITransport, AsyncClient


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def deployment_settings(monkeypatch, tmp_path):
    """Give the settings that have no default the values a deployment would provide."""
    from custom_domain.config import settings

    staging = tmp_path / "staging"
    staging.mkdir()
    values = {
        "nginx_sites_dir": str(tmp_path / "sites-enabled"),
        "nginx_config_prefix": "custom-domain-",
        "nginx_bin": "/usr/sbin/nginx",
        "nginx_service": "nginx",
        "systemctl_bin": "/usr/bin/systemctl",
        "certbot_bin": "/usr/bin/certbot",
        "openssl_bin": "/usr/bin/openssl",
        "certbot_email": "ops@example.invalid",
        "certbot_webroot": "/srv/acme",
        "letsencrypt_dir": "/srv/letsencrypt",
        "sudo_bin": "sudo",
        "privileged_helper": "/opt/custom-domain/privileged-helper",
        "privileged_staging_dir": str(staging),
    }
    for name, value in values.items():
        monkeypatch.setattr(settings, name, value)
    return settings


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.scalar = AsyncMock(return_value=None)
    session.scalars = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def test_user() -> User:
    """Create a test user with standard scopes."""
    return User(
        id=uuid4(),
        email="test@example.com",
        name="Test User",
        scopes=["custom-domain:read", "custom-domain:write", "custom-domain:lookup"],
        is_machine_client=False,
        client_id="test-client-id",
    )


@pytest.fixture
def admin_user() -> User:
    """Create an admin user with all scopes."""
    return User(
        id=uuid4(),
        email="admin@example.com",
        name="Admin User",
        scopes=[
            "custom-domain:admin",
            "custom-domain:admin:clients",
            "custom-domain:admin:templates",
            "custom-domain:admin:stats",
            "custom-domain:read",
            "custom-domain:write",
            "custom-domain:lookup",
        ],
        is_machine_client=False,
        client_id="admin-client-id",
    )


@pytest.fixture
def machine_user() -> User:
    """Create a machine/service account user."""
    return User(
        id="service-account",
        email=None,
        name=None,
        scopes=["custom-domain:read", "custom-domain:lookup"],
        is_machine_client=True,
        client_id="service-client-id",
    )


@pytest.fixture
def other_user() -> User:
    """Create a user from a different client."""
    return User(
        id=uuid4(),
        email="other@example.com",
        name="Other User",
        scopes=["custom-domain:read", "custom-domain:write", "custom-domain:lookup"],
        is_machine_client=False,
        client_id="other-client-id",
    )


def _create_jwt_claims(user: User) -> dict:
    """Create JWT claims from a User object."""
    return {
        "sub": str(user.id),
        "email": user.email,
        "name": user.name,
        "scope": " ".join(user.scopes) if user.scopes else "",
        "client_id": user.client_id,
    }


def _setup_auth_mocks(user: User):
    """Set up authentication mocks for a given user."""
    claims = _create_jwt_claims(user)

    jwks_patcher = patch("custom_domain.auth.dependencies.jwks_manager")
    introspection_patcher = patch("custom_domain.auth.dependencies.introspection_client")
    exchange_patcher = patch("custom_domain.auth.dependencies.token_exchange_client")

    mock_jwks = jwks_patcher.start()
    mock_introspection = introspection_patcher.start()
    mock_exchange = exchange_patcher.start()

    mock_jwks.is_configured = True
    mock_jwks.validate_token = AsyncMock(return_value=claims)

    mock_introspection.validate_token_with_introspection = AsyncMock(return_value=claims)
    mock_introspection.validate_opaque_token = AsyncMock(return_value=claims)

    mock_exchange.is_configured = False

    return jwks_patcher, introspection_patcher, exchange_patcher


@pytest_asyncio.fixture
async def client(mock_db_session) -> AsyncGenerator[AsyncClient, None]:
    """Create test HTTP client with mocked database (no auth)."""

    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_client(mock_db_session, test_user: User) -> AsyncGenerator[AsyncClient, None]:
    """Create test HTTP client with authenticated user."""

    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db

    patchers = _setup_auth_mocks(test_user)

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer header.payload.signature"},
        ) as test_client:
            yield test_client
    finally:
        for p in patchers:
            p.stop()
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_client_other(mock_db_session, other_user: User) -> AsyncGenerator[AsyncClient, None]:
    """Create test HTTP client with user from different client."""

    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db

    patchers = _setup_auth_mocks(other_user)

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer header.payload.signature"},
        ) as test_client:
            yield test_client
    finally:
        for p in patchers:
            p.stop()
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_client(mock_db_session, admin_user: User) -> AsyncGenerator[AsyncClient, None]:
    """Create test HTTP client with admin user."""

    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db

    patchers = _setup_auth_mocks(admin_user)

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer header.payload.signature"},
        ) as test_client:
            yield test_client
    finally:
        for p in patchers:
            p.stop()
        app.dependency_overrides.clear()


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    mock = MagicMock()
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock()
    mock.setex = AsyncMock()
    mock.delete = AsyncMock()
    mock.lrange = AsyncMock(return_value=[])
    mock.llen = AsyncMock(return_value=0)
    mock.lpush = AsyncMock()
    mock.close = AsyncMock()
    mock.aclose = AsyncMock()
    return mock


@pytest.fixture
def mock_subprocess():
    """Mock asyncio subprocess for certbot/nginx."""
    with patch("asyncio.create_subprocess_exec") as mock:
        process = AsyncMock()
        process.returncode = 0
        process.communicate = AsyncMock(return_value=(b"", b""))
        mock.return_value = process
        yield mock


@pytest.fixture
def mock_httpx():
    """Mock httpx client for external API calls."""
    with patch("httpx.AsyncClient") as mock:
        client_instance = AsyncMock()
        mock.return_value.__aenter__ = AsyncMock(return_value=client_instance)
        mock.return_value.__aexit__ = AsyncMock()
        yield client_instance


@pytest.fixture
def sample_client_data():
    """Sample authorized client data."""
    return {
        "id": 1,
        "client_id": f"test-client-{uuid4().hex[:8]}",
        "name": "Test Client",
        "description": "Test client for testing",
        "default_upstream_target": "unix:/var/run/app.sock",
        "default_cname_target": "apps.example.com",
        "max_domains": 10,
        "is_active": True,
    }


@pytest.fixture
def sample_template_data():
    """Sample nginx template data."""
    return {
        "id": 1,
        "slug": f"template-{uuid4().hex[:8]}",
        "name": "Default Template",
        "description": "Default nginx template",
        "http_template": "server { listen 80; server_name {{ domain }}; }",
        "https_template": "server { listen 443 ssl; server_name {{ domain }}; }",
        "is_default": True,
        "is_active": True,
        "available_variables": ["domain", "upstream"],
    }


@pytest.fixture
def sample_domain_data(test_user):
    """Sample custom domain data."""
    return {
        "id": 1,
        "domain": f"test-{uuid4().hex[:8]}.example.com",
        "client_id": test_user.client_id,
        "owner_id": "org_123",
        "owner_type": "organization",
        "upstream_target": "unix:/var/run/app.sock",
        "cname_target": "apps.example.com",
        "status": "pending",
    }


@pytest.fixture
def mock_authorized_client(sample_client_data):
    """Create a mock AuthorizedClient model."""
    from datetime import UTC, datetime

    from custom_domain.models import AuthorizedClient

    client = MagicMock(spec=AuthorizedClient)
    for key, value in sample_client_data.items():
        setattr(client, key, value)
    # Add optional fields that may be accessed
    client.metadata_ = None
    client.default_nginx_template_id = None
    client.created_at = datetime.now(UTC)
    client.updated_at = datetime.now(UTC)
    return client


@pytest.fixture
def mock_nginx_template(sample_template_data):
    """Create a mock NginxTemplate model."""
    from custom_domain.models import NginxTemplate

    template = MagicMock(spec=NginxTemplate)
    for key, value in sample_template_data.items():
        setattr(template, key, value)
    return template


@pytest.fixture
def mock_custom_domain(sample_domain_data):
    """Create a mock CustomDomain model."""
    from datetime import UTC, datetime

    from custom_domain.models import CustomDomain
    from custom_domain.models.enums import DomainStatus

    domain = MagicMock(spec=CustomDomain)
    for key, value in sample_domain_data.items():
        setattr(domain, key, value)
    # Add optional fields that may be accessed
    domain.deleted_at = None
    domain.error_message = None
    domain.error = None
    domain.metadata_ = None
    domain.nginx_template_id = None
    domain.verification_token = "test-token"
    domain.ssl_certificate_expires = None
    domain.status = DomainStatus.PENDING
    domain.created_at = datetime.now(UTC)
    domain.updated_at = datetime.now(UTC)
    return domain


@pytest.fixture
def test_domain(mock_custom_domain):
    """Alias for mock_custom_domain - used by existing tests."""
    return mock_custom_domain


@pytest.fixture
def test_engine():
    """Mock database engine for tests that need it."""
    engine = MagicMock()
    engine.dispose = AsyncMock()
    return engine


@pytest.fixture
def db_session(mock_db_session):
    """Alias for mock_db_session - used by existing tests."""
    return mock_db_session


@pytest.fixture
def sample_client(mock_authorized_client):
    """Alias for mock_authorized_client."""
    return mock_authorized_client


@pytest.fixture
def sample_template(mock_nginx_template):
    """Alias for mock_nginx_template."""
    return mock_nginx_template


@pytest.fixture
def sample_domain(mock_custom_domain):
    """Alias for mock_custom_domain."""
    return mock_custom_domain
