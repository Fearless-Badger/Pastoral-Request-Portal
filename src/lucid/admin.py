from django.contrib import admin

from .models import PrayerRequest

# The admin login page is also the door to /staff/, so it is worth it not
# greeting anyone with "Django administration". site_header is the bar at the
# top, site_title the browser tab, index_title the heading on /admin/ itself.
admin.site.site_header = "Lake Hills Baptist Church"
admin.site.site_title = "Lake Hills Admin"
admin.site.index_title = "Administration"


@admin.register(PrayerRequest)
class PrayerRequestAdmin(admin.ModelAdmin):
    list_display = ["name", "status", "submitted_at"]
    list_filter = ["status"]
    search_fields = ["name", "request"]

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ["request", "name", "submitted_at", "updated_at"]
        return ["submitted_at", "updated_at"]
