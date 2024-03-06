from datetime import timedelta

from django.db import models
from django.utils import timezone


class EmploymentVerification(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("verified", "Verified"),
        ("not_verified", "Not Verified"),
    )

    token = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)

    verification_data = models.JSONField(null=True, blank=True)

    class Meta:
        verbose_name = "Employment Verification"
        verbose_name_plural = "Employment Verifications"

    def is_token_expired(self):
        """
        Check if the token has expired, considering only working days (excluding weekends).
        """
        if self.verified_at is not None:
            return False  # Token has already been verified

        now = timezone.now()
        expiration_date = self.created_at

        # Count 3 working days for expiration
        days_counted = 0
        while days_counted < 3:
            expiration_date += timedelta(days=1)
            if expiration_date.weekday() < 5:  # Weekdays are less than 5
                days_counted += 1

        return now > expiration_date

    def save(self, *args, **kwargs):
        """
        Override the save method to check for token expiration.
        """
        super().save(*args, **kwargs)


class PDFFile(models.Model):
    file = models.FileField(upload_to="pdf_files/")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.file.name

    class Meta:
        verbose_name = "PDF File"
        verbose_name_plural = "PDF Files"
