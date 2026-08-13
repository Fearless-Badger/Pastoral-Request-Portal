import io
from datetime import timedelta
from unittest import mock
from urllib.error import URLError

from django.conf import settings
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from . import turnstile
from .checks import turnstile_is_configured_for_production
from .forms import COUNTER_THRESHOLD, REQUEST_MAX_LENGTH
from .models import PrayerRequest

SECRET = "surgery on Thursday"

# Turnstile state is always pinned explicitly rather than inherited. The local
# .env holds Cloudflare's test keys, so anything reading ambient settings would
# pass or fail by accident depending on the machine.
TURNSTILE_ON = override_settings(
    TURNSTILE_SITE_KEY="1x00000000000000000000AA",
    TURNSTILE_SECRET_KEY="1x0000000000000000000000000000000AA",
)
TURNSTILE_OFF = override_settings(TURNSTILE_SITE_KEY="", TURNSTILE_SECRET_KEY="")

# Tests always run with DEBUG=False, which activates the manifest static storage
# and makes every {% static %} tag demand a collectstatic manifest entry. Swap in
# the plain backend so the suite does not depend on a build artifact.
no_manifest = override_settings(
    STORAGES={
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)


@no_manifest
class StaffAccessTests(TestCase):
    """The gate matters more than anything else on this page. Prayer requests are
    the most sensitive thing the site holds."""

    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("staff_requests")
        PrayerRequest.objects.create(name="Sarah", request=SECRET)

    def test_anonymous_is_redirected_and_sees_nothing(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])
        self.assertNotContains(response, SECRET, status_code=302)

    def test_non_staff_user_is_redirected(self):
        User.objects.create_user("member", password="pw-for-tests-only")
        self.client.login(username="member", password="pw-for-tests-only")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_staff_user_gets_the_page(self):
        User.objects.create_user("pastor", password="pw-for-tests-only", is_staff=True)
        self.client.login(username="pastor", password="pw-for-tests-only")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, SECRET)


@no_manifest
class StaffFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("staff_requests")
        cls.new = PrayerRequest.objects.create(name="Sarah", request="Surgery Thursday")
        cls.prayed = PrayerRequest.objects.create(
            name="Dave", request="Job interview", status=PrayerRequest.Status.PRAYED_FOR
        )
        cls.archived = PrayerRequest.objects.create(
            name="Karen", request="Brother out of work", status=PrayerRequest.Status.ARCHIVED
        )

    def setUp(self):
        User.objects.create_user("pastor", password="pw-for-tests-only", is_staff=True)
        self.client.login(username="pastor", password="pw-for-tests-only")

    def rows(self, **params):
        return list(self.client.get(self.url, params).context["page"].object_list)

    def test_default_view_hides_archived(self):
        self.assertEqual(self.rows(), [self.prayed, self.new])
        self.assertNotIn(self.archived, self.rows())

    def test_status_tabs(self):
        self.assertEqual(self.rows(status="new"), [self.new])
        self.assertEqual(self.rows(status="prayed"), [self.prayed])
        self.assertEqual(self.rows(status="archived"), [self.archived])
        self.assertEqual(len(self.rows(status="all")), 3)

    def test_unknown_status_falls_back_to_default(self):
        self.assertEqual(self.rows(status="nonsense"), self.rows())

    def test_search_matches_name_and_request_text(self):
        self.assertEqual(self.rows(q="sarah"), [self.new])
        self.assertEqual(self.rows(q="interview"), [self.prayed])
        self.assertEqual(self.rows(q="nothing here"), [])

    def test_sort_order(self):
        self.assertEqual(self.rows(sort="oldest"), [self.new, self.prayed])
        self.assertEqual(self.rows(sort="newest"), [self.prayed, self.new])

    def test_time_window_excludes_older_requests(self):
        old = PrayerRequest.objects.create(request="Long ago")
        PrayerRequest.objects.filter(pk=old.pk).update(
            submitted_at=old.submitted_at - timedelta(days=40)
        )

        self.assertNotIn(old, self.rows(days="7"))
        self.assertIn(old, self.rows(days=""))


