# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = APP_DIR / "web"
TEMPLATE = APP_DIR / "src" / "frontend" / "templates" / "index.html"
GENERATOR = WEB_DIR / "scripts" / "generate-template.js"

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

# Hard-coded values of the development page that must never reach the template.
PERSONAL_VALUES = ["Terre Rouge", "26410 Boulc", "Chris Becker", "0899 701 761", "Quai du Sartel"]

DEV_PAGE = """<!DOCTYPE html>
<html><head>
<meta name="description" content="GOABONGA - Developer Portfolio" />
<title>GOABONGA</title>
<script>
window.__APP_CONFIG__ = {
  appName: "GOABONGA",
  authUrl: "https://auth.goabonga.com",
  apiUrl: "",
  analyticsUrl: "https://ua.goabonga.com",
  clientId: "ea2457629d5f4680e3968df232849fde",
  welcomeName: "Chris",
  companyName: "GOABONGA",
  address: "Terre Rouge",
  hostPhone: "0899 701 761",
};
</script>
</head><body>
<a href="https://github.com/goabonga" title="GitHub">GitHub</a>
<span class="cd-words-wrapper waiting"><b class="is-visible">super</b><b>fucking</b><b>french</b><b>cool</b></span>
</body></html>
"""


def test_web_client_files_exist() -> None:
    for name in (
        "index.html",
        "package.json",
        "package-lock.json",
        "tsconfig.json",
        "tsconfig.node.json",
        "vite.config.ts",
        "src/main.ts",
        "src/router.ts",
        "scripts/generate-template.js",
    ):
        assert (WEB_DIR / name).is_file(), name


def test_build_script_type_checks_bundles_and_generates_the_template() -> None:
    package = json.loads((WEB_DIR / "package.json").read_text(encoding="utf-8"))
    build = package["scripts"]["build"]
    assert build.index("tsc") < build.index("vite build") < build.index("generate-template.js")
    assert package["scripts"]["build:template"] == "node scripts/generate-template.js"
    assert package["type"] == "module"


def test_vite_serves_assets_under_static_in_production() -> None:
    config = (WEB_DIR / "vite.config.ts").read_text(encoding="utf-8")
    assert "mode === 'production' ? '/static/' : '/'" in config
    assert "outDir: 'dist'" in config


def test_generator_writes_into_the_python_package() -> None:
    source = GENERATOR.read_text(encoding="utf-8")
    match = re.search(r"const TARGET = join\(rootDir, ([^)]*)\);", source)
    assert match is not None
    parts = [p.strip().strip("'") for p in match.group(1).split(",")]
    assert (WEB_DIR / Path(*parts)).resolve() == TEMPLATE.resolve()


def test_generated_template_is_committed_and_parametrised() -> None:
    template = TEMPLATE.read_text(encoding="utf-8")
    variables = set(re.findall(r"{{\s*([a-z_]+)", template))
    assert {
        "app_name",
        "auth_url",
        "api_url",
        "analytics_url",
        "client_id",
        "welcome_name",
        "welcome_words",
        "legal_company_name",
        "legal_address",
        "legal_city",
        "legal_country",
        "legal_director_name",
        "legal_host_name",
        "legal_host_address",
        "legal_host_city",
        "legal_host_country",
        "legal_host_phone",
        "legal_host_website",
        "social_linkedin",
        "social_github",
        "social_huggingface",
    } <= variables


def test_generated_template_has_no_hard_coded_personal_values() -> None:
    template = TEMPLATE.read_text(encoding="utf-8")
    for value in PERSONAL_VALUES:
        assert value not in template, value


def _run_generator(tmp_path: Path, page: str | None) -> subprocess.CompletedProcess[str]:
    web = tmp_path / "web"
    (web / "scripts").mkdir(parents=True)
    shutil.copy(GENERATOR, web / "scripts" / "generate-template.js")
    shutil.copy(WEB_DIR / "package.json", web / "package.json")
    if page is not None:
        (web / "dist").mkdir()
        (web / "dist" / "index.html").write_text(page, encoding="utf-8")
    return subprocess.run(
        ["node", "scripts/generate-template.js"],
        cwd=web,
        capture_output=True,
        text=True,
        check=False,
    )


@needs_node
def test_generator_replaces_hard_coded_values(tmp_path: Path) -> None:
    result = _run_generator(tmp_path, DEV_PAGE)
    assert result.returncode == 0, result.stderr
    output = (tmp_path / "src" / "frontend" / "templates" / "index.html").read_text(
        encoding="utf-8"
    )
    assert "<title>{{ app_name }}</title>" in output
    assert "authUrl: {{ auth_url | tojson }}" in output
    assert "apiUrl: {{ api_url | tojson }}" in output
    assert "analyticsUrl: {{ analytics_url | tojson }}" in output
    assert "{{ client_id | tojson }}" in output
    assert "welcomeName: {{ welcome_name | tojson }}" in output
    assert "address: {{ legal_address | tojson }}" in output
    assert 'href="{{ social_github }}"' in output
    assert "{% for word in welcome_words.split(',')[1:] %}" in output
    for leaked in ("ea2457629d5f4680e3968df232849fde", "Terre Rouge", "0899 701 761", "fucking"):
        assert leaked not in output, leaked


@needs_node
def test_generator_fails_without_a_build(tmp_path: Path) -> None:
    result = _run_generator(tmp_path, None)
    assert result.returncode == 1
    assert 'Make sure to run "npm run build" first.' in result.stderr
