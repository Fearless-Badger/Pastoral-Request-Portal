from django.contrib import admin

from .models import PrayerRequest


@admin.register(PrayerRequest)
class PrayerRequestAdmin(admin.ModelAdmin):
    list_display = ["name", "status", "submitted_at"]
    list_filter = ["status"]
    search_fields = ["name", "request"]

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ["request", "name", "submitted_at", "updated_at"]
        return ["submitted_at", "updated_at"]
