"""Configuration primitives.

A leaf: it imports nothing from ``pxapi`` and no third-party distribution, so
that configuration can never smuggle a dependency into an inner layer. Adapters
may import it.

Empty in A3: there is nothing to configure yet.
"""
