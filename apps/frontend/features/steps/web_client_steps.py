# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the web client feature."""

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from behave import given, then, when

APP_DIR = Path(__file__).resolve().parents[2]
WEB_DIR = APP_DIR / "web"
TEMPLATE = APP_DIR / "src" / "frontend" / "templates" / "index.html"
GENERATOR = WEB_DIR / "scripts" / "generate-template.js"

PERSONAL_VALUES = ["Terre Rouge", "26410 Boulc", "Chris Becker", "0899 701 761", "Quai du Sartel"]

DEV_PAGE = """<!DOCTYPE html>
<html><head>
<title>GOABONGA</title>
<script>
window.__APP_CONFIG__ = {
  appName: "GOABONGA",
  apiUrl: "",
  clientId: "ea2457629d5f4680e3968df232849fde",
};
</script>
</head><body></body></html>
"""


def _prepare_workspace(context, page: str | None) -> None:
    """Copy the generator next to an optional built page, in a throw-away directory."""
    if shutil.which("node") is None:
        context.scenario.skip("node is not installed")
        return
    root = Path(tempfile.mkdtemp(prefix="frontend-web-"))
    context.add_cleanup(shutil.rmtree, root, True)
    web = root / "web"
    (web / "scripts").mkdir(parents=True)
    shutil.copy(GENERATOR, web / "scripts" / "generate-template.js")
    shutil.copy(WEB_DIR / "package.json", web / "package.json")
    if page is not None:
        (web / "dist").mkdir()
        (web / "dist" / "index.html").write_text(page, encoding="utf-8")
    context.web_root = web
    context.generated = root / "src" / "frontend" / "templates" / "index.html"


@given("a built page containing hard-coded values")
def step_built_page(context) -> None:
    _prepare_workspace(context, DEV_PAGE)


@given("no built page")
def step_no_built_page(context) -> None:
    _prepare_workspace(context, None)


@when("the template generator runs")
def step_run_generator(context) -> None:
    context.result = subprocess.run(
        ["node", "scripts/generate-template.js"],
        cwd=context.web_root,
        capture_output=True,
        text=True,
        check=False,
    )


@then('the web client contains "{name}"')
def step_web_contains(context, name: str) -> None:
    assert (WEB_DIR / name).is_file(), name


@then('the "{script}" npm script runs "{first}", then "{second}", then "{third}"')
def step_npm_script(context, script: str, first: str, second: str, third: str) -> None:
    package = json.loads((WEB_DIR / "package.json").read_text(encoding="utf-8"))
    command = package["scripts"][script]
    assert command.index(first) < command.index(second) < command.index(third), command


@then('the committed template uses the variable "{name}"')
def step_template_variable(context, name: str) -> None:
    variables = set(re.findall(r"{{\s*([a-z_]+)", TEMPLATE.read_text(encoding="utf-8")))
    assert name in variables, name


@then("the committed template contains no personal default value")
def step_no_personal_values(context) -> None:
    template = TEMPLATE.read_text(encoding="utf-8")
    assert not [value for value in PERSONAL_VALUES if value in template]


@then('the generated template contains "{text}"')
def step_generated_contains(context, text: str) -> None:
    assert context.result.returncode == 0, context.result.stderr
    assert text in context.generated.read_text(encoding="utf-8")


@then('the generated template no longer contains "{text}"')
def step_generated_lacks(context, text: str) -> None:
    assert text not in context.generated.read_text(encoding="utf-8")


@then("the generator fails asking to run the build first")
def step_generator_fails(context) -> None:
    assert context.result.returncode == 1
    assert "npm run build" in context.result.stderr
