# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""``python -m auth`` runs the ``auth`` command."""

import sys

from auth.cli import main

sys.exit(main())
