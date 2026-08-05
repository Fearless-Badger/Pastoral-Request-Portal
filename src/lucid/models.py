from django.db import models

class PrayerRequest(models.Model):
    
    class Status(models.TextChoices):
        NEW = "nw", "New"
        PRAYED_FOR = "pr", "Prayed For"
        ARCHIVED = "arch", "Archived"
    
    name = models.CharField(max_length=100, blank=True)
    request = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)



