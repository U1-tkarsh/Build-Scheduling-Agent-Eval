from django.core.management.base import BaseCommand

from agent.prompt_manager import PromptManager
from evals.improver import run_improvement_loop
from evals.reports import format_improvement_console, format_run_console
from evals.runner import EvalRunner


class Command(BaseCommand):
    help = "Run the scheduling agent evaluation suite"

    def add_arguments(self, parser):
        parser.add_argument(
            "--improve",
            action="store_true",
            help="Run baseline, generate improvement, rerun, and accept/reject",
        )
        parser.add_argument(
            "--no-improve",
            action="store_true",
            help="Run evaluation only (default)",
        )
        parser.add_argument(
            "--prompt-version",
            default=None,
            help="Prompt version to evaluate (default: active)",
        )

    def handle(self, *args, **options):
        # Evals must be reproducible — always use FakeLLM regardless of .env
        from django.conf import settings

        settings.USE_FAKE_LLM = True

        pm = PromptManager()
        version = options.get("prompt_version") or pm.get_active_version()
        improve = options.get("improve") and not options.get("no_improve")

        if improve:
            # Always start improvement loop from the requested/baseline version
            result = run_improvement_loop(prompt_version=version)
            self.stdout.write(format_improvement_console(result))
            return

        summary = EvalRunner(prompt_version=version).run_all()
        self.stdout.write(format_run_console(summary))
        failures = summary.get("failures") or []
        if failures:
            self.stdout.write("")
            self.stdout.write("Failures:")
            for f in failures:
                detail = (f.get("failure") or {}).get("message", "")
                self.stdout.write(f"  - {f['scenario_id']}: {detail}")
