from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import PrayerRequest

SECRET = "surgery on Thursday"

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
