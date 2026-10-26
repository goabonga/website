# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave hooks that give ``@browser`` scenarios a Playwright page.

Call them from the ``features/environment.py`` of an application, next to its own
hooks::

    from e2e_support import behave_hooks as e2e

    def before_all(context):
        e2e.before_all(context)

    def before_scenario(context, scenario):
        e2e.before_scenario(
            context, scenario, base_url=lambda: e2e.live_server(context, "app", app).url
        )

    def after_scenario(context, scenario):
        e2e.after_scenario(context, scenario)

    def after_all(context):
        e2e.after_all(context)

A scenario (or a whole feature) tagged ``@browser`` then finds ``context.page``,
``context.browser_context`` and ``context.base_url``. Scenarios without the tag are
left alone, and nothing is started when no ``@browser`` scenario runs.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from e2e_support.browser import BrowserScenario, BrowserSession, BrowserUnavailable
from e2e_support.server import LiveServer
from e2e_support.settings import E2ESettings

#: Tag selecting the scenarios that run in a real browser.
BROWSER_TAG = "browser"


@dataclass
class E2EState:
    """What the hooks keep for the whole run, stored as ``context.e2e``.

    Behave drops attributes assigned on ``context`` when the scenario ends, so the
    run-wide state lives in this object, which the hooks mutate.
    """

    settings: E2ESettings
    session: BrowserSession | None = None
    unavailable: str | None = None
    servers: dict[str, LiveServer] = field(default_factory=dict)
    scenario: BrowserScenario | None = None
    announced: bool = False


def is_browser_scenario(scenario: Any) -> bool:
    """Whether the scenario, or its feature, carries the ``@browser`` tag."""
    tags = getattr(scenario, "effective_tags", None)
    if tags is None:
        tags = scenario.tags
    return BROWSER_TAG in tags


def before_all(context: Any) -> None:
    """Read the settings; nothing is started until a ``@browser`` scenario needs it.

    With ``E2E_SCREENSHOTS=steps`` it also registers :func:`after_step`, so that an
    application does not have to wire that hook itself.
    """
    context.e2e = E2EState(E2ESettings.from_env())
    if context.e2e.settings.screenshots == "steps":
        _register_after_step(context)


def _register_after_step(context: Any) -> None:
    """Chain :func:`after_step` to the ``after_step`` hook of ``environment.py``, if any."""
    hooks = getattr(getattr(context, "_runner", None), "hooks", None)
    if hooks is None:
        return
    own = hooks.get("after_step")

    def hook(ctx: Any, step: Any) -> None:
        if own is not None:
            own(ctx, step)
        after_step(ctx, step)

    hooks["after_step"] = hook


def after_step(context: Any, step: Any) -> None:
    """Keep a screenshot of the page after each step of a ``@browser`` scenario.

    Only active with ``E2E_SCREENSHOTS=steps``; :func:`before_all` registers it.
    """
    state: E2EState = context.e2e
    if state.scenario is not None and state.settings.screenshots == "steps":
        state.scenario.capture_step(f"{step.keyword} {step.name}")


def before_tag(context: Any, tag: str) -> None:
    """Skip a ``@browser`` scenario as early as its tag is seen, when browsers cannot run.

    Optional: :func:`before_scenario` takes the same decision, so an application that
    only wires ``before_scenario`` behaves identically.
    """
    if tag != BROWSER_TAG:
        return
    target = getattr(context, "scenario", None) or getattr(context, "feature", None)
    reason = skip_reason(context)
    if target is not None and reason is not None:
        target.skip(reason)


def skip_reason(context: Any) -> str | None:
    """Why browser scenarios cannot run (``None`` when they can).

    The browser is launched on the first call that gets this far and the outcome is
    kept, so an uninstalled browser is reported once, not once per scenario.
    """
    state: E2EState = context.e2e
    if state.settings.skip_browser:
        return _announce(state, "browser scenarios are disabled (E2E_SKIP_BROWSER)")
    if state.unavailable is not None:
        return state.unavailable
    if state.session is None:
        session = BrowserSession(state.settings)
        try:
            session.start()
        except BrowserUnavailable as exc:
            state.unavailable = _announce(state, str(exc))
            return state.unavailable
        state.session = session
    return None


def _announce(state: E2EState, reason: str) -> str:
    """Tell the user, once per run, why @browser scenarios are skipped.

    Behave captures ``sys.stdout``/``sys.stderr`` inside hooks and drops the output of
    hooks that pass, so the message goes to the real standard error.
    """
    if not state.announced:
        state.announced = True
        print(f"e2e-support: @browser scenarios are skipped: {reason}", file=sys.__stderr__)
    return reason


def before_scenario(
    context: Any,
    scenario: Any,
    base_url: str | Callable[[], str] | None = None,
    **context_options: Any,
) -> None:
    """Open an isolated browser context for a ``@browser`` scenario.

    ``base_url`` is the address of the application under test; pass a callable to start
    the server only when the scenario really runs (see :func:`live_server`).
    ``context_options`` go to Playwright's ``new_context``.
    """
    if not is_browser_scenario(scenario):
        return
    reason = skip_reason(context)
    if reason is not None:
        scenario.skip(reason)
        return
    url = base_url() if callable(base_url) else base_url
    state: E2EState = context.e2e
    browser_scenario = state.session.new_scenario(
        f"{scenario.feature.name} - {scenario.name}", base_url=url, **context_options
    )
    state.scenario = browser_scenario
    context.browser_context = browser_scenario.context
    context.page = browser_scenario.page
    context.base_url = url


def after_scenario(context: Any, scenario: Any) -> None:
    """Close the scenario's browser context, keeping the artifacts if it failed."""
    state: E2EState = context.e2e
    browser_scenario, state.scenario = state.scenario, None
    if browser_scenario is None:
        return
    failed = getattr(scenario.status, "name", str(scenario.status)) == "failed"
    saved = browser_scenario.finish(failed=failed)
    if saved:
        print(f"e2e-support: artifacts saved in {browser_scenario.artifacts}")


def after_all(context: Any) -> None:
    """Stop the browser and every server started with :func:`live_server`."""
    state: E2EState = context.e2e
    session, servers = state.session, list(state.servers.values())
    state.session, state.servers = None, {}
    try:
        if session is not None:
            session.stop()
    finally:
        for server in reversed(servers):
            server.stop()


def live_server(context: Any, name: str, app: Any, **options: Any) -> LiveServer:
    """Serve ``app`` once per run under ``name``; later calls return the same server.

    The server is stopped by :func:`after_all`. ``options`` go to
    :class:`~e2e_support.server.LiveServer` (``host``, ``port``, ...).
    """
    servers = context.e2e.servers
    if name not in servers:
        servers[name] = LiveServer(app, **options).start()
    return servers[name]
