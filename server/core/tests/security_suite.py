"""The security test suite: which test files protect which security rules.

Every file listed here gets the `security` marker, so `python -m pytest -m security` runs the
suite alone (CI shows it as its own check). The normal `python -m pytest` runs it too, so a
failing security test blocks a change like any other failing test.

When a feature adds a security rule (a route, a role, a kind of company data, a limit), its
tests go into one of these areas, or a new area is added here.
"""

AREAS = {
    "sign-in": [
        "signin/tests/test_login.py",
        "signin/tests/test_refresh_view.py",
        "signin/tests/test_change_password.py",
        "twostep/tests/test_setup_and_login.py",
        "adminusers/tests/test_admin_login.py",
        "adminusers/tests/test_first_super_admin.py",
        "companies/tests/test_password_reset.py",
    ],
    "tokens: tampered, expired, reused, wrong audience": [
        "signin/tests/test_tokens.py",
        "signin/tests/test_service.py",
        "signin/tests/test_authentication.py",
        "signin/tests/test_signing_secrets.py",
        "core/tests/test_security_every_route.py",
    ],
    "permissions per role": [
        "companies/tests/test_role_matrix.py",
        "companies/tests/test_invites.py",
        "companies/tests/test_team_members.py",
        "adminusers/tests/test_admin_roles.py",
        "plans/tests/test_plans.py",
        "plans/tests/test_regional_pricing.py",
        "plans/tests/test_subscription_states.py",
        "usage/tests/test_usage_counting.py",
        "plans/tests/test_limits.py",
        "plans/tests/test_plan_display.py",
        "projects/tests/test_create_project.py",
        "projects/tests/test_projects_list.py",
        "projects/tests/test_edit_archive.py",
        "projects/tests/test_project_deletion.py",
        "projects/tests/test_requirement_extraction.py",
        "projects/tests/test_requirement_editor.py",
        "projects/tests/test_scoring_settings.py",
        "cvs/tests/test_cv_upload.py",
        "cvs/tests/test_cv_downloads.py",
        "cvs/tests/test_duplicate_detection.py",
        "cvs/tests/test_text_reading.py",
        "cvs/tests/test_processing.py",
        "cvs/tests/test_ai_reading.py",
        "cvs/tests/test_fairness_guard.py",
        "cvs/tests/test_candidate_record.py",
        "cvs/tests/test_candidate_data_protection.py",
        "ai/tests/test_model_settings.py",
        "ai/tests/test_prompt_versions.py",
        "cvs/tests/test_read_description.py",
        "privatefiles/tests/test_private_storage.py",
        "ai/tests/test_ai_client.py",
        "adminusers/tests/test_admin_controls.py",
        "adminusers/tests/test_block_member.py",
        "activity/tests/test_activity_log.py",
        "twostep/tests/test_company_requirement.py",
    ],
    "wrong-company access for every kind of object": [
        "signin/tests/test_object_permissions.py",
        "signin/tests/test_company_isolation.py",
    ],
    "audit log: complete, permanent, free of secrets": [
        "audit/tests/test_audit_log.py",
        "audit/tests/test_security_events.py",
    ],
    "hostile input": [
        "core/tests/test_hostile_input.py",
        "core/tests/test_browser_protection.py",
    ],
    "rate limits": [
        "core/tests/test_rate_limits.py",
        "core/tests/test_rate_limits_on_real_routes.py",
    ],
    "blocked and suspended users": [
        "signin/tests/test_ending_sessions.py",
        "companies/tests/test_role_matrix.py",
    ],
    "routes are private unless listed": [
        "core/tests/test_route_protection.py",
        "core/tests/test_refusals.py",
    ],
    "the suite itself": ["core/tests/test_security_suite.py"],
}

SECURITY_TEST_FILES = frozenset(path for files in AREAS.values() for path in files)