@no_manifest
class StaffStatusChangeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("staff_requests")

    def setUp(self):
        User.objects.create_user("pastor", password="pw-for-tests-only", is_staff=True)
        self.client.login(username="pastor", password="pw-for-tests-only")
        self.prayer_request = PrayerRequest.objects.create(request="Surgery Thursday")

    def test_marking_prayed_updates_status_and_timestamp(self):
        before = self.prayer_request.updated_at

        response = self.client.post(
            self.url, {"pk": self.prayer_request.pk, "status": "prayed"}
        )

        self.prayer_request.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.prayer_request.status, PrayerRequest.Status.PRAYED_FOR)
        self.assertGreater(self.prayer_request.updated_at, before)

    def test_redirect_preserves_the_current_filters(self):
        response = self.client.post(
            f"{self.url}?status=new&q=surgery&sort=oldest",
            {"pk": self.prayer_request.pk, "status": "archived"},
        )

        self.assertEqual(response["Location"], f"{self.url}?status=new&q=surgery&sort=oldest")

    def test_unknown_status_is_rejected(self):
        response = self.client.post(
            self.url, {"pk": self.prayer_request.pk, "status": "deleted"}
        )

        self.prayer_request.refresh_from_db()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.prayer_request.status, PrayerRequest.Status.NEW)

    def test_missing_request_is_a_404(self):
        response = self.client.post(self.url, {"pk": 9999, "status": "prayed"})

        self.assertEqual(response.status_code, 404)

    def test_dropdown_can_set_any_valid_status(self):
        """The modal's select posts the same two fields as the shortcut buttons,
        so it has to reach statuses the buttons do not offer from every state."""
        for status in PrayerRequest.Status.values:
            with self.subTest(status=status):
                self.client.post(self.url, {"pk": self.prayer_request.pk, "status": status})

                self.prayer_request.refresh_from_db()
                self.assertEqual(self.prayer_request.status, status)


@no_manifest
class StaffModalTests(TestCase):
    """Each row carries its own dialog, so the request has to be reachable
    without a second request to the server."""

    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("staff_requests")
        cls.prayer_request = PrayerRequest.objects.create(name="Sarah", request=SECRET)

    def setUp(self):
        User.objects.create_user("pastor", password="pw-for-tests-only", is_staff=True)
        self.client.login(username="pastor", password="pw-for-tests-only")

    def test_row_opens_a_dialog_holding_the_request(self):
        response = self.client.get(self.url)

        self.assertContains(response, f'data-dialog="request-{self.prayer_request.pk}"')
        self.assertContains(response, f'id="request-{self.prayer_request.pk}"')
        # Once in the row, once in the dialog.
        self.assertContains(response, SECRET, count=2)

    def test_dialog_offers_every_status_with_the_current_one_selected(self):
        response = self.client.get(self.url)

        for value, label in PrayerRequest.Status.choices:
            self.assertContains(response, f'value="{value}"')
            self.assertContains(response, label)

        self.assertContains(response, '<option value="new" selected>', html=False)


@no_manifest
class AdminBrandingTests(TestCase):
    """The admin login page is the first thing a staff member sees, and it is
    reached by being bounced off /staff/. It has to look like the church."""

    def test_login_page_is_branded_and_loads_the_church_palette(self):
        response = self.client.get(reverse("admin:login"), {"next": "/staff/"})

        self.assertContains(response, "Lake Hills Baptist Church")
        self.assertNotContains(response, "Django administration")
        # Proves the base_site.html override in DIRS beat the one Django ships.
        self.assertContains(response, "lucid/css/admin.css")


class TurnstileVerifyTests(SimpleTestCase):
    """urlopen is patched in every test here. Reaching Cloudflare for real would
    make the suite flaky by design."""

    def test_blank_token_is_rejected_without_a_network_call(self):
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("called out")):
            self.assertFalse(turnstile.verify(""))

    def test_success_passes(self):
        with mock.patch("urllib.request.urlopen", return_value=io.BytesIO(b'{"success": true}')):
            self.assertTrue(turnstile.verify("token"))

    def test_failure_blocks_and_logs_the_codes(self):
        body = b'{"success": false, "error-codes": ["invalid-input-response"]}'

        with mock.patch("urllib.request.urlopen", return_value=io.BytesIO(body)):
            with self.assertLogs("lucid.turnstile", "WARNING") as logs:
                self.assertFalse(turnstile.verify("token"))

        self.assertIn("invalid-input-response", logs.output[0])

    def test_unreachable_cloudflare_lets_the_submission_through(self):
        """Pins the fail-open decision. If this ever starts failing, somebody
        changed the policy rather than fixed a bug."""
        with mock.patch("urllib.request.urlopen", side_effect=URLError("down")):
            with self.assertLogs("lucid.turnstile", "WARNING"):
                self.assertTrue(turnstile.verify("token"))


