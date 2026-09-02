"""Domain layer — the innermost ring.

May import: the Python standard library, and ``pxapi.domain``. Nothing else.
It imports no web framework, no database library, no cloud SDK and no adapter
implementation, and no third-party distribution at all.

A4 adds the first domain concepts: the Analysis Run state vocabulary and its approved
transitions (``run_state``), and the stage vocabulary with the Pass-1 projection
(``stage_execution``). Both are pure data and decisions over it. The JSON contracts themselves
live under ``contracts/`` at the repository root, outside this package.
"""
