"""What run validation needs from contract validation, and nothing more (PXAPI-25).

Run validation checks every canonical document against its registered contract, and it lives in
the application layer, which may never import a validator (``tests/contracts/
test_dependency_isolation.py``). This port is the narrow boundary between the two: one question
— "which constraints of contract ``name`` does this document break?" — answered with a pointer
and a schema keyword per violation. The validator's free-text message is deliberately not part
of it, so no reason a receipt gives can carry text a validator or a document produced.

``pxapi.adapters.contracts.registry.ContractRegistry`` satisfies it structurally, as it stands:
its ``validate`` returns frozen ``Violation`` records that carry exactly these two members. No
wrapper exists, because none is needed.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol


class ContractViolation(Protocol):
    """One broken constraint: where it is, and which schema keyword it broke."""

    @property
    def pointer(self) -> str: ...

    @property
    def keyword(self) -> str: ...


class ContractValidation(Protocol):
    """Validates a document against one registered contract, by the contract's name."""

    def validate(self, name: str, document: Any) -> Sequence[ContractViolation]: ...
