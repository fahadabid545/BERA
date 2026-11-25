"""What the checks may use from the outside: running a program, and where the project is.
The checks never run a program themselves, so the tests can give them canned answers."""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

COMMAND_SECONDS = 300


def run_program(arguments, *, folder=None):
    """(exit code, output). An exit code of None means the program could not be run at all
    (missing, not allowed, too slow), which the checks treat as a failure."""
    try:
        done = subprocess.run(
            arguments,
            capture_output=True,
            text=True,
            timeout=COMMAND_SECONDS,
            cwd=folder,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None, ""
    return done.returncode, done.stdout


@dataclass
class Context:
    project_folder: Path
    staging_env_file: Path
    production_env_file: Path
    run: object = run_program
    _remembered: dict = field(default_factory=dict)

    def remembered_run(self, name, arguments):
        """Runs a slow check once for the whole report, however many items use its answer."""
        if name not in self._remembered:
            self._remembered[name] = self.run(arguments, folder=self.project_folder)
        return self._remembered[name]
