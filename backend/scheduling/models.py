from django.db import models


class Doctor(models.Model):
    name = models.CharField(max_length=120)
    specialty = models.CharField(max_length=80)

    def __str__(self) -> str:
        return f"{self.name} ({self.specialty})"


class AppointmentSlot(models.Model):
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name="slots")
    start_time = models.DateTimeField()
    is_available = models.BooleanField(default=True)

    class Meta:
        ordering = ["start_time"]

    def __str__(self) -> str:
        return f"{self.doctor.name} @ {self.start_time}"


class Appointment(models.Model):
    STATUS_CONFIRMED = "confirmed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    patient_name = models.CharField(max_length=120)
    slot = models.ForeignKey(AppointmentSlot, on_delete=models.PROTECT, related_name="appointments")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_CONFIRMED)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Appt {self.id} — {self.patient_name} ({self.status})"


class Conversation(models.Model):
    id = models.CharField(max_length=64, primary_key=True)
    state_json = models.JSONField(default=dict)
    messages_json = models.JSONField(default=list)
    tool_logs_json = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Conversation {self.id}"


class PromptVersion(models.Model):
    version = models.CharField(max_length=20, unique=True)
    content = models.TextField()
    score = models.FloatField(null=True, blank=True)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    accepted = models.BooleanField(default=False)
    notes = models.TextField(blank=True, default="")

    def __str__(self) -> str:
        return f"Prompt {self.version} (active={self.is_active})"
