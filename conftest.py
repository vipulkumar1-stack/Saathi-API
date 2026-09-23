"""Session-wide fixtures: settings, an authed HttpClient/GenericClient, an
unauthenticated pair for negative tests, and a token-sanity gate so a bad
credential fails once with a clear message instead of as 90 scattered
401s.
"""
import json
import os
import time
from datetime import datetime
from pathlib import Path

import pytest
import requests

from src.auth.token_provider import (
    OtpTokenProvider,
    StaticTokenProvider,
    TokenAcquisitionError,
    assert_token_sane,
)
from src.clients.finex import FinexClient
from src.clients.generic_client import GenericClient
from src.config.settings import get_settings
from src.core.http_client import HttpClient
from src.reporting.allure_reporter import attach_exchange
from src.reporting import run_collector
from src.reporting.excel_reporter import generate_excel_report

_run_started_at = None


def _reported_exchange(response) -> None:
    """Composed HttpClient reporter: Allure attachment + in-memory collection
    for the post-run Excel/email report."""
    attach_exchange(response)
    run_collector.record_exchange(response)


@pytest.fixture(scope="session")
def settings():
    return get_settings()


@pytest.fixture(scope="session")
def token_provider(settings):
    if settings.auth_token:
        provider = StaticTokenProvider(settings.auth_token)
    else:
        provider = OtpTokenProvider(settings, session=requests.Session())

    try:
        token = provider.get_token()
        assert_token_sane(token)
    except TokenAcquisitionError as exc:
        pytest.exit(f"Auth setup failed - aborting the whole run: {exc}", returncode=1)

    return provider


@pytest.fixture(scope="session")
def http(settings, token_provider):
    return HttpClient(settings, token_provider=token_provider, reporter=_reported_exchange)


@pytest.fixture(scope="session")
def unauthed_http(settings):
    """No token attached, ever - for 401 negative tests and verified-public
    endpoints."""
    return HttpClient(settings, token_provider=None, reporter=_reported_exchange)


@pytest.fixture(scope="session")
def api(http) -> GenericClient:
    return GenericClient(http)


@pytest.fixture(scope="session")
def api_unauthed(unauthed_http) -> GenericClient:
    return GenericClient(unauthed_http)


@pytest.fixture(scope="session")
def finex(api) -> FinexClient:
    return FinexClient(api)


def pytest_addoption(parser):
    # Email report control. Default (neither flag) = ask interactively at the
    # end of a run. Non-interactive executions never send by default: an
    # agent, CI job, or script must explicitly opt in with --email.
    parser.addoption("--email", action="store_true", default=False,
        help="Send the report email without prompting.")
    parser.addoption("--no-email", action="store_true", default=False,
        help="Never send the report email for this run.")


def pytest_sessionstart(session):
    global _run_started_at
    _run_started_at = time.time()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    run_collector.start_test(item.nodeid, item.name)
    yield
    run_collector.end_test()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()

    if rep.when != "call" and not (rep.when == "setup" and rep.outcome != "passed"):
        return  # only record the outcome once per test: its call phase, or a setup failure/skip

    if getattr(rep, "wasxfail", None) is not None:
        status = "xpassed" if rep.passed else "xfailed"
    elif rep.passed:
        status = "passed"
    elif rep.skipped:
        status = "skipped"
    else:
        status = "failed"

    error = str(rep.longrepr) if (status == "failed" and rep.longrepr) else ""
    run_collector.record_test_result(item.nodeid, item.name, status, rep.duration, error)


def _write_allure_environment(results_dir: Path) -> None:
    """Write Allure's environment.properties + categories.json so the
    report shows which environment ran and auto-triages failures into
    auth/not-found/server-error/contract buckets instead of one flat list.
    """
    try:
        settings = get_settings()
        env_lines = [
            f"environment.name={settings.environment.name}",
            f"environment.base_url={settings.base_url}",
            f"environment.allow_mutations={settings.allow_mutations}",
        ]
    except RuntimeError:
        env_lines = ["environment.name=unknown"]
    # Allure environment.properties keys must not contain spaces.
    (results_dir / "environment.properties").write_text("\n".join(env_lines) + "\n")

    categories = [
        {
            "name": "Auth failures",
            "matchedStatuses": ["failed", "broken"],
            "messageRegex": ".*(401|403|Unauthorized|Auth Failed).*",
        },
        {
            "name": "Not found",
            "matchedStatuses": ["failed", "broken"],
            "messageRegex": ".*(404|not found|Not Found).*",
        },
        {
            "name": "Backend 5xx / internal error",
            "matchedStatuses": ["failed", "broken"],
            "messageRegex": ".*(50[0-9]|INTERNAL_SERVER_ERROR).*",
        },
        {
            "name": "Contract violation (schema/GraphQL errors)",
            "matchedStatuses": ["failed", "broken"],
            "messageRegex": ".*(GraphQL errors|did not match schema|GRAPHQL_VALIDATION_FAILED).*",
        },
    ]
    (results_dir / "categories.json").write_text(json.dumps(categories, indent=2))


