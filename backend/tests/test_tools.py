import pytest

from agent.tools import book_appointment, cancel_appointment, get_appointment, search_available_slots
from scheduling.models import AppointmentSlot


@pytest.mark.django_db
def test_search_book_cancel_roundtrip():
    result = search_available_slots(
        specialty="dermatology",
        date="2026-10-06",
        time_preference="afternoon",
    )
    assert result["success"] is True
    assert len(result["slots"]) >= 1
    slot_id = result["slots"][0]["slot_id"]

    booked = book_appointment("Jordan Lee", slot_id)
    assert booked["success"] is True
    assert booked["appointment_id"]

    fetched = get_appointment(booked["appointment_id"])
    assert fetched["success"] is True
    assert fetched["appointment"]["status"] == "confirmed"

    cancelled = cancel_appointment(booked["appointment_id"])
    assert cancelled["success"] is True
    assert AppointmentSlot.objects.get(id=slot_id).is_available is True


@pytest.mark.django_db
def test_simulate_booking_failure():
    slots = search_available_slots("dermatology", "2026-10-06", "afternoon")["slots"]
    result = book_appointment("Jordan Lee", slots[0]["slot_id"], simulate_failure=True)
    assert result["success"] is False
    assert result["appointment_id"] is None
