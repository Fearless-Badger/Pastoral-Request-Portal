"""Cloudflare Turnstile verification for the public prayer form.

Stdlib only, on purpose. This makes exactly one small HTTP POST per submission,
which is not worth adding a dependency to the droplet for.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

# Worst case a slow Cloudflare holds one of the two gunicorn workers for this
# long. Tolerable only because a tokenless POST is rejected below without ever
# reaching the network, so a flood cannot use this to tie the workers up.
TIMEOUT_SECONDS = 5


def is_enabled() -> bool:
    """Turnstile is off unless both keys are configured.

    This is what lets the test suite and a fresh clone run with no keys and no
    network access.
    """
    return bool(settings.TURNSTILE_SITE_KEY and settings.TURNSTILE_SECRET_KEY)


def verify(token: str) -> bool:
    """Ask Cloudflare whether a challenge token is genuine.

    True means let the submission through. That deliberately includes the case
    where Cloudflare could not be reached at all; see the except block.
    """
    if not token:
        # No widget response at all, which is what a bot POSTing straight at the
        # endpoint looks like. Reject it without spending a round trip.
        return False

    body = urllib.parse.urlencode(
        {
            "secret": settings.TURNSTILE_SECRET_KEY,
            "response": token,
            # remoteip is deliberately omitted, and adding it would be a bug.
            # Behind Caddy, REMOTE_ADDR is the proxy container's address on the
            # compose bridge, and Cloudflare rejects a token whose remoteip does
            # not match the address that actually solved the challenge. Sending
            # the wrong one would fail every genuine submission. The token is
            # single-use and expires in about five minutes, which covers what
            # remoteip would have added here.
        }
    ).encode()

    outbound = urllib.request.Request(
        VERIFY_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    try:
        with urllib.request.urlopen(outbound, timeout=TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read())
    except (OSError, json.JSONDecodeError) as exc:
        # Fail OPEN, on purpose. urllib.error.URLError and TimeoutError are both
        # OSError subclasses, so this covers DNS, TLS, refused and timed out.
        #
        # With Cloudflare unreachable the choice is between letting bots through
        # for the duration of the outage and telling someone in crisis that their
        # prayer request could not be sent. The second is worse. Flip this to
        # False if that trade ever stops holding; it is not an oversight.
        logger.warning("Turnstile unreachable, allowing submission through: %s", exc)
        return True

    if not isinstance(payload, dict):
        # Same reasoning as above: a shape we do not recognise is Cloudflare's
        # problem, not the person submitting the form.
        logger.warning("Turnstile returned an unexpected payload: %r", payload)
        return True

    if payload.get("success") is True:
        return True

    # Logging the codes matters. "invalid-input-secret" from a typo'd key is
    # otherwise indistinguishable from a genuine bot rejection.
    logger.warning("Turnstile rejected a submission: %s", payload.get("error-codes"))
    return False
