*** Settings ***
Library    aitester_bdd.AITester

*** Variables ***
${ENGINE}    agent-browser
${BASE_URL}    http://localhost:5175

*** Test Cases ***
API Health And UI Consistency
    [Documentation]    Verify API health via shell curl, then confirm UI reflects the same state.
    [Setup]    Given I start scenario "health" at "${BASE_URL}"

    # Rule 1: API health check via shell
    I define rule "api_health"
        When I run shell "curl -s ${BASE_URL}/api/health"
        Then last shell exit "0"
        And last shell stdout contains "ok"

    # Rule 2: UI shows healthy state (depends on API being up)
    I define rule "ui_status"
        And I declare parents "api_health"
        Given selector exists "[data-testid='status-indicator']"
        Then has class "[data-testid='status-indicator']" "healthy"
        And contains ".status-text" "All systems operational"

    [Teardown]    Then I finalize verification
