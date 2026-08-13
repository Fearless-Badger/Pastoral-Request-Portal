"""Deployment checks for the Turnstile configuration.

Registered from LucidConfig.ready(). Being deploy=True, these run only under
`manage.py check --deploy`, never during the Docker build.
"""

from django.conf import settings
from django.core.checks import Error, Tags, register

# Cloudflare's test keys all start with one of these. Real keys never do.
TEST_KEY_PREFIXES = ("1x", "2x", "3x")


@register(Tags.security, deploy=True)
def turnstile_is_configured_for_production(app_configs, **kwargs):
    """The prayer form must not go live with its bot protection switched off.

    Blank keys disable Turnstile entirely and verify() fails open, so a
    misconfiguration here is completely silent: the form keeps working and every
    bot gets through. This check is the only thing that makes noise about it.
    """
    if not settings.PROD:
        return []

    keys = {
        "TURNSTILE_SITE_KEY": settings.TURNSTILE_SITE_KEY,
        "TURNSTILE_SECRET_KEY": settings.TURNSTILE_SECRET_KEY,
    }

    missing = sorted(name for name, value in keys.items() if not value)
    if missing:
        return [
            Error(
                f"Turnstile is disabled in production. Not set: {', '.join(missing)}.",
                hint="Set both keys in the droplet's .env from the Cloudflare dashboard.",
                id="lucid.E001",
            )
        ]

    # Checking for test keys is not paranoia. .env.example ships the always-pass
    # pair so a fresh clone works, which makes "copied the example across and
    # never swapped it" the realistic production mistake. Both keys are populated
    # in that case, so the blank check above sails straight past it.
    test_keys = sorted(
        name for name, value in keys.items() if value.startswith(TEST_KEY_PREFIXES)
    )
    if test_keys:
        return [
            Error(
                "Turnstile is using Cloudflare test keys in production. "
                f"Affected: {', '.join(test_keys)}.",
                hint="Test keys accept every submission. Replace them with the real pair.",
                id="lucid.E002",
            )
        ]

    return []
