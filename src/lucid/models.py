from django.db import models

class PrayerRequest(models.Model):
    
    class Status(models.TextChoices):
        NEW = "new", "New"
        PRAYED_FOR = "prayed", "Prayed For"
        ARCHIVED = "archived", "Archived"
        
    class Meta: 
        verbose_name = "Prayer Request"
        verbose_name_plural = "Prayer Requests"

    
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

