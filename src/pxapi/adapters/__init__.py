"""Adapters — implementations that bind ports to the outside world.

The only layer permitted to import third-party distributions. It may depend
inward (``pxapi.application``, ``pxapi.ports``, ``pxapi.domain``,
``pxapi.config``); nothing inward may depend back on it.

Empty in A3: no provider, persistence, storage or transport adapter exists yet.
"""
