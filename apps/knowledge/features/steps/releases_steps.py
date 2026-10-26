# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the MCP releases feature.

The routes and the webhook processing are real. The database is replaced by an
in-memory store that understands the handful of SELECT statements they issue.
"""

import hashlib
import hmac
import json
from datetime import datetime
from unittest.mock import patch

from behave import given, then, when
from fakes import FakeSession, Store

from knowledge.config import get_settings
from knowledge.database import get_db
from knowledge.models import McpRelease, McpReleaseAsset
from knowledge.models.enums import Platform, ReleaseStatus


class _SessionFactory:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *exc):
        return False


@given("the releases data layer is in memory")
def step_releases_in_memory(context):
    context.store = Store()
    context.session = FakeSession(context.store)

    async def fake_db():
        yield context.session

    context.app.dependency_overrides[get_db] = fake_db
    patcher = patch(
        "knowledge.routes.github_webhooks.async_session_factory", _SessionFactory(context.session)
    )
    patcher.start()
    context.add_cleanup(patcher.stop)


@given('the GitHub webhook secret is "{secret}"')
def step_github_secret(context, secret):
    context.github_secret = secret
    patcher = patch.object(get_settings(), "github_webhook_secret", secret)
    patcher.start()
    context.add_cleanup(patcher.stop)


# --- webhook --------------------------------------------------------------


def _release_payload(action, tag, assets=(), draft=False, body=None):
    return {
        "action": action,
        "release": {
            "id": 42,
            "tag_name": tag,
            "body": body,
            "draft": draft,
            "published_at": "2026-03-01T10:00:00Z",
            "assets": [
                {
                    "id": index,
                    "name": name,
                    "size": int(size),
                    "browser_download_url": f"https://downloads.example.test/{name}",
                }
                for index, (name, size) in enumerate(assets, start=1)
            ],
        },
    }


def _github_post(context, payload, event="release", secret="", sign=True):
    body = json.dumps(payload).encode() if not isinstance(payload, bytes) else payload
    headers = {"X-GitHub-Event": event, "Content-Type": "application/json"}
    if sign:
        digest = hmac.new((secret or context.github_secret).encode(), body, hashlib.sha256)
        headers["X-Hub-Signature-256"] = "sha256=" + digest.hexdigest()
    context.response = context.call(
        "POST", "/webhooks/github/releases", content=body, headers=headers
    )


def _table_assets(context):
    return [(row["name"], row["size"]) for row in context.table]


@when('GitHub sends a signed "{action}" event for release "{tag}" with the assets')
def step_signed_with_assets(context, action, tag):
    _github_post(context, _release_payload(action, tag, _table_assets(context)))


@when('GitHub sends a signed "{action}" event for release "{tag}" with the notes "{notes}"')
def step_signed_with_notes(context, action, tag, notes):
    _github_post(
        context,
        _release_payload(action, tag, [("knowledge-mcp-linux-x86_64", 1000)], body=notes),
    )


@when('GitHub sends a signed "{action}" event for a draft release "{tag}"')
def step_signed_draft(context, action, tag):
    _github_post(
        context,
        _release_payload(action, tag, [("knowledge-mcp-linux-x86_64", 1000)], draft=True),
    )


@when('GitHub sends a signed "{event}" event')
def step_signed_other_event(context, event):
    _github_post(context, {"zen": "Keep it logically awesome."}, event=event)


@when("GitHub sends an event signed with the wrong secret")
def step_wrong_secret(context):
    _github_post(context, _release_payload("published", "v1.0.0"), secret="other")


@when("GitHub sends an unsigned event")
def step_unsigned(context):
    _github_post(context, _release_payload("published", "v1.0.0"), sign=False)


@when("GitHub sends a signed release payload that is not valid")
def step_invalid_release(context):
    _github_post(context, {"action": "published"})


@given('the release "{version}" was imported from GitHub')
def step_imported(context, version):
    _github_post(
        context,
        _release_payload("published", f"v{version}", [("knowledge-mcp-linux-x86_64", 1000)]),
    )
    assert context.response.status_code == 200


def _release(context, version):
    return next(r for r in context.store.releases.values() if r.version == version)


@then('the release "{version}" should have the platforms "{platforms}"')
def step_platforms(context, version, platforms):
    actual = sorted(a.platform.value for a in _release(context, version).assets)
    assert actual == sorted(p.strip() for p in platforms.split(",")), actual


@then('the release "{version}" should have the notes "{notes}"')
def step_notes(context, version, notes):
    assert _release(context, version).release_notes == notes


@then("there should be {count:d} release")
def step_release_count(context, count):
    assert len(context.store.releases) == count


# --- downloads ------------------------------------------------------------


@given('the release "{version}" published on "{published}" for "{platforms}"')
def step_published_release(context, version, published, platforms):
    release = McpRelease(
        version=version,
        github_release_id=len(context.store.releases) + 1,
        release_notes=None,
        status=ReleaseStatus.PUBLISHED,
        published_at=datetime.fromisoformat(published.replace("Z", "+00:00")),
    )
    FakeSession(context.store).add(release)
    for platform in (p.strip() for p in platforms.split(",")):
        asset = McpReleaseAsset(
            release_id=release.id,
            platform=Platform(platform),
            filename=f"knowledge-mcp-{platform}",
            download_url=f"https://downloads.example.test/{version}/{platform}",
            file_size=1024,
        )
        context.session.add(asset)


@then('the asset "{platform}" of release "{version}" should have {count:d} download')
def step_download_count(context, platform, version, count):
    asset = next(a for a in _release(context, version).assets if a.platform.value == platform)
    assert asset.download_count == count
