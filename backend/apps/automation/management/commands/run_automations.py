from django.core.management.base import BaseCommand, CommandError

from apps.automation import runner


class Command(BaseCommand):
    help = ("Run the automations that are due (reminders, escalation, digests, backups...). "
            "Schedule this every 15 minutes; each job keeps its own timetable.")

    def add_arguments(self, parser):
        parser.add_argument("--job", help="Run only this job (see the Automations screen for the keys).")
        parser.add_argument("--force", action="store_true", help="Run even if not due or switched off.")
        parser.add_argument("--list", action="store_true", help="List the jobs and exit.")

    def handle(self, *args, **options):
        if options["list"]:
            for job in runner.JOBS:
                self.stdout.write(f"{job.key:<22} {job.schedule:<28} {job.name}")
            return
        if options["job"] and options["job"] not in runner.BY_KEY:
            raise CommandError(f"Unknown job. Choose from: {', '.join(runner.BY_KEY)}")
        ran = runner.run_due(only=options["job"], force=options["force"])
        if not ran:
            self.stdout.write("Nothing was due.")
        for job, state in ran:
            self.stdout.write(f"[{state.last_status or 'busy'}] {job.name}: {state.last_detail}")