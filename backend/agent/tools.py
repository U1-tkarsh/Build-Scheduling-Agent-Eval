from __future__ import annotations

from datetime import datetime, time
from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from scheduling.models import Appointment, AppointmentSlot, Doctor


def _parse_date(date_str: str | None):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None


def _matches_time_preference(dt: datetime, preference: str | None) -> bool:
    if not preference:
        return True
    pref = preference.lower().strip()
    hour = timezone.localtime(dt).hour if timezone.is_aware(dt) else dt.hour
    if pref in ("morning", "am"):
        return 6 <= hour < 12
    if pref in ("afternoon", "pm"):
        return 12 <= hour < 17
    if pref in ("evening",):
        return 17 <= hour < 21
    return True


def search_available_slots(
    specialty: str,
    date: str | None = None,
    time_preference: str | None = None,
) -> dict[str, Any]:
    """Return available slots for a specialty/date/time preference."""
    qs = AppointmentSlot.objects.filter(
        is_available=True,
        doctor__specialty__iexact=specialty.strip(),
    ).select_related("doctor")

    target_date = _parse_date(date)
    if target_date:
        qs = qs.filter(start_time__date=target_date)

    slots = []
    for slot in qs:
        if not _matches_time_preference(slot.start_time, time_preference):
            continue
        slots.append(
            {
                "slot_id": slot.id,
                "doctor": slot.doctor.name,
                "specialty": slot.doctor.specialty,
                "start_time": slot.start_time.isoformat(),
            }
        )

    return {"success": True, "slots": slots}


@transaction.atomic
def book_appointment(
    patient_name: str,
    slot_id: int,
    *,
    simulate_failure: bool = False,
) -> dict[str, Any]:
    """Book a slot. Truth lives here — never invent confirmation elsewhere."""
    if simulate_failure:
        return {
            "success": False,
            "error": "Booking service temporarily unavailable.",
            "appointment_id": None,
            "status": "failed",
        }

    try:
        slot = AppointmentSlot.objects.select_for_update().get(id=slot_id)
    except AppointmentSlot.DoesNotExist:
        return {
            "success": False,
            "error": f"Slot {slot_id} does not exist.",
            "appointment_id": None,
            "status": "failed",
        }

    if not slot.is_available:
        return {
            "success": False,
            "error": "That slot is no longer available.",
            "appointment_id": None,
            "status": "failed",
        }

    # Idempotency: same patient + same slot already confirmed
    existing = Appointment.objects.filter(
        patient_name=patient_name,
        slot_id=slot_id,
        status=Appointment.STATUS_CONFIRMED,
    ).first()
    if existing:
        return {
            "success": True,
            "appointment_id": existing.id,
            "status": "confirmed",
            "idempotent": True,
        }

    appointment = Appointment.objects.create(
        patient_name=patient_name,
        slot=slot,
        status=Appointment.STATUS_CONFIRMED,
    )
    slot.is_available = False
    slot.save(update_fields=["is_available"])

    return {
        "success": True,
        "appointment_id": appointment.id,
        "status": "confirmed",
    }


@transaction.atomic
def cancel_appointment(appointment_id: int) -> dict[str, Any]:
    try:
        appointment = Appointment.objects.select_for_update().select_related("slot").get(
            id=appointment_id
        )
    except Appointment.DoesNotExist:
        return {"success": False, "error": f"Appointment {appointment_id} not found."}

    if appointment.status == Appointment.STATUS_CANCELLED:
        return {"success": True, "status": "cancelled", "already_cancelled": True}

    appointment.status = Appointment.STATUS_CANCELLED
    appointment.save(update_fields=["status"])
    appointment.slot.is_available = True
    appointment.slot.save(update_fields=["is_available"])

    return {"success": True, "status": "cancelled", "appointment_id": appointment.id}


def get_appointment(appointment_id: int) -> dict[str, Any]:
    try:
        appointment = Appointment.objects.select_related("slot", "slot__doctor").get(
            id=appointment_id
        )
    except Appointment.DoesNotExist:
        return {"success": False, "error": f"Appointment {appointment_id} not found."}

    return {
        "success": True,
        "appointment": {
            "appointment_id": appointment.id,
            "patient_name": appointment.patient_name,
            "status": appointment.status,
            "slot_id": appointment.slot_id,
            "doctor": appointment.slot.doctor.name,
            "specialty": appointment.slot.doctor.specialty,
            "start_time": appointment.slot.start_time.isoformat(),
        },
    }


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_available_slots",
            "description": "Search for available appointment slots by specialty, date, and optional time preference.",
            "parameters": {
                "type": "object",
                "properties": {
                    "specialty": {"type": "string"},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "time_preference": {
                        "type": "string",
                        "enum": ["morning", "afternoon", "evening"],
                    },
                },
                "required": ["specialty"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": "Book an appointment for a patient on a specific slot.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_name": {"type": "string"},
                    "slot_id": {"type": "integer"},
                },
                "required": ["patient_name", "slot_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_appointment",
            "description": "Cancel an existing appointment by ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "appointment_id": {"type": "integer"},
                },
                "required": ["appointment_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_appointment",
            "description": "Look up an appointment by ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "appointment_id": {"type": "integer"},
                },
                "required": ["appointment_id"],
            },
        },
    },
]


def execute_tool(name: str, arguments: dict[str, Any], *, simulate_booking_failure: bool = False) -> dict[str, Any]:
    if name == "search_available_slots":
        return search_available_slots(
            specialty=arguments.get("specialty", ""),
            date=arguments.get("date"),
            time_preference=arguments.get("time_preference"),
        )
    if name == "book_appointment":
        return book_appointment(
            patient_name=arguments.get("patient_name", "Patient"),
            slot_id=int(arguments["slot_id"]),
            simulate_failure=simulate_booking_failure,
        )
    if name == "cancel_appointment":
        return cancel_appointment(int(arguments["appointment_id"]))
    if name == "get_appointment":
        return get_appointment(int(arguments["appointment_id"]))
    return {"success": False, "error": f"Unknown tool: {name}"}
