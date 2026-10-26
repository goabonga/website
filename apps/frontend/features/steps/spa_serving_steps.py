# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the single page application serving feature."""

import shutil
import tempfile
from pathlib import Path

from behave import given


@given('a client build containing "{name}"')
def step_client_build(context, name: str) -> None:
    root = Path(tempfile.mkdtemp(prefix="frontend-dist-"))
    context.add_cleanup(shutil.rmtree, root, True)
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("console.log('hi')", encoding="utf-8")
    context.overrides["static_dir"] = str(root)
