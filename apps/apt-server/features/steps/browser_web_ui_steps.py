# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the public web pages browser scenarios."""

import browser_support
from apt_server.db.models import Package, PackageVisibility
from behave import given, step, then
from e2e_support.steps import current_page


@given('{count:d} public packages named "{prefix}" exist')
def bulk_packages(context, count, prefix):
    async def seed(session):
        session.add_all(
            [
                Package(
                    name=f"{prefix}-{index:02d}",
                    version="1.0",
                    architecture="amd64",
                    suite="stable",
                    component="main",
                    owner_id="someone",
                    visibility=PackageVisibility.PUBLIC,
                    filename=f"pool/main/b/{prefix}-{index:02d}/{prefix}_1.0_amd64.deb",
                    size=42,
                    md5="0" * 32,
                    sha1="1" * 40,
                    sha256="2" * 64,
                    control={},
                )
                for index in range(count)
            ]
        )
        await session.commit()

    context.run_db(seed)


@step('I visit the detail page of the package "{name}"')
def visit_detail(context, name):
    context.visit = current_page(context).goto(
        f"/packages/{browser_support.package_id(context, name)}"
    )


@then('the component filter offers only "{options}"')
def component_options(context, options):
    expected = [option.strip() for option in options.split(",")]
    actual = current_page(context).locator("select[name=component] option").all_inner_texts()
    assert actual == expected, f"the filter offers {actual}"
