"""The Operator Workbench: one multi-page analysis started and inspected from a browser (PXAPI-25).

It is a thin internal adapter and holds no analysis logic. A submitted URL and an explicit page
budget travel the path the multi-page command line takes — ``build_request`` → the registry's
request contract → ``SelectionBudgets`` → ``build_site_acquisition`` → ``AcquireSelectedPages`` —
in process, never as a subprocess, under the same strict target policy. What comes back is
validated against its contracts before anything is shown, published as a canonical artifact
bundle, read back from that bundle, and validated as a run by ``ValidateAnalysisRun`` into an
``analysis-validation-receipt.v1`` that is itself checked against its contract and rules.

**Routes.** ``GET /operator`` is the start form; ``POST /operator/runs`` starts exactly one
synchronous run and answers ``303 See Other`` with the result page, so a reload or the back
button never submits twice; ``GET /operator/runs/{run_id}`` is the result; two download routes
serve the canonical bundle and the receipt. There is no JSON API here and no OpenAPI surface:
``POST /v1/analysis-runs`` stays the homepage-only machine boundary it is.

**Ephemeral by design (V1).** The adapter holds at most one running run and the most recently
completed one, in memory. There is no database, queue, run history, idempotency key or durable
run identity; a restart loses everything. While a run is in progress a second submission is
refused with ``409`` — an adapter-local concurrency guard, not a deduplication contract.

**Untrusted content stays text.** Pages are rendered by ``workbench_views``, which escapes by
construction, and every response carries a Content-Security-Policy that allows no script at all,
styles from this origin only, and forms that post back to this origin only. A cross-site form
post is refused. Only canonical, contract-valid documents are shown; raw response bodies never
reach this adapter.

Run it with ``uvicorn pxapi.adapters.inbound.workbench:app`` (binds to 127.0.0.1 by default).
"""

from __future__ import annotations

import argparse
import io
import re
import threading
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Protocol
from urllib.parse import parse_qs, urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from pxapi.adapters.composition import (
    build_site_acquisition,
    default_registry,
    new_identifier,
    utc_now,
)
from pxapi.adapters.contracts.registry import ContractRegistry
from pxapi.adapters.inbound import workbench_views as views
from pxapi.adapters.inbound.acquire_cli import invalid_documents, page_budget
from pxapi.adapters.inbound.cli import REQUEST_CONTRACT, build_request
from pxapi.application.validate_analysis_run import (
    RECEIPT_CONTRACT,
    RECEIPT_FILE,
    ValidateAnalysisRun,
    build_artifact_bundle,
    canonical_bytes,
)
from pxapi.domain.run_validation import receipt_rule_violations
from pxapi.domain.sampling_policy import SelectionBudgets
from pxapi.domain.site_identity import UrlRefusal, refuse

#: The two form fields, and the most bytes a start form may post. Anything larger is not a form
#: this page produced.
URL_FIELD: Final = "url"
BUDGET_FIELD: Final = "max_selected_pages"
MAX_FORM_BYTES: Final = 16 * 1024
FORM_MEDIA_TYPE: Final = "application/x-www-form-urlencoded"

#: A run id as this adapter accepts it in a path: the shape of an identity, never a path of its
#: own. A value outside it is simply not a run this workbench knows.
RUN_ID_PATH: Final = re.compile(r"[A-Za-z0-9._-]{1,128}")

#: Every response's security headers. No script may run on any page; styles, forms and frames
#: are confined to this origin; nothing is cached.
SECURITY_HEADERS: Final[dict[str, str]] = {
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'self'; img-src 'self'; form-action 'self'; "
        "frame-ancestors 'none'; base-uri 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cache-Control": "no-store",
}

#: The host names this workbench answers to. Loopback only: it is an internal tool, and a Host
#: check is what keeps a DNS-rebinding page from operating it. Starlette's host check does not
#: parse bracketed IPv6 literals, so ``[::1]`` is not offered.
LOOPBACK_HOSTS: Final[tuple[str, ...]] = ("127.0.0.1", "localhost")

#: One fixed modification time for every archive member, so one bundle is one set of bytes.
_ARCHIVE_TIME: Final = (1980, 1, 1, 0, 0, 0)


class SiteAcquisition(Protocol):
    """The multi-page use case as the adapter drives it: one validated request in."""

    def run(self, request: dict[str, Any]) -> dict[str, Any]: ...


#: How the adapter obtains that use case for one declared budget. Production passes
#: ``build_site_acquisition`` itself; a test passes a factory over fake ports.
AcquisitionFactory = Callable[[SelectionBudgets, ContractRegistry], SiteAcquisition]


