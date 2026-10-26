# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""A tiny ASGI site shared by the pytest fixtures and the behave project."""

from urllib.parse import parse_qs


async def site(scope, receive, send):
    """HTML pages that set and echo a cookie, and misbehave on demand."""
    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
    path = scope["path"]
    headers = [(b"content-type", b"text/html; charset=utf-8")]
    status = 200
    form = await _read_form(receive) if scope["method"] == "POST" else {}
    cookie = dict(scope["headers"]).get(b"cookie", b"").decode()
    body = f"<title>Page {path}</title><h1>Hello {path}</h1><p id='cookie'>{cookie}</p>"

    if path == "/set-cookie":
        headers.append((b"set-cookie", b"visited=yes; Path=/"))
    elif path == "/console":
        body += "<script>console.log('fine'); console.error('boom from console')</script>"
    elif path == "/crash":
        body += "<script>setTimeout(() => { throw new Error('kaput') }, 0)</script>"
    elif path == "/login":
        if form.get("password") == "secret":
            status = 303
            headers.append((b"location", b"/dashboard"))
            body = ""
        else:
            error = "<p role='alert'>Invalid credentials</p>" if form else ""
            body = f"<title>Sign in</title><h1>Sign in</h1>{error}{_LOGIN_FORM}"
    elif path == "/dashboard":
        body = (
            "<title>Dashboard</title>"
            "<nav><a href='/dashboard'>Dashboard</a> <a href='/settings'>Settings</a></nav>"
            "<h1>Welcome back</h1><p style='display:none'>Never shown</p>"
            "<a href='/login'>Sign out</a>"
        )
    elif path == "/delayed":
        body = (
            '<title>Delayed</title><button onclick="setTimeout(() => {'
            "const b = document.createElement('button'); b.textContent = 'Later';"
            "b.onclick = () => { document.title = 'Clicked later' };"
            'document.body.append(b) }, 300)">Reveal</button>'
        )
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body.encode()})


_LOGIN_FORM = """
<form method="post" action="/login">
  <label for="email">Email</label><input id="email" name="email">
  <label for="password">Password</label>
  <input id="password" name="password" type="password" placeholder="Your password">
  <label for="role">Role</label>
  <select id="role" name="role"><option>Reader</option><option>Editor</option></select>
  <button type="submit">Sign in</button>
</form>
"""


async def _read_form(receive):
    """Parse an urlencoded request body."""
    body = b""
    while True:
        message = await receive()
        body += message.get("body", b"")
        if not message.get("more_body"):
            return {key: values[0] for key, values in parse_qs(body.decode()).items()}