@no_manifest
@TURNSTILE_OFF
class PrayerFormWithoutTurnstileTests(TestCase):
    """Blank keys have to switch the whole thing off, or a fresh clone cannot
    submit the form without network access."""

    def test_neither_the_script_nor_the_widget_renders(self):
        response = self.client.get(reverse("submit_request"))

        self.assertNotContains(response, "challenges.cloudflare.com")
        self.assertNotContains(response, "cf-turnstile")

    def test_verification_is_never_reached(self):
        with mock.patch.object(turnstile, "verify", side_effect=AssertionError("verified")):
            response = self.client.post(reverse("submit_request"), {"request": "Please pray"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(PrayerRequest.objects.count(), 1)


@no_manifest
@TURNSTILE_ON
class PrayerFormTurnstileTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("submit_request")

    def test_widget_renders_with_the_sitekey(self):
        response = self.client.get(self.url)

        self.assertContains(response, "challenges.cloudflare.com/turnstile/v0/api.js")
        self.assertContains(response, 'data-sitekey="1x00000000000000000000AA"')

    def test_no_template_comments_leak_into_the_page(self):
        """Django only strips {# #} when it sits on a single line. A multi-line one
        is emitted verbatim, so the explanation ends up in the page source."""
        response = self.client.get(self.url)

        self.assertNotContains(response, "{#")

    def test_a_failed_challenge_saves_nothing(self):
        """The one that matters. A rejected challenge must not write a row, and
        the person has to be told why rather than watching the form do nothing."""
        with mock.patch.object(turnstile, "verify", return_value=False):
            response = self.client.post(self.url, {"request": "Please pray"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please complete the verification")
        self.assertEqual(PrayerRequest.objects.count(), 0)

    def test_a_passed_challenge_saves(self):
        with mock.patch.object(turnstile, "verify", return_value=True) as verify:
            response = self.client.post(
                self.url, {"request": "Please pray", "cf-turnstile-response": "token"}
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(PrayerRequest.objects.count(), 1)
        # Also pins which field name the token is read out of.
        verify.assert_called_once_with("token")


@no_manifest
@TURNSTILE_OFF
class RequestLengthTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("submit_request")

    def test_text_at_the_cap_is_accepted(self):
        response = self.client.post(self.url, {"request": "p" * REQUEST_MAX_LENGTH})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(PrayerRequest.objects.count(), 1)

    def test_text_over_the_cap_is_rejected(self):
        response = self.client.post(self.url, {"request": "p" * (REQUEST_MAX_LENGTH + 1)})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(PrayerRequest.objects.count(), 0)

    def test_textarea_carries_the_cap_and_the_counter_threshold(self):
        """prayer_form.js reads both numbers off the element, so this is the
        contract between forms.py and the counter. The textarea assertion catches
        the CharField default widget silently collapsing it to one line."""
        response = self.client.get(self.url)

        self.assertContains(response, "<textarea")
        self.assertContains(response, f'maxlength="{REQUEST_MAX_LENGTH}"')
        self.assertContains(response, f'data-counter-at="{COUNTER_THRESHOLD}"')


class TurnstileDeployCheckTests(SimpleTestCase):
    """Blank keys plus a fail-open verify() make a misconfigured droplet silent.
    This check is the only thing that complains, so it gets tested."""

    def ids(self, **overrides):
        with override_settings(**overrides):
            return [error.id for error in turnstile_is_configured_for_production(None)]

    def test_local_development_is_never_flagged(self):
        self.assertEqual(
            self.ids(PROD=False, TURNSTILE_SITE_KEY="", TURNSTILE_SECRET_KEY=""), []
        )

    def test_blank_keys_in_production_are_an_error(self):
        self.assertEqual(
            self.ids(PROD=True, TURNSTILE_SITE_KEY="", TURNSTILE_SECRET_KEY=""),
            ["lucid.E001"],
        )

    def test_test_keys_in_production_are_an_error(self):
        """The realistic mistake is .env.example copied across and never swapped,
        which leaves both keys populated and every bot waved through."""
        self.assertEqual(
            self.ids(
                PROD=True,
                TURNSTILE_SITE_KEY="1x00000000000000000000AA",
                TURNSTILE_SECRET_KEY="1x0000000000000000000000000000000AA",
            ),
            ["lucid.E002"],
        )

    def test_real_keys_in_production_pass(self):
        self.assertEqual(
            self.ids(
                PROD=True,
                TURNSTILE_SITE_KEY="0x4AAAAAAAtestsitekey",
                TURNSTILE_SECRET_KEY="0x4AAAAAAAtestsecretkey",
            ),
            [],
        )