@dataclass(frozen=True)
class CompletedRun:
    """One finished run, as the adapter keeps it until the next one or a restart.

    ``envelope`` is present only when every canonical document satisfied its contract, and
    ``receipt`` only when the receipt satisfied its contract and the receipt rules; the archive
    exists only when both hold. Nothing withheld is kept in a form a page could show.
    """

    run_id: str
    target_url: str
    declared_budget: int
    envelope: dict[str, Any] | None
    receipt: dict[str, Any] | None
    withheld_contracts: tuple[str, ...]
    archive: bytes | None

    @property
    def defective(self) -> bool:
        return self.envelope is None or self.receipt is None


class RunSlot:
    """At most one running run, and the most recently completed one. Memory only."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: str | None = None
        self._latest: CompletedRun | None = None

    def claim(self, run_id: str) -> bool:
        """Take the one slot for ``run_id``, or refuse because another run holds it."""
        with self._lock:
            if self._active is not None:
                return False
            self._active = run_id
            return True

    def release(self, completed: CompletedRun | None) -> None:
        with self._lock:
            self._active = None
            if completed is not None:
                self._latest = completed

    def snapshot(self) -> tuple[str | None, CompletedRun | None]:
        with self._lock:
            return self._active, self._latest


def archive_of(files: Mapping[str, bytes]) -> bytes:
    """A deterministic zip of ``files``: sorted names, one fixed time, fixed permissions."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=_ARCHIVE_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, files[name])
    return buffer.getvalue()


def read_archive(content: bytes) -> dict[str, bytes]:
    """Every member of an archive, as a consumer that downloaded it would read it."""
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        return {info.filename: archive.read(info) for info in archive.infolist()}


async def _bounded_body(request: Request) -> bytes | None:
    """The request body, or ``None`` as soon as it is known to exceed :data:`MAX_FORM_BYTES`.

    A declared oversized length is refused before anything is read, and an undeclared one is
    read chunk by chunk and abandoned at the bound, so the bound limits memory, not only the
    answer.
    """
    declared = request.headers.get("content-length")
    if declared is not None and (not declared.isdigit() or int(declared) > MAX_FORM_BYTES):
        return None
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_FORM_BYTES:
            return None
    return bytes(body)


