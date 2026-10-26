# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the rate limiting feature."""

import asyncio
from unittest.mock import patch

from backend.middleware.rate_limit import RateLimiter
from backend.utils.request import get_client_ip
from behave import given, then, when
from fastapi import FastAPI, Request
from starlette.testclient import TestClient


class FakePipeline:
    """Record sorted-set commands and apply them on execute."""

    def __init__(self, store):
        self.store = store
        self.ops = []

    def zremrangebyscore(self, key, low, high):
        self.ops.append(("zremrangebyscore", key, low, high))

    def zcard(self, key):
        self.ops.append(("zcard", key))

    def zadd(self, key, mapping):
        self.ops.append(("zadd", key, mapping))

    def expire(self, key, seconds):
        self.ops.append(("expire", key, seconds))

    async def execute(self):
        results = []
        for op in self.ops:
            name, key = op[0], op[1]
            zset = self.store.setdefault(key, {})
            if name == "zremrangebyscore":
                for member in [m for m, score in zset.items() if op[2] <= score <= op[3]]:
                    del zset[member]
                results.append(0)
            elif name == "zcard":
                results.append(len(zset))
            elif name == "zadd":
                zset.update(op[2])
                results.append(len(op[2]))
            else:
                results.append(True)
        self.ops = []
        return results


class FakeRedis:
    """Minimal in-memory stand-in for the Redis commands used by the limiter."""

    def __init__(self):
        self.store = {}

    def pipeline(self):
        return FakePipeline(self.store)

    async def zrem(self, key, member):
        self.store.get(key, {}).pop(member, None)

    async def close(self):
        pass


@given("a rate limiter backed by an in-memory Redis")
def step_limiter(context):
    context.limiter = RateLimiter()
    context.limiter._redis = FakeRedis()
    context.results = []


@given(
    "the limits are {anon:d} anonymous, {auth:d} authenticated per window "
    "and {sessions:d} new session per IP"
)
def step_limits(context, anon, auth, sessions):
    patcher = patch("backend.middleware.rate_limit.settings")
    settings = patcher.start()
    context.patches["rate_limit_settings"] = patcher
    settings.rate_limit_anon = anon
    settings.rate_limit_auth = auth
    settings.rate_limit_window = 60
    settings.session_create_limit = sessions
    settings.session_create_window = 86400


def _check(context, user_id, ip):
    return asyncio.run(context.limiter.check_rate_limit(user_id, ip))


@given('an anonymous client "{ip}" has used its quota')
def step_used_quota(context, ip):
    for _ in range(2):
        _check(context, None, ip)


@when('an anonymous client "{ip}" makes {count:d} requests')
def step_anonymous_requests(context, ip, count):
    context.results = [_check(context, None, ip) for _ in range(count)]


@when('the user "{user_id}" makes {count:d} requests')
def step_user_requests(context, user_id, count):
    context.results = [_check(context, user_id, "203.0.113.7") for _ in range(count)]


@then("every request should be allowed")
def step_all_allowed(context):
    assert all(allowed for allowed, _, _ in context.results), context.results


@then("the last request should be rejected")
def step_last_rejected(context):
    allowed, remaining, _ = context.results[-1]
    assert allowed is False and remaining == 0, context.results


@then("the remaining quota should be {remaining:d}")
def step_remaining(context, remaining):
    assert context.results[-1][1] == remaining, context.results


@when('the address "{ip}" creates a session')
def step_create_session(context, ip):
    allowed, _, _ = asyncio.run(context.limiter.check_session_creation_limit(ip))
    assert allowed
    asyncio.run(context.limiter.record_session_creation(ip))


@then('the address "{ip}" may not create another session')
def step_cannot_create(context, ip):
    allowed, _, _ = asyncio.run(context.limiter.check_session_creation_limit(ip))
    assert allowed is False


@then('the address "{ip}" may create a session')
def step_can_create(context, ip):
    allowed, _, _ = asyncio.run(context.limiter.check_session_creation_limit(ip))
    assert allowed is True


@given("an API that echoes the client address")
def step_echo_api(context):
    api = FastAPI()

    @api.get("/ip")
    async def ip(request: Request):
        return {"ip": get_client_ip(request)}

    context.client.close()
    context.client = TestClient(api)


@when('I request "{path}" with the header "{name}" set to "{value}"')
def step_get_with_header(context, path, name, value):
    context.response = context.client.get(path, headers={name: value})
