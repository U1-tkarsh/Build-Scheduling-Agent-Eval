import pytest

from django.core.management import call_command


@pytest.fixture(autouse=True)
def _use_fake_llm(settings):
    """Keep tests deterministic even when .env enables Gemini."""
    settings.USE_FAKE_LLM = True


@pytest.fixture(scope="session")
def django_db_setup(django_db_blocker):
    with django_db_blocker.unblock():
        call_command("migrate", run_syncdb=True, verbosity=0)
        call_command("seed_data", verbosity=0)


@pytest.fixture(autouse=True)
def _seed_each_db(db):
    """Ensure seed data exists for every DB-backed test."""
    from scheduling.models import AppointmentSlot

    if not AppointmentSlot.objects.exists():
        call_command("seed_data", verbosity=0)
