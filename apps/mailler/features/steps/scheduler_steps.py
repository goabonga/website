# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions to run the periodic tasks."""

from behave import when
from mailler.tasks import scheduler


@when('the scheduler task "{name}" runs')
def step_run_scheduler_task(context, name):
    context.task_result = getattr(scheduler, name)()


@when('the scheduler task "{name}" runs with {argument}={value:d}')
def step_run_scheduler_task_with(context, name, argument, value):
    context.task_result = getattr(scheduler, name)(**{argument: value})
