#!/usr/bin/env python3
"""Run the full iMessage archiver pipeline."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from imessage_archiver.cli import main

main()
