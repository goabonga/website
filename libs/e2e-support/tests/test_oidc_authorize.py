# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""The fake provider's authorization endpoint, login and consent pages."""

import contextlib
from html import unescape
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from e2e_support.oidc import Client, FakeOIDCProvider, SigningKey, User, pkce
from e2e_support.oidc.authorize import (
    SESSION_COOKIE,
    is_valid_redirect_uri,
    redirect_uri_registered,
)
from e2e_support.server import LiveServer

CALLBACK = "http://127.0.0.1:9/auth/callback"
VERIFIER = "v" * 43
KEY = SigningKey()  # generating a key is slow: share one between providers


def authorize_params(**overrides):
    params = {
        "response_type": "code",
        "client_id": "web",
        "redirect_uri": CALLBACK,
        "scope": "openid profile email",
        "state": "xyz",
        "code_challenge": pkce.challenge_for(VERIFIER),
        "code_challenge_method": "S256",
    }
    params.update(overrides)
    return {k: v for k, v in params.items() if v is not None}


def make_provider(**options):
    return FakeOIDCProvider(
        users=[
            User(email="ada@example.test", name="Ada", password="secret"),
            User(email="grace@example.test", name="Grace"),
        ],
        clients=[
            Client.public("web", ["http://127.0.0.1:*/auth/callback"]),
            Client.public("anywhere", [], require_pkce=False),
            Client("closed", redirect_uris=("https://app.example.test/cb",), is_active=False),
        ],
        signing_key=KEY,
        **options,
    )


@contextlib.contextmanager
def serve(provider):
    """Serve the provider and yield an HTTP client that does not follow redirects."""
    with (
        LiveServer(provider) as server,
        httpx.Client(base_url=server.url, follow_redirects=False) as client,
    ):
        client.provider = provider
        yield client


@pytest.fixture
def provider():
    return make_provider()


@pytest.fixture
def http(provider):
    with serve(provider) as client:
        yield client


@pytest.fixture
def auto_http():
    with serve(make_provider(auto_approve=True)) as client:
        yield client


def redirect_query(response):
    assert response.status_code in (302, 303), response.text
    location = urlparse(response.headers["location"])
    return location, {k: v[0] for k, v in parse_qs(location.query).items()}


def request_id(page):
    marker = 'name="request_id" value="'
    return page.split(marker)[1].split('"')[0]


def log_in(http, email="ada@example.test", password="secret", **params):
    page = http.get("/oauth2/authorize", params=authorize_params(**params))
    assert "Sign in" in page.text
    return http.post(
        "/oauth2/authorize/login",
        data={"request_id": request_id(page.text), "email": email, "password": password},
    )


# -- auto approve ---------------------------------------------------------------------


def test_auto_approve_redirects_with_a_code_and_echoes_the_state(auto_http):
    response = auto_http.get("/oauth2/authorize", params=authorize_params())
    location, query = redirect_query(response)
    assert f"{location.scheme}://{location.netloc}{location.path}" == CALLBACK
    assert query["state"] == "xyz"
    code = auto_http.provider.store.codes[query["code"]]
    assert code.user_id == next(iter(auto_http.provider.users))
    assert code.scopes == ["openid", "profile", "email"]
    assert code.code_challenge == pkce.challenge_for(VERIFIER)


def test_auto_approve_picks_the_user_named_by_login_hint(auto_http):
    response = auto_http.get(
        "/oauth2/authorize", params=authorize_params(login_hint="Grace@example.test")
    )
    _, query = redirect_query(response)
    grace = auto_http.provider.user_by_email("grace@example.test")
    assert auto_http.provider.store.codes[query["code"]].user_id == grace.id


def test_the_scope_defaults_to_openid_and_the_nonce_is_kept(auto_http):
    response = auto_http.get("/oauth2/authorize", params=authorize_params(scope=None, nonce="n-1"))
    _, query = redirect_query(response)
    code = auto_http.provider.store.codes[query["code"]]
    assert code.scopes == ["openid"]
    assert code.nonce == "n-1"


def test_auto_approve_without_a_user_is_an_error():
    provider = FakeOIDCProvider(clients=[Client.public("web")], auto_approve=True, signing_key=KEY)
    with LiveServer(provider) as server:
        response = httpx.get(f"{server.url}/oauth2/authorize", params=authorize_params())
    assert response.status_code == 400
    assert "no user is configured" in response.text


# -- login page -----------------------------------------------------------------------


def test_without_a_session_the_login_page_is_shown(http):
    response = http.get("/oauth2/authorize", params=authorize_params(login_hint="ada@example.test"))
    assert response.status_code == 200
    assert "<h1>Sign in</h1>" in response.text
    assert 'value="ada@example.test"' in response.text
    assert '<label for="password">Password</label>' in response.text


