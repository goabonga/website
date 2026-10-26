# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the enrichment feature."""

from analytics.config import settings
from analytics.services.geoip import GeoIPService
from analytics.services.useragent import UserAgentService
from behave import given, then, when


def _override_setting(context, name, value):
    previous = getattr(settings, name)
    setattr(settings, name, value)
    context.add_cleanup(setattr, settings, name, previous)


@when('I parse the user agent "{user_agent}"')
def step_parse_user_agent(context, user_agent):
    context.device = UserAgentService().parse(user_agent)


@when("I parse an empty user agent")
def step_parse_empty_user_agent(context):
    context.device = UserAgentService().parse(None)


@then('the device type should be "{device_type}"')
def step_device_type(context, device_type):
    assert context.device.device_type == device_type, context.device


@then("the device type should be unknown")
def step_device_type_unknown(context):
    assert context.device.device_type is None, context.device


@then('the browser should be "{browser}"')
def step_browser(context, browser):
    assert context.device.browser == browser, context.device


@then('the operating system should be "{os_name}"')
def step_os(context, os_name):
    expected = None if os_name == "Other" else os_name
    assert context.device.os == expected, context.device


@then("the visitor should be flagged as a bot")
def step_is_bot(context):
    assert context.device.is_bot is True, context.device


@then("the visitor should not be flagged as a bot")
def step_is_not_bot(context):
    assert context.device.is_bot is False, context.device


@given("GeoIP is disabled")
def step_geoip_disabled(context):
    _override_setting(context, "geoip_enabled", False)


@given("GeoIP is enabled with a database that does not exist")
def step_geoip_missing_database(context):
    _override_setting(context, "geoip_enabled", True)
    _override_setting(context, "geoip_database_path", "/nonexistent/GeoLite2-City.mmdb")


@when('I look up the location of "{ip_address}"')
def step_lookup(context, ip_address):
    context.geoip = GeoIPService()
    context.location = context.geoip.lookup(ip_address)


@then("no country should be found")
def step_no_country(context):
    assert context.location.country is None


@then("no city should be found")
def step_no_city(context):
    assert context.location.city is None


@then("GeoIP lookups should be switched off")
def step_geoip_switched_off(context):
    assert context.geoip._enabled is False
