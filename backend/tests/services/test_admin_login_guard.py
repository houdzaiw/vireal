from unittest.mock import patch

import pytest

from app.services.admin_login_guard import (
    AdminLoginGuard,
    AdminLoginRateLimitedError,
)


def test_admin_login_guard_limits_and_clears_failures() -> None:
    guard = AdminLoginGuard()
    with patch("app.services.admin_login_guard.settings.ADMIN_LOGIN_MAX_FAILURES", 2):
        guard.record_failure("client:admin@example.com")
        guard.record_failure("client:admin@example.com")
        with pytest.raises(AdminLoginRateLimitedError):
            guard.check("client:admin@example.com")
        guard.clear("client:admin@example.com")
        guard.check("client:admin@example.com")
