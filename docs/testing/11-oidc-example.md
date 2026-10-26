# Worked example: logging in through OpenID Connect

This page wires everything together for an application that logs users in
through OpenID Connect: a [live server](01-live-server.md) for the
application, the [fake provider](07-fake-openid-provider.md) in place of the
auth application, the [behave hooks](05-behave-hooks.md) and the [generic
steps](06-steps.md). The example lives in the library tests
(`libs/e2e-support/tests/toy_oidc_app.py` and `behave_oidc_project/`) and is
run by `test_oidc_example.py`, so it is known to work.

## The toy application

`toy_oidc_app.create_app(config)` is a small FastAPI application that does
what `internal`, `knowledge` and `apt-server` do:

| Route | Behavior |
| --- | --- |
| `GET /auth/login` | Redirects to `{issuer}/oauth2/authorize` with a PKCE challenge (`S256`), a `state` and the `openid profile email offline_access` scopes; keeps `state` and the verifier in cookies |
| `GET /auth/callback` | Checks `state`, posts the code and verifier to `{issuer}/oauth2/token`, stores the access token in a cookie |
| `GET /dashboard` | Without a cookie, redirects to `/auth/login`. With one, verifies the signature against `{issuer}/.well-known/jwks.json`, asks `{issuer}/oauth2/introspect` whether the token is active, reads `{issuer}/userinfo`, and asks a token exchange whether the user holds `billing:read` to decide whether the navigation shows a Billing link |
| `GET /auth/logout` | Clears the cookie |

Its settings (`ToyConfig`: issuer, own base URL, client ids and secret) are
filled in once both servers run, exactly like the `OAUTH2_ISSUER`,
`APP_BASE_URL` and `OAUTH2_CLIENT_*` settings of a real application.

## Wiring the environment

```python
# features/environment.py
from e2e_support import behave_hooks as e2e
from e2e_support.oidc import Client, FakeOIDCProvider, User


def start_stack(context, scenario):
    servers = context.e2e.servers
    if "provider" not in servers:
        config = ToyConfig()
        provider = FakeOIDCProvider(
            users=[
                User(
                    email="ada@example.test",
                    name="Ada",
                    password="secret",
                    scopes=("billing:read",),
                ),
                User(email="grace@example.test", name="Grace", password="secret"),
            ],
            clients=[
                Client.service(
                    "toy-api",
                    "toy-api-secret",
                    ["openid", "profile", "email", "billing:*", "introspect"],
                )
            ],
        )
        config.issuer = e2e.live_server(context, "provider", provider).url
        config.base_url = e2e.live_server(context, "app", create_app(config)).url
        # the redirect URI is only known once the application listens
        provider.add_client(Client.public("toy-web", [f"{config.base_url}/auth/callback"]))

    provider = servers["provider"].app
    provider.end_sessions()
    provider.revoke_tokens()
    provider.clear_requests()
    provider.auto_approve = "auto-approve" in scenario.effective_tags
    return servers["app"].url


def before_scenario(context, scenario):
    e2e.before_scenario(context, scenario, base_url=lambda: start_stack(context, scenario))
```

Points to copy:

- Start the provider **first**, so its URL can be put in the application's
  settings, then the application, then register the public client with the
  application's real callback URL (or register
  `http://127.0.0.1:*/auth/callback` up front).
- The servers start lazily, in the `base_url` callable, so a run with
  `E2E_SKIP_BROWSER=1` or `-t ~@browser` starts nothing.
- Reset the provider before each scenario: sessions, tokens and recorded
  requests. A tag (`@auto-approve`) switches a provider option for one
  scenario.
- For an application that is configured through `pydantic-settings`, set the
  settings object's attributes (`settings.oauth2_issuer = ...`) after the
  servers start, the way existing in-process scenarios patch them. Settings
  that are read at import time need to be set through the environment before
  the application module is imported.
- The users' `scopes` are what the application's token exchange will grant:
  give each persona the roles the scenario needs.

## Scenarios

```gherkin
@browser
Feature: Signing in through OpenID Connect

  Scenario: A user signs in and lands on the dashboard
    When I navigate to "/dashboard"
    And I fill "Email" with "ada@example.test"
    And I fill "Password" with "secret"
    And I click "Sign in"
    Then the URL should be "/dashboard"
    And I should see "Welcome Ada"
    And the provider received a token request for the "authorization_code" grant
    And the browser should report no errors

  Scenario: A user without the billing scope does not see the link
    When I navigate to "/dashboard"
    And I fill "Email" with "grace@example.test"
    And I fill "Password" with "secret"
    And I click "Sign in"
    Then the navigation should not contain a link "Billing"

  @auto-approve
  Scenario: With auto-approve the login page is skipped
    When I navigate to "/dashboard"
    Then I should see "Welcome Ada"
```

The `provider received ...` step is an application-level step in the same
steps module; it reads the recorded requests:

```python
@then('the provider received a token request for the "{grant}" grant')
def token_request_received(context, grant):
    provider = context.e2e.servers["provider"].app
    grants = [r.form["grant_type"] for r in provider.requests_to("/oauth2/token")]
    assert grant in grants
```

The complete feature also covers a wrong password, signing out, and revoked
tokens sending the user back to the provider (`the provider ends every
session`).

## Pointing a real application at the fake

An application needs no code change: only its settings.

| Setting of the application | Value |
| --- | --- |
| OAuth2 issuer | `provider.issuer` (the provider's server URL) |
| Frontend / PKCE client id | The `client_id` of the `Client.public(...)` |
| Confidential client id and secret | The `Client.service(...)` credentials, whose allowed scopes include `introspect` and the scopes the application exchanges for |
| Application base URL / redirect URI | The application's server URL, registered on the public client |
| Cookie `secure` flag | Off where a setting exists (`COOKIE_SECURE=false`): the servers speak plain http on `127.0.0.1` |

Chromium accepts `Secure` cookies on loopback http addresses, so a cookie
that an application always marks `Secure` (the OAuth state cookie of
`apt-server`) still works; other engines may refuse it, which is one more
reason the default engine is Chromium.

The `OAUTH2_ISSUER` of the application must be exactly the provider's URL,
because token validation compares the `iss` claim.

## How it is tested

`libs/e2e-support/tests/test_oidc_example.py`: a pytest test drives the toy
application with Playwright directly (anonymous redirect, login, welcome
heading, Billing link, no browser errors, and the grants the provider saw),
and a second test runs the eight scenarios of the behave project in a
subprocess.
