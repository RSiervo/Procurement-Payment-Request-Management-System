#!/usr/bin/env python
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    if sys.stdout is None:
        # Started without a console (pythonw, from the Windows scheduled task): keep the output in a log file.
        log = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".local", "logs", "scheduled.log")
        os.makedirs(os.path.dirname(log), exist_ok=True)
        fresh = os.path.exists(log) and os.path.getsize(log) > 2_000_000
        sys.stdout = sys.stderr = open(log, "w" if fresh else "a", encoding="utf-8", buffering=1)
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
