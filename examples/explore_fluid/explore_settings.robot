*** Settings ***
Library    aitester_bdd.AITester

*** Variables ***
${ENGINE}    agent-browser
${BASE_URL}    http://localhost:5173

*** Test Cases ***
Explore Settings Page
    [Documentation]    Mix pinned rules (deterministic login) with fluid explore
    ...    (LLM-driven settings verification). The explore rule adapts to
    ...    UI changes without requiring suite updates.
    [Setup]    Given I start scenario "settings" at "${BASE_URL}/login"

    # Pinned rule: deterministic login
    I define rule "login"
        When I type "admin" into "#username"
        And I type "admin" into "#password"
        When I click locator "#submit"
        Then url contains "/dashboard"

    # Fluid rule: LLM explores settings (adapts to UI changes)
    When I explore "Navigate to Settings from the dashboard. Verify there is a theme toggle, a notification preferences section, and a save button. Toggle the theme and confirm the page appearance changes."

    [Teardown]    Then I finalize verification