def _html(document: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(content=document, status_code=status)


def _single(fields: dict[str, list[str]], name: str) -> str | None:
    values = fields.get(name, [])
    return values[0] if len(values) == 1 else None


def may_carry_credentials(url: str) -> bool:
    """Whether ``url`` may carry userinfo, decided conservatively and independently of order.

    The Domain's ``site_identity.refuse`` reports only the *first* rule a URL breaks, so a URL
    with userinfo that also has a backslash, a space, a stray bracket or an unsupported scheme
    is reported under that other rule. Admission therefore also treats any ``@`` in the
    authority — the text after ``//`` up to the first ``/``, ``?``, ``#`` or backslash — as
    userinfo, and a URL without ``//`` as carrying userinfo if it has an ``@`` at all. Refusing
    an unusual URL that merely contains ``@`` there costs nothing; admitting a secret would
    persist it in the run's request document.
    """
    try:
        if refuse(url) is UrlRefusal.CREDENTIALS_PRESENT:
            return True
    except Exception:
        pass
    if "//" not in url:
        return "@" in url
    authority = re.split(r"[/?#\\]", url.split("//", 1)[1], maxsplit=1)[0]
    return "@" in authority


def _cross_site(request: Request) -> bool:
    """Whether a state-changing request came from a page of another origin.

    The browser's own fetch metadata decides first: ``Sec-Fetch-Site`` is set by the browser,
    cannot be written by a page, and says ``same-origin`` for our own form. It has to come first
    because this adapter sends ``Referrer-Policy: no-referrer``, under which a browser serialises
    the ``Origin`` of its own form post as ``null`` (measured on Chrome 154). Without fetch
    metadata, the ``Origin`` header must name this origin; ``null`` or another origin is refused.
    A request carrying neither (a test client, a command-line tool) was not sent by another
    site's page.
    """
    site = request.headers.get("sec-fetch-site")
    if site is not None:
        return site not in {"same-origin", "none"}
    origin = request.headers.get("origin")
    if origin is None:
        return False
    own = f"{request.url.scheme}://{request.headers.get('host', '')}"
    parsed = urlsplit(origin)
    return f"{parsed.scheme}://{parsed.netloc}" != own


class Workbench:
    """The adapter's behaviour, independent of routing, so it can be driven directly."""

    def __init__(
        self,
        registry: ContractRegistry,
        acquisition: AcquisitionFactory,
        clock: Callable[[], datetime],
        new_id: Callable[[], str],
    ) -> None:
        self.registry = registry
        self.acquisition = acquisition
        self.clock = clock
        self.new_id = new_id
        self.slot = RunSlot()

    # --- input -------------------------------------------------------------------------

    def admit(self, fields: dict[str, list[str]]) -> tuple[dict[str, Any], int] | views.FormState:
        """A validated request document and budget, or the form to show again with errors.

        Nothing is fetched here. A URL that may carry userinfo is refused first and never
        echoed back (:func:`may_carry_credentials`), whatever else is wrong with it; every other
        URL is then checked by the request contract itself, never by a weaker check of our own.
        """
        url = _single(fields, URL_FIELD)
        budget_text = _single(fields, BUDGET_FIELD)
        errors: list[str] = []

        if url is None or url == "":
            errors.append("Enter the target URL.")
        budget: int | None = None
        if budget_text is None or budget_text == "":
            errors.append("Enter the maximum number of selected pages; there is no default.")
        else:
            try:
                budget = page_budget(budget_text)
            except (argparse.ArgumentTypeError, ValueError):
                errors.append("The page budget must be a whole number of at least 1.")

        # A refused URL is shown again for correction, unless it could hold a secret at all.
        echo_url = "" if url is None or "@" in url else url
        request: dict[str, Any] | None = None
        if url:
            if may_carry_credentials(url):
                errors.append(
                    "A target carrying credentials in its authority is refused; it is not "
                    "shown again here."
                )
                echo_url = ""
            else:
                request = build_request(url)
                if self.registry.validate(REQUEST_CONTRACT, request):
                    errors.append("The target must be an absolute public http(s) URL.")
                    request = None

        if errors or request is None or budget is None:
            return views.FormState(url=echo_url, budget=budget_text or "", errors=tuple(errors))
        return request, budget

    # --- one run ------------------------------------------------------------------------

    def execute(self, request: dict[str, Any], budget: int) -> CompletedRun:
        """One synchronous run through the production path, validated end to end."""
        run_id = request["run_id"]
        envelope = self.acquisition(SelectionBudgets(max_selected_pages=budget), self.registry).run(
            request
        )
        withheld = tuple(dict.fromkeys(invalid_documents(self.registry, envelope)))

        # Publish the canonical bundle and read it back as a consumer would, then validate the
        # run against what was actually published. The archive validated here is the archive
        # served, byte for byte. The receipt is built only afterwards, pins it by digest, and is
        # never part of it: it has its own download.
        archive = archive_of(build_artifact_bundle(envelope))
        published = read_archive(archive)
        # Validated against the request that was submitted, never against the request the
        # documents carry: a run for any other target cannot pass its input gate.
        receipt = ValidateAnalysisRun(self.registry, self.clock, self.new_id).run(
            envelope, published, submitted_request=request, declared_budget=budget
        )
        receipt_valid = not self.registry.validate(RECEIPT_CONTRACT, receipt) and not (
            receipt_rule_violations(receipt)
        )

        return CompletedRun(
            run_id=run_id,
            target_url=request["target_url"],
            declared_budget=budget,
            envelope=None if withheld else envelope,
            receipt=receipt if receipt_valid else None,
            withheld_contracts=withheld,
            archive=archive if receipt_valid and not withheld else None,
        )

    def completed(self, run_id: str) -> CompletedRun | None:
        _active, latest = self.slot.snapshot()
        if latest is not None and latest.run_id == run_id:
            return latest
        return None


def create_workbench_app(
    registry: ContractRegistry | None = None,
    acquisition: AcquisitionFactory | None = None,
    clock: Callable[[], datetime] = utc_now,
    new_id: Callable[[], str] = new_identifier,
    allowed_hosts: Sequence[str] = LOOPBACK_HOSTS,
) -> FastAPI:
    """Build the Workbench. The arguments exist for tests; the defaults are the real thing."""
    registry = registry or default_registry()
    workbench = Workbench(registry, acquisition or build_site_acquisition, clock, new_id)

    app = FastAPI(
        title="PXAPI Operator Workbench",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.workbench = workbench

    # A page served under another name is not this workbench's page, even when the name
    # resolves to loopback: DNS rebinding makes an attacker's origin "same-origin" with it.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(allowed_hosts))

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any) -> Response:
        response: Response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers[name] = value
        return response

    @app.get("/operator", response_class=HTMLResponse)
    async def start() -> HTMLResponse:
        active, latest = workbench.slot.snapshot()
        return _html(
            views.start_page(latest_run_id=latest.run_id if latest else None, active_run_id=active)
        )

    @app.get(views.STYLESHEET_PATH)
    async def stylesheet() -> Response:
        return Response(content=views.STYLESHEET, media_type="text/css; charset=utf-8")

    @app.post("/operator/runs")
    async def start_run(request: Request) -> Response:
        if _cross_site(request):
            return _html(
                views.message_page(
                    "Refused",
                    "Cross-site submission refused",
                    "This workbench only accepts runs started from its own start page.",
                ),
                403,
            )
        media_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
        if media_type != FORM_MEDIA_TYPE:
            return _html(
                views.message_page(
                    "Unsupported submission",
                    "Unsupported submission",
                    "Runs are started from the form on the start page.",
                ),
                415,
            )
        body = await _bounded_body(request)
        if body is None:
            return _html(
                views.message_page(
                    "Submission too large",
                    "Submission too large",
                    "The start form posts a URL and a page budget, nothing more.",
                ),
                413,
            )
        try:
            fields = parse_qs(
                body.decode("utf-8"), keep_blank_values=True, strict_parsing=False, max_num_fields=8
            )
        except (UnicodeDecodeError, ValueError):
            fields = {}

        admitted = workbench.admit(fields)
        if isinstance(admitted, views.FormState):
            active, latest = workbench.slot.snapshot()
            page = views.start_page(
                admitted, latest_run_id=latest.run_id if latest else None, active_run_id=active
            )
            return _html(page, 422)

        run_request, budget = admitted
        run_id = run_request["run_id"]
        if not workbench.slot.claim(run_id):
            active, _latest = workbench.slot.snapshot()
            return _html(
                views.message_page(
                    "Run in progress",
                    "A run is already in progress",
                    views.el(
                        "span",
                        "This workbench runs one analysis at a time. Run ",
                        views.el("code", active or "unknown"),
                        " has not finished yet; nothing was started for this submission.",
                    ),
                ),
                409,
            )

        completed: CompletedRun | None = None
        try:
            completed = await run_in_threadpool(workbench.execute, run_request, budget)
        except Exception:
            return _html(
                views.message_page(
                    "Run failed",
                    "The run could not be completed",
                    "An internal defect stopped this run before a result existed. Nothing about "
                    "the website is implied, and nothing was kept.",
                ),
                500,
            )
        finally:
            workbench.slot.release(completed)
        return RedirectResponse(url=f"/operator/runs/{run_id}", status_code=303)

    @app.get("/operator/runs/{run_id}", response_class=HTMLResponse)
    async def result(run_id: str) -> HTMLResponse:
        active, _latest = workbench.slot.snapshot()
        if RUN_ID_PATH.fullmatch(run_id) and active == run_id:
            return _html(
                views.message_page(
                    "Run in progress",
                    "This run is still in progress",
                    "Its result page is available once it has finished.",
                ),
                202,
            )
        completed = workbench.completed(run_id) if RUN_ID_PATH.fullmatch(run_id) else None
        if completed is None:
            return _not_retained()
        view = views.ResultView(
            run_id=completed.run_id,
            target_url=completed.target_url,
            declared_budget=completed.declared_budget,
            envelope=completed.envelope,
            receipt=completed.receipt,
            withheld_contracts=completed.withheld_contracts,
            archive_available=completed.archive is not None,
        )
        return _html(views.result_page(view), 500 if completed.defective else 200)

    @app.get("/operator/runs/{run_id}/artifacts.zip")
    async def artifacts(run_id: str) -> Response:
        completed = workbench.completed(run_id) if RUN_ID_PATH.fullmatch(run_id) else None
        if completed is None or completed.archive is None:
            return _not_retained()
        return Response(
            content=completed.archive,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="pxapi-run-{run_id}.zip"'},
        )

    @app.get("/operator/runs/{run_id}/" + RECEIPT_FILE)
    async def validation_receipt(run_id: str) -> Response:
        completed = workbench.completed(run_id) if RUN_ID_PATH.fullmatch(run_id) else None
        if completed is None or completed.receipt is None:
            return _not_retained()
        return Response(
            content=canonical_bytes(completed.receipt),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="pxapi-run-{run_id}-{RECEIPT_FILE}"'
            },
        )

    return app


def _not_retained() -> HTMLResponse:
    return _html(
        views.message_page(
            "Run not available",
            "This run is not available",
            "The workbench keeps only the most recently completed run, in memory. A restart or "
            "a newer run discards it, and a run whose documents were withheld offers no bundle.",
        ),
        404,
    )


#: The ASGI application, for ``uvicorn pxapi.adapters.inbound.workbench:app``.
app = create_workbench_app()
