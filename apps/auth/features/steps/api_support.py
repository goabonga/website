# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Helpers shared by the step modules that call the JSON API (no step definitions here)."""

import json
import re

from auth.db.models.user import User, UserEmail
from behave import register_type
from parse import with_pattern
from sqlalchemy import func, select


@with_pattern(r"GET|POST|PUT|PATCH|DELETE")
def parse_method(text):
    return text


register_type(Method=parse_method)


def _user(context, email):
    return context.database.sync_session.scalars(
        select(User).join(UserEmail).where(func.lower(UserEmail.email) == email.lower())
    ).one()


def _headers(context):
    return {"Authorization": f"Bearer {context.bearer}"}


def _body(context):
    text = context.text.replace("{scope_id}", str(getattr(context, "scope_id", "")))
    text = re.sub(r"\{user:([^}]+)\}", lambda m: str(_user(context, m.group(1)).id), text)
    return json.loads(text)


def _remember(context, path):
    """Remember the URL of the resource a creation request just returned."""
    if context.response.status_code in (200, 201):
        payload = context.response.json()
        if isinstance(payload, dict) and "id" in payload:
            context.created_path = f"{path.split('?')[0].rstrip('/')}/{payload['id']}"


def _send(context, method, path, *, body=None, remember=False):
    kwargs = {"headers": _headers(context)}
    if body is not None:
        kwargs["json"] = body
    context.response = context.client.request(method, path, **kwargs)
    if remember:
        _remember(context, path)
