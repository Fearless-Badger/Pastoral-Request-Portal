from django.contrib import admin
from django.db import models

class PrayerRequest(models.Model):
    
    class Status(models.TextChoices):
        NEW = "new", "New"
        PRAYED_FOR = "prayed", "Prayed For"
        ARCHIVED = "archived", "Archived"
        


    
    name = models.CharField(max_length=100, blank=True)
    request = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self): 
        return f"{self.name or 'Anonymous'} - {str(self.request)[:40]}" 


@admin.register(PrayerRequest)
class PrayerRequestAdmin(admin.ModelAdmin):
    list_display = ["name", "status", "submitted_at"]
    list_filter = ["status"]
    search_fields = ["name", "request"]
    readonly_fields = ["request", "name", "submitted_at", "updated_at"]