def _build_summary(exitstatus) -> dict:
    test_results = run_collector.TEST_RESULTS
    exchanges = run_collector.EXCHANGES
    total = len(test_results)
    passed = sum(1 for r in test_results if r["status"] == "passed")
    failed = sum(1 for r in test_results if r["status"] == "failed")
    xfailed = sum(1 for r in test_results if r["status"] in ("xfailed", "xpassed"))
    skipped = sum(1 for r in test_results if r["status"] == "skipped")
    call_failures = sum(1 for e in exchanges if e["result"] == "FAIL")

    try:
        settings = get_settings()
        environment = settings.environment.name
        base_url = settings.base_url
        allow_mutations = settings.allow_mutations
    except RuntimeError:
        environment, base_url, allow_mutations = "unknown", "", ""

    started_at = _run_started_at or time.time()
    finished_at = time.time()

    return {
        "environment": environment,
        "base_url": base_url,
        "allow_mutations": allow_mutations,
        "started_at": datetime.fromtimestamp(started_at).strftime("%Y-%m-%d %H:%M:%S"),
        "finished_at": datetime.fromtimestamp(finished_at).strftime("%Y-%m-%d %H:%M:%S"),
        "duration_s": round(finished_at - started_at, 1),
        "total_tests": total,
        "passed": passed,
        "failed": failed,
        "xfailed": xfailed,
        "skipped": skipped,
        "pass_rate": f"{(passed / total * 100):.0f}%" if total else "-",
        "total_calls": len(exchanges),
        "call_failures": call_failures,
    }


def _should_send_email(config, summary: str) -> bool:
    """Decide whether to actually send, once we know a report was built.
    --no-email wins, then --email, otherwise ask interactively.

    The prompt talks to the controlling terminal (/dev/tty) directly rather
    than sys.stdin/stdout. pytest captures those at the file-descriptor
    level, which (a) makes sys.stdin.isatty() report False and (b) wedges
    the process on exit if we suspend/resume capture around an input()
    call. Reading /dev/tty sidesteps capture entirely. If there is no
    controlling terminal (cron/CI), opening it raises OSError and we
    default to not sending. An agent, CI job, or script must pass --email
    to authorize an external email."""
    if config.getoption("--no-email"):
        return False
    if config.getoption("--email"):
        return True

    # Separate read/write handles: a single "r+" text stream on /dev/tty
    # raises UnsupportedOperation ("not seekable") when you write then read.
    try:
        with open("/dev/tty", "w") as tty_out, open("/dev/tty", "r") as tty_in:
            tty_out.write(f"\n📧 {summary}\n   Send report email to recipients? [y/N] ")
            tty_out.flush()
            answer = tty_in.readline().strip().lower()
    except (OSError, EOFError, KeyboardInterrupt):
        # No interactive terminal (or Ctrl-C at the prompt): never auto-send.
        return False
    return answer in ("y", "yes")


def pytest_sessionfinish(session, exitstatus):
    # Only the controller reports under xdist - workers each hold a partial
    # slice of the results and would otherwise send/duplicate the report.
    if hasattr(session.config, "workerinput"):
        return

    results_dir = Path("allure-results")
    if results_dir.exists():
        _write_allure_environment(results_dir)

    if not run_collector.TEST_RESULTS:
        return  # nothing ran (e.g. --collect-only) - nothing to report

    summary = _build_summary(exitstatus)

    excel_path = None
    try:
        env_tag = summary["environment"]
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        excel_path = generate_excel_report(
            summary, run_collector.TEST_RESULTS, run_collector.EXCHANGES,
            output_path=f"reports/saathi-api-report-{env_tag}-{timestamp}.xlsx",
        )
        print(f"\n\nExcel report: {excel_path}")
    except Exception as e:  # noqa: BLE001 - reporting must never fail the run
        print(f"\n\n⚠️  Excel report generation failed: {e}")

    if not os.getenv("REPORT_EMAIL_TO", "").strip():
        return  # not configured - skip silently

    run_summary = (
        f"Run finished: {summary['passed']}/{summary['total_tests']} passed, "
        f"{summary['failed']} failed."
    )
    if not _should_send_email(session.config, run_summary):
        print("✉️  Email skipped by choice.")
        return

    try:
        from src.reporting.email_reporter import send_report_email
        attachments = [excel_path] if excel_path else []
        recipients = send_report_email(
            summary, run_collector.TEST_RESULTS, run_collector.EXCHANGES, attachments,
        )
        print(f"📧 Report emailed to: {', '.join(recipients)}")
    except Exception as e:  # noqa: BLE001 - never fail the run over email delivery
        print(f"⚠️  Email report failed: {e}")


def pytest_collection_modifyitems(config, items):
    """Skip @pytest.mark.mutation tests unless the settings say it's safe."""
    from src.config.settings import get_settings as _get_settings

    try:
        settings = _get_settings()
    except RuntimeError:
        return  # let collection proceed; the token_provider fixture will report the real error

    if settings.allow_mutations:
        return

    skip_mutation = pytest.mark.skip(
        reason="mutation tests are gated - set ALLOW_MUTATIONS=1 (and use an "
        "environment profile with allow_mutations=True) to run them"
    )
    for item in items:
        if "mutation" in item.keywords:
            item.add_marker(skip_mutation)
