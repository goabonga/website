# Generic steps

`e2e_support.steps` is a library of behave steps written in the vocabulary of
a user, so that a browser scenario of any application reads the same way and
needs no application-specific step for the common interactions.

## Using them

Importing the module registers the steps. Do it from any module of the
application's `features/steps/` directory:

```python
# apps/<app>/features/steps/browser_steps.py
from e2e_support import steps  # noqa: F401
```

The steps need a page, so they only work in `@browser` scenarios (see
[Behave hooks](05-behave-hooks.md)). Used elsewhere, they fail with
`this step needs a browser page: tag the scenario or the feature with @browser ...`.

## Describing a target

Targets are described as a user sees the page, not with CSS:

| Step family | A target is searched as |
| --- | --- |
| Click | a button by accessible name, then a link, then a control by label, then visible text |
| Fill, select | a control by label, then by placeholder, then a textbox by accessible name, then by its `name` attribute |
| Visibility, text | visible text |
| Navigation | a link by accessible name inside a `nav` or `[role=navigation]` landmark |

Matching is a case-insensitive substring match (Playwright's default); the
first match wins. Searching retries until `E2E_TIMEOUT`, so a control added
by JavaScript after a click is found without an explicit wait. When nothing
matches the failure says what was looked for:
`nothing on the page matches a button, link or text "Nonexistent button"`.

Prefix a target with `css=` for the rare case a selector is the only way:
`I click "css=#submit"`, `"css=nav" should be visible`.

## Steps

Action steps accept any keyword (`Given`, `When`, `And`); the steps written
with `Then` are assertions and only match after `Then` (or the `And` that
follows it).

| Step | Effect |
| --- | --- |
| `I navigate to "{path}"` | Go to a path (resolved against `context.base_url`) or an absolute URL |
| `I click "{target}"` | Click the target |
| `I fill "{name}" with "{value}"` | Fill a field |
| `I select "{option}" from "{name}"` | Choose an option by its label |
| `I press "{key}"` | Press a key, for example `Enter` |
| `I take a screenshot "{name}"` | Save a full-page PNG in `<E2E_ARTIFACTS_DIR>/screenshots/` |
| `Then I should see "{text}"` | The text is visible |
| `Then I should not see "{text}"` | The text is absent or hidden |
| `Then the URL should be "{location}"` | Exact URL; a path is resolved against the base URL |
| `Then the URL should contain "{fragment}"` | The URL contains the fragment |
| `Then the page title should be "{title}"` | Exact title |
| `Then the page title should contain "{fragment}"` | Title contains the fragment |
| `Then "{target}" should be visible` | The text (or `css=` selector) is visible |
| `Then "{target}" should be hidden` | It is hidden or absent |
| `Then the navigation should contain a link "{text}"` | A visible link with that name exists in the navigation |
| `Then the navigation link "{text}" should point to "{href}"` | The link also has that `href` |
| `Then the navigation should not contain a link "{text}"` | No such link in the navigation |
| `Then the browser should report no errors` | No console error and no uncaught page error ([diagnostics](04-diagnostics.md)) |

Expectations retry until `E2E_TIMEOUT`, so they tolerate pages that render
progressively.

## Example

```gherkin
@browser
Feature: Signing in

  Scenario: A user signs in with a password
    Given I navigate to "/login"
    When I fill "Email" with "ada@example.test"
    And I fill "Password" with "secret"
    And I click "Sign in"
    Then the URL should be "/dashboard"
    And the navigation should contain a link "Settings"
    And the browser should report no errors
```

Application-specific steps live next to the application and use
`context.page` directly; they can reuse `e2e_support.steps.clickable`,
`field` and `current_page`.

## How it is tested

Pytest (`libs/e2e-support/tests/test_steps.py`) runs behave on the test
project against a toy site with a login form, a dashboard with a navigation
and a page whose button appears after a delay: a sign-in flow using every
family of steps, a wrong password, navigation checks, waiting for late
elements, screenshots, the message for a missing target and the message for
a scenario without the `@browser` tag.
