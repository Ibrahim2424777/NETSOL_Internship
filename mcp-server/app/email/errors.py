"""Email tool error types - same pattern as app/weather/errors.py (see that
file's docstring for the reasoning): every one of these is caught at the
tool boundary and turned into a clean, structured error, never a raw
exception/stack trace surfaced to the MCP client (Phase 17 doc section 21)."""


class EmailError(Exception):
    error_type = "email_error"


class EmailAuthenticationError(EmailError):
    """Gmail rejected the stored OAuth credentials (expired/revoked refresh
    token, wrong scopes, etc.) - the fix is re-running
    scripts/gmail_authorize.py, not retrying the request."""

    error_type = "email_authentication_error"


class InvalidRecipientError(EmailError):
    error_type = "invalid_recipient"


class EmailNotFoundError(EmailError):
    error_type = "email_not_found"


class EmailProviderUnavailableError(EmailError):
    error_type = "email_provider_unavailable"


class EmailRateLimitedError(EmailError):
    error_type = "email_rate_limited"


class EmailNotConfiguredError(EmailError):
    """Gmail credentials aren't set at all - distinct from AuthenticationError
    (which means credentials exist but Gmail rejected them)."""

    error_type = "email_not_configured"
