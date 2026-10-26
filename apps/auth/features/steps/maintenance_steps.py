# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the maintenance tasks and operations scripts feature."""

import contextlib
import importlib.util
import io
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from auth.celery import celery_app
from auth.db.models.user import Session, User, UserEmail, UserProfile
from auth.tasks import backfill_pairwise, cleanup, custom_domain
from behave import given, then, when
from factories import make_user
from helpers import patch_setting
from sqlalchemy import func, select

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
TASKS = {
    "cleanup_expired_sessions": cleanup.cleanup_expired_sessions,
    "cleanup_unverified_users": cleanup.cleanup_unverified_users,
    "backfill_pairwise_subjects": backfill_pairwise.backfill_pairwise_subjects,
}


def _session(context):
    return context.database.sync_session


# --------------------------------------------------------------------- tasks
@given('an unverified user "{email}" created {days:d} day ago')
@given('an unverified user "{email}" created {days:d} days ago')
def step_unverified_user(context, email, days):
    user = make_user(_session(context), email, verified=False)
    user.created_at = datetime.now(UTC) - timedelta(days=days)
    context.database.commit()


@given("unverified accounts expire after {days:d} days")
def step_expiry(context, days):
    patch_setting(context, "unverified_user_expiry_days", days)


@when('the task "{name}" runs')
def step_run_task(context, name):
    context.task_result = TASKS[name]()


@then('the task reports "{key}" as {value:d}')
def step_task_reports_number(context, key, value):
    assert context.task_result[key] == value, context.task_result


@then('the task reports "{key}" as "{value}"')
def step_task_reports_text(context, key, value):
    assert context.task_result[key] == value, context.task_result


@then('the user "{email}" has {count:d} stored session')
@then('the user "{email}" has {count:d} stored sessions')
def step_stored_sessions(context, email, count):
    rows = (
        _session(context)
        .scalars(
            select(Session)
            .join(UserEmail, UserEmail.user_id == Session.user_id)
            .where(func.lower(UserEmail.email) == email.lower())
        )
        .all()
    )
    assert len(rows) == count, len(rows)


@then("the beat schedule contains the jobs")
def step_beat_jobs(context):
    missing = [
        row["job"] for row in context.table if row["job"] not in celery_app.conf.beat_schedule
    ]
    assert not missing, missing


# ------------------------------------------------------------- custom domains
@then('the custom domain "{domain}" is {verdict}')
def step_domain_verdict(context, domain, verdict):
    assert custom_domain._validate_domain(domain) is (verdict == "valid")


@given('the custom domain target is "{target}"')
def step_domain_target(context, target):
    _configure_target(context, target)


@given("the custom domain target is not configured")
def step_domain_target_missing(context):
    _configure_target(context, "")


def _configure_target(context, target):
    patch_setting(context, "custom_domain_cname_target", target)
    context.status_updates = []
    patcher = patch.object(
        custom_domain,
        "_update_tenant_status",
        lambda tenant_id, status, **kwargs: context.status_updates.append(str(status.value)),
    )
    patcher.start()
    context.add_cleanup(patcher.stop)
    context.ssl_queue = MagicMock()
    ssl_patcher = patch.object(
        custom_domain.provision_custom_domain_ssl, "delay", context.ssl_queue
    )
    ssl_patcher.start()
    context.add_cleanup(ssl_patcher.stop)


@given('the DNS of "{domain}" points to the target')
def step_dns_ok(context, domain):
    patcher = patch.object(
        custom_domain, "_check_dns_cname", lambda name, target: (True, f"{name} -> {target}")
    )
    patcher.start()
    context.add_cleanup(patcher.stop)


@when('the DNS verification of "{domain}" runs')
def step_verify_dns(context, domain):
    context.task_result = custom_domain.verify_custom_domain_dns.run(
        "00000000-0000-0000-0000-000000000001", domain, "shop"
    )


@then('the custom domain status becomes "{status}"')
def step_domain_status(context, status):
    assert context.status_updates[-1] == status, context.status_updates


@then('the SSL provisioning is queued for "{domain}"')
def step_ssl_queued(context, domain):
    context.ssl_queue.assert_called_once()
    assert context.ssl_queue.call_args.args[1] == domain


@then("the SSL provisioning is not queued")
def step_ssl_not_queued(context):
    context.ssl_queue.assert_not_called()


# -------------------------------------------------------------------- scripts
@when('I run the script "{name}" with the arguments "{arguments}"')
def step_run_script(context, name, arguments):
    spec = importlib.util.spec_from_file_location(f"script_{name[:-3]}", SCRIPTS / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    out, err = io.StringIO(), io.StringIO()
    context.script_code = 0
    with (
        patch.object(sys, "argv", [name, *arguments.split()]),
        contextlib.redirect_stdout(out),
        contextlib.redirect_stderr(err),
    ):
        try:
            module.main()
        except SystemExit as exit_:
            context.script_code = exit_.code or 0
    context.script_out, context.script_err = out.getvalue(), err.getvalue()


@then("the script succeeds")
def step_script_succeeds(context):
    assert context.script_code == 0, context.script_err


@then("the script exits with the code {code:d}")
def step_script_exit(context, code):
    assert context.script_code == code, (context.script_code, context.script_err)


@then('the script output JSON field "{field}" is "{value}"')
def step_script_json(context, field, value):
    assert str(json.loads(context.script_out)[field]) == value, context.script_out


@then('the script error contains "{text}"')
def step_script_error(context, text):
    assert text in context.script_err, context.script_err


@then('the stored nickname of "{email}" is "{nickname}"')
def step_nickname(context, email, nickname):
    user = (
        _session(context)
        .scalars(select(User).join(UserEmail).where(func.lower(UserEmail.email) == email.lower()))
        .one()
    )
    profile = (
        _session(context).scalars(select(UserProfile).where(UserProfile.user_id == user.id)).one()
    )
    assert profile.nickname == nickname


@then('the account "{email}" is still registered')
def step_still_registered(context, email):
    row = (
        _session(context)
        .scalars(select(UserEmail).where(func.lower(UserEmail.email) == email.lower()))
        .first()
    )
    assert row is not None
