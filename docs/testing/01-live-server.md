# Live server

A browser cannot talk to an ASGI application through an in-process
transport, it needs a socket. `e2e_support.server.LiveServer` runs any ASGI
application with uvicorn in a background thread and exposes its URL.

## What it does

- Binds a socket on `host:port` **before** starting the thread. With the
  default `port=0` the operating system picks a free port, so parallel runs
  never collide and `url` is exact as soon as the server is started.
- Starts uvicorn on that socket in a daemon thread and waits until the
  server has completed its startup (including the ASGI lifespan) before
  returning.
- Stops cleanly: `stop()` asks uvicorn to exit, joins the thread and closes
  the socket, so the port is free again. It is idempotent.
- Is a context manager: `with LiveServer(app) as server:`.

## Usage

```python
from e2e_support.server import LiveServer

with LiveServer(app) as server:
    print(server.url)  # http://127.0.0.1:<random port>
```

| Argument | Default | Description |
| --- | --- | --- |
| `app` | required | ASGI application, for example a FastAPI instance |
| `host` | `127.0.0.1` | Interface to bind; an IPv6 address is bracketed in `url` |
| `port` | `0` | Port to bind; `0` picks a free one |
| `startup_timeout` | `10.0` | Seconds to wait for readiness |
| `shutdown_timeout` | `10.0` | Seconds to wait for the thread to exit |
| `log_level` | `warning` | uvicorn log level |

| Attribute | Description |
| --- | --- |
| `url` | Base URL without a trailing slash |
| `host`, `port` | The bound address |
| `is_running` | Whether the server thread is alive |

## Behavior worth knowing

- The ASGI lifespan protocol is required (Starlette and FastAPI provide
  it). A failing startup hook makes `start()` raise `LiveServerError`
  instead of being silently ignored.
- Binding a busy port raises `LiveServerError` with the address in the
  message.
- If the application has a `bind_url(url)` method it is called with the
  public URL once the socket is bound and before the first request. The fake
  OpenID provider uses it to learn its issuer.
- Cookies are shared between servers on the same host name regardless of the
  port. Two applications served on `127.0.0.1` therefore share a browser
  cookie jar: give their cookies distinct names, or serve one of them on
  `localhost`.

## How it is tested

Pytest (`libs/e2e-support/tests/test_server.py`): real HTTP requests against
the server, distinct ports for two servers, port release after `stop()`,
idempotent stop, an explicit port, a busy port, a double start, the
`bind_url` hook and a failing startup.
