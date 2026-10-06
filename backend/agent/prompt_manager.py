from __future__ import annotations

from pathlib import Path

from django.conf import settings

from scheduling.models import PromptVersion


class PromptManager:
    """Load and version prompts from files + optional DB tracking."""

    def __init__(self, prompts_dir: Path | None = None):
        self.prompts_dir = Path(prompts_dir or settings.AGENT_PROMPTS_DIR)

    def list_versions(self) -> list[str]:
        versions = sorted(p.stem for p in self.prompts_dir.glob("v*.txt"))
        return versions

    def read_file(self, version: str) -> str:
        path = self.prompts_dir / f"{version}.txt"
        if not path.exists():
            raise FileNotFoundError(f"Prompt version not found: {version}")
        return path.read_text(encoding="utf-8")

    def get_active_version(self) -> str:
        active = PromptVersion.objects.filter(is_active=True).order_by("-created_at").first()
        if active:
            return active.version
        versions = self.list_versions()
        return versions[0] if versions else "v1"

    def get_active_prompt(self) -> tuple[str, str]:
        version = self.get_active_version()
        return version, self.read_file(version)

    def save_version(
        self,
        version: str,
        content: str,
        *,
        activate: bool = False,
        score: float | None = None,
        accepted: bool = False,
        notes: str = "",
    ) -> PromptVersion:
        path = self.prompts_dir / f"{version}.txt"
        path.write_text(content, encoding="utf-8")

        if activate:
            PromptVersion.objects.filter(is_active=True).update(is_active=False)

        obj, _ = PromptVersion.objects.update_or_create(
            version=version,
            defaults={
                "content": content,
                "score": score,
                "is_active": activate,
                "accepted": accepted,
                "notes": notes,
            },
        )
        return obj

    def set_active(self, version: str) -> None:
        content = self.read_file(version)
        PromptVersion.objects.filter(is_active=True).update(is_active=False)
        PromptVersion.objects.update_or_create(
            version=version,
            defaults={"content": content, "is_active": True},
        )

    def next_version_name(self) -> str:
        nums = []
        for v in self.list_versions():
            try:
                nums.append(int(v.lstrip("v")))
            except ValueError:
                continue
        nxt = (max(nums) + 1) if nums else 2
        return f"v{nxt}"

    def has_booking_verification_rule(self, prompt: str | None = None) -> bool:
        text = prompt if prompt is not None else self.get_active_prompt()[1]
        markers = [
            "BOOKING VERIFICATION",
            "Never tell the patient an appointment is confirmed unless",
            "Never state that an appointment is booked",
            "book_appointment returned success=true",
            "book_appointment returns success=true",
        ]
        return any(m.lower() in text.lower() for m in markers)
