*** Settings ***
Library    aitester_bdd.AITester

*** Variables ***
${ENGINE}    agent-browser
${BASE_URL}    http://localhost:5173

*** Test Cases ***
Login And Verify Dashboard
    [Documentation]    Login with credentials, verify dashboard widgets load,
    ...    open sidebar, verify navigation links within scoped container.
    [Setup]    Given I start scenario "login_flow" at "${BASE_URL}/login"
    And I configure interrupts    dismiss=.cookie-banner
    And I configure interrupts    dismiss=[aria-label="Close"]

    # Rule 1: Login
    I define rule "login"
        When I type "admin" into "#username"
        And I type "password123" into "#password"    secret
        When I click locator "#login-submit"
        Then url contains "/dashboard"
        And selector exists "[data-testid='user-avatar']"

    # Rule 2: Dashboard widgets (depends on login, retries for AJAX)
    I define rule "dashboard"
        And I declare parents "login"
        And I set retry 2 delay 1000
        Given url contains "/dashboard"
        Given count at least ".widget-card" 3
        When I click locator ".widget-card:first-child"
        Then selector exists ".widget-detail-panel"

    # Rule 3: Sidebar (depends on login, sets scope for children)
    I define rule "sidebar"
        And I declare parents "login"
        When I click locator "[data-testid='sidebar-toggle']"
        Then selector exists ".sidebar-panel"
        And set child scope ".sidebar-panel"

    # Rule 4: Sidebar links (depends on sidebar, inherits scope)
    I define rule "sidebar_links"
        And I declare parents "sidebar"
        Then count at least "a.nav-link" 5
        And contains "a.nav-link:first-child" "Home"
        And selector exists ".nav-section-header"

    [Teardown]    Then I finalize verification