def test_logging_in_redirects_with_a_code_and_sets_the_session_cookie(http, provider):
    response = log_in(http)
    _, query = redirect_query(response)
    assert query["state"] == "xyz"
    ada = provider.user_by_email("ada@example.test")
    assert provider.store.codes[query["code"]].user_id == ada.id
    assert SESSION_COOKIE in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]


def test_a_wrong_password_shows_the_login_page_again(http, provider):
    response = log_in(http, password="wrong")
    assert response.status_code == 200
    assert 'role="alert"' in response.text
    assert "Invalid email or password." in response.text
    assert provider.store.codes == {}


def test_an_unknown_email_is_refused(http):
    assert "Invalid email or password." in log_in(http, email="nobody@example.test").text


def test_a_user_without_a_password_accepts_any_password(http):
    response = log_in(http, email="grace@example.test", password="whatever")
    assert "code" in redirect_query(response)[1]


def test_posting_an_unknown_request_is_an_error(http):
    response = http.post("/oauth2/authorize/login", data={"request_id": "nope"})
    assert response.status_code == 400
    assert "Unknown or expired authorization request" in response.text


def test_the_session_gives_single_sign_on(http, provider):
    log_in(http)
    response = http.get("/oauth2/authorize", params=authorize_params(state="second"))
    _, query = redirect_query(response)
    assert query["state"] == "second"


def test_prompt_login_asks_for_credentials_again(http):
    log_in(http)
    response = http.get("/oauth2/authorize", params=authorize_params(prompt="login"))
    assert "<h1>Sign in</h1>" in response.text


def test_prompt_none_without_a_session_is_login_required(http):
    response = http.get("/oauth2/authorize", params=authorize_params(prompt="none"))
    _, query = redirect_query(response)
    assert query["error"] == "login_required"
    assert query["state"] == "xyz"


def test_prompt_none_with_a_session_issues_a_code(http):
    log_in(http)
    response = http.get("/oauth2/authorize", params=authorize_params(prompt="none"))
    assert "code" in redirect_query(response)[1]


def test_ending_the_sessions_asks_for_a_login_again(http, provider):
    log_in(http)
    provider.end_sessions()
    assert "<h1>Sign in</h1>" in http.get("/oauth2/authorize", params=authorize_params()).text


# -- consent page ---------------------------------------------------------------------


@pytest.fixture
def consent_http():
    with serve(make_provider(require_consent=True)) as client:
        yield client


def test_consent_lists_the_scopes_and_allow_issues_the_code(consent_http):
    page = log_in(consent_http)
    assert page.status_code == 200
    assert "<h1>Authorize access</h1>" in page.text
    assert "<li>profile</li>" in page.text
    response = consent_http.post(
        "/oauth2/authorize/consent", data={"request_id": request_id(page.text), "decision": "allow"}
    )
    _, query = redirect_query(response)
    assert query["state"] == "xyz"
    assert query["code"] in consent_http.provider.store.codes


def test_denying_consent_returns_access_denied(consent_http):
    page = log_in(consent_http)
    response = consent_http.post(
        "/oauth2/authorize/consent", data={"request_id": request_id(page.text), "decision": "deny"}
    )
    _, query = redirect_query(response)
    assert query["error"] == "access_denied"
    assert query["state"] == "xyz"
    assert consent_http.provider.store.codes == {}


def test_consent_cannot_be_posted_without_a_login(consent_http):
    page = consent_http.get("/oauth2/authorize", params=authorize_params())
    response = consent_http.post(
        "/oauth2/authorize/consent",
        data={"request_id": request_id(page.text), "decision": "allow"},
    )
    assert response.status_code == 400


# -- request validation ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "error", "description"),
    [
        ({"response_type": None}, "invalid_request", "response_type is required"),
        ({"redirect_uri": None}, "invalid_request", "redirect_uri is required"),
        ({"response_type": "token"}, "unsupported_response_type", "Only 'code'"),
        ({"redirect_uri": "http://evil.example/cb"}, "invalid_request", "Invalid redirect_uri"),
        ({"redirect_uri": "no-scheme"}, "invalid_request", "Invalid redirect_uri"),
        ({"client_id": "ghost"}, "unauthorized_client", "Unknown or inactive client"),
        ({"client_id": "closed"}, "unauthorized_client", "Unknown or inactive client"),
        (
            {"redirect_uri": "http://127.0.0.1:9/elsewhere"},
            "invalid_request",
            "redirect_uri not registered for this client",
        ),
    ],
)
def test_untrustworthy_requests_get_an_error_page_not_a_redirect(
    http, overrides, error, description
):
    response = http.get("/oauth2/authorize", params=authorize_params(**overrides))
    assert response.status_code == 400
    assert error in response.text
    assert description in unescape(response.text)


