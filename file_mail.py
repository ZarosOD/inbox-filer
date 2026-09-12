#!/usr/bin/env python3
"""Entry point. See README.md, or run with --help."""

import sys

from inbox_filer.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
