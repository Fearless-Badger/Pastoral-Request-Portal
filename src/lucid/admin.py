from django.contrib import admin
from django.utils.text import Truncator

from .models import PrayerRequest

# The admin login page is also the door to /staff/, so it is worth it not
# greeting anyone with "Django administration". site_header is the bar at the
# top, site_title the browser tab, index_title the heading on /admin/ itself.
admin.site.site_header = "Lake Hills Baptist Church"
admin.site.site_title = "Lake Hills Admin"
admin.site.index_title = "Administration"


@admin.register(PrayerRequest)
class PrayerRequestAdmin(admin.ModelAdmin):
    list_display = ["name", "preview", "status", "submitted_at"]
    list_filter = ["status"]
    search_fields = ["name", "request"]

    @admin.display(description="Request")
    def preview(self, obj):
        # Truncator counts the ellipsis toward the 20, so the column never widens.
        return Truncator(obj.request).chars(20)

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ["request", "name", "submitted_at", "updated_at"]
        return ["submitted_at", "updated_at"]
