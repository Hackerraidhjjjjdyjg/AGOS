"""Pytest configuration for AGOS.

Ensures the repository root is importable so tests can `import agents` / `import
memory` regardless of how pytest is invoked.
"""

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
