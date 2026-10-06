"""Allow running the tool as ``python -m backupgit``."""

import sys

from backupgit.cli import main

if __name__ == "__main__":
    sys.exit(main())