@pytest.mark.parametrize(
    ("overrides", "error", "description"),
    [
        ({"scope": "openid billing:read"}, "invalid_scope", "scopes are not allowed"),
        ({"code_challenge": None}, "invalid_request", "PKCE is required"),
        ({"code_challenge_method": "S512"}, "invalid_request", "Invalid code_challenge_method"),
        ({"code_challenge": "short"}, "invalid_request", "Invalid code_challenge format"),
    ],
)
def test_other_problems_are_returned_to_the_application(http, overrides, error, description):
    response = http.get("/oauth2/authorize", params=authorize_params(**overrides))
    _, query = redirect_query(response)
    assert query["error"] == error
    assert description in query["error_description"]
    assert query["state"] == "xyz"


def test_the_challenge_method_defaults_to_s256(auto_http):
    response = auto_http.get(
        "/oauth2/authorize", params=authorize_params(code_challenge_method=None)
    )
    _, query = redirect_query(response)
    assert auto_http.provider.store.codes[query["code"]].code_challenge_method == "S256"


def test_a_client_that_does_not_require_pkce_may_omit_it(auto_http):
    response = auto_http.get(
        "/oauth2/authorize",
        params=authorize_params(
            client_id="anywhere", code_challenge=None, redirect_uri="https://x.test/cb"
        ),
    )
    _, query = redirect_query(response)
    assert auto_http.provider.store.codes[query["code"]].code_challenge is None


def test_authorization_requests_are_recorded(http, provider):
    http.get("/oauth2/authorize", params=authorize_params())
    record = provider.last_request("/oauth2/authorize")
    assert record.query["client_id"] == "web"
    assert record.status == 200


# -- helpers --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("uri", "valid"),
    [
        ("https://app.example.test/cb", True),
        ("http://localhost/cb", True),
        ("http://localhost:3000/cb", True),
        ("http://127.0.0.1:8000/cb", True),
        ("http://[::1]:8000/cb", True),
        ("http://app.example.test/cb", False),
        ("https:///cb", False),
        ("vpnclient://callback", True),
        ("/relative", False),
        ("", False),
    ],
)
def test_redirect_uri_format_follows_the_auth_application(uri, valid):
    assert is_valid_redirect_uri(uri) is valid


def test_registered_redirect_uris_are_exact_or_patterns():
    client = Client.public("c", ["https://a.test/cb", "http://127.0.0.1:*/auth/callback"])
    assert redirect_uri_registered(client, "https://a.test/cb")
    assert not redirect_uri_registered(client, "https://a.test/cb2")
    assert redirect_uri_registered(client, "http://127.0.0.1:51234/auth/callback")
    assert not redirect_uri_registered(client, "http://127.0.0.1:51234/other")
    assert redirect_uri_registered(Client.public("any"), "https://whatever.test/cb")


def test_pkce_s256_and_plain():
    verifier = "a" * 43
    assert pkce.verify(verifier, pkce.challenge_for(verifier))
    assert not pkce.verify("b" * 43, pkce.challenge_for(verifier))
    assert pkce.verify(verifier, verifier, "plain")
    assert not pkce.verify(verifier, verifier, "S512")
    assert pkce.challenge_for("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk") == (
        "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    )
    assert pkce.is_valid_verifier("a" * 43) and not pkce.is_valid_verifier("a" * 42)
    assert not pkce.is_valid_verifier("a" * 129)
    assert not pkce.is_valid_verifier("a" * 42 + " ")


# -- a real browser -------------------------------------------------------------------


@pytest.mark.browser
def test_a_browser_logs_in_through_the_login_page(browser_session, site):
    provider = make_provider()
    with LiveServer(provider) as server:
        scenario = browser_session.new_scenario("oidc login", base_url=server.url)
        try:
            redirect = f"{site.url}/auth/callback"
            params = authorize_params(redirect_uri=redirect)
            scenario.page.goto("/oauth2/authorize?" + httpx.QueryParams(params).__str__())
            scenario.page.get_by_label("Email").fill("ada@example.test")
            scenario.page.get_by_label("Password").fill("secret")
            scenario.page.get_by_role("button", name="Sign in").click()
            scenario.page.wait_for_url(f"{redirect}?*")
            query = parse_qs(urlparse(scenario.page.url).query)
            assert query["state"] == ["xyz"]
            assert query["code"][0] in provider.store.codes
        finally:
            scenario.close()
