# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""The minimal HTML pages of the fake provider: login, consent and error."""

from __future__ import annotations

from html import escape

_LAYOUT = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>{title}</title></head>
<body><main>
<h1>{title}</h1>
{body}
</main></body>
</html>
"""


def _page(title: str, body: str) -> str:
    return _LAYOUT.format(title=escape(title), body=body)


def login_page(
    request_id: str, client_name: str, login_hint: str = "", error: str | None = None
) -> str:
    alert = f'<p role="alert">{escape(error)}</p>' if error else ""
    return _page(
        "Sign in",
        f"""<p>Sign in to continue to <strong>{escape(client_name)}</strong>.</p>
{alert}
<form method="post" action="/oauth2/authorize/login">
  <input type="hidden" name="request_id" value="{escape(request_id)}">
  <label for="email">Email</label>
  <input id="email" name="email" type="email" value="{escape(login_hint)}" required>
  <label for="password">Password</label>
  <input id="password" name="password" type="password">
  <button type="submit">Sign in</button>
</form>""",
    )


def consent_page(request_id: str, client_name: str, user_name: str, scopes: list[str]) -> str:
    items = "".join(f"<li>{escape(scope)}</li>" for scope in scopes)
    return _page(
        "Authorize access",
        f"""<p><strong>{escape(client_name)}</strong> requests access to the account of
{escape(user_name)}:</p>
<ul>{items}</ul>
<form method="post" action="/oauth2/authorize/consent">
  <input type="hidden" name="request_id" value="{escape(request_id)}">
  <button type="submit" name="decision" value="allow">Allow</button>
  <button type="submit" name="decision" value="deny">Deny</button>
</form>""",
    )


def error_page(error: str, description: str) -> str:
    return _page(
        "Authorization error",
        f'<p role="alert"><code>{escape(error)}</code>: {escape(description)}</p>',
    )
