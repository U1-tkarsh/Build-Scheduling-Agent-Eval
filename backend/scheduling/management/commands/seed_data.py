from datetime import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from agent.prompt_manager import PromptManager
from scheduling.models import Appointment, AppointmentSlot, Conversation, Doctor, PromptVersion


class Command(BaseCommand):
    help = "Seed deterministic doctors, slots, and activate prompt v1"

    def handle(self, *args, **options):
        Appointment.objects.all().delete()
        AppointmentSlot.objects.all().delete()
        Doctor.objects.all().delete()
        Conversation.objects.all().delete()

        doctors = [
            Doctor.objects.create(name="Dr. Smith", specialty="dermatology"),
            Doctor.objects.create(name="Dr. Patel", specialty="dermatology"),
            Doctor.objects.create(name="Dr. Nguyen", specialty="cardiology"),
            Doctor.objects.create(name="Dr. Alvarez", specialty="general medicine"),
        ]

        # Fixed base: Monday 2026-10-05 — slots on Tue/Wed/Thu
        base = timezone.make_aware(datetime(2026, 10, 6, 0, 0, 0))

        slot_specs = [
            # Dermatology Tue Oct 6 afternoon
            (doctors[0], base.replace(hour=14, minute=0)),   # 2:00 PM
            (doctors[0], base.replace(hour=15, minute=30)),  # 3:30 PM
            (doctors[0], base.replace(hour=16, minute=30)),  # 4:30 PM
            (doctors[1], base.replace(hour=14, minute=30)),
            # Dermatology Wed Oct 7 morning
            (doctors[0], base.replace(day=7, hour=9, minute=0)),
            (doctors[0], base.replace(day=7, hour=10, minute=0)),
            (doctors[1], base.replace(day=7, hour=9, minute=30)),
            # Cardiology Tue Oct 6 morning
            (doctors[2], base.replace(hour=9, minute=0)),
            (doctors[2], base.replace(hour=10, minute=30)),
            (doctors[2], base.replace(hour=11, minute=0)),
            # Cardiology Wed
            (doctors[2], base.replace(day=7, hour=14, minute=0)),
            # General medicine Thu Oct 8 afternoon
            (doctors[3], base.replace(day=8, hour=14, minute=0)),
            (doctors[3], base.replace(day=8, hour=15, minute=0)),
            (doctors[3], base.replace(day=8, hour=16, minute=0)),
            # Extra general medicine / derm coverage
            (doctors[3], base.replace(day=6, hour=9, minute=0)),
            (doctors[3], base.replace(day=7, hour=11, minute=0)),
            (doctors[1], base.replace(day=8, hour=10, minute=0)),
            (doctors[0], base.replace(day=9, hour=14, minute=0)),
            (doctors[2], base.replace(day=9, hour=9, minute=0)),
            (doctors[3], base.replace(day=9, hour=15, minute=30)),
        ]

        for doctor, start in slot_specs:
            AppointmentSlot.objects.create(doctor=doctor, start_time=start, is_available=True)

        pm = PromptManager()
        v1 = pm.read_file("v1")
        v2 = pm.read_file("v2")
        PromptVersion.objects.all().delete()
        pm.save_version("v1", v1, activate=True, score=None, accepted=False, notes="Baseline")
        pm.save_version("v2", v2, activate=False, score=None, accepted=False, notes="Known improved policy")

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {Doctor.objects.count()} doctors, "
                f"{AppointmentSlot.objects.count()} slots. Active prompt: v1"
            )
        )
