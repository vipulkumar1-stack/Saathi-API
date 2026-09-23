"""Email the generated per-run report (Excel attachment + HTML summary body).

Configuration is read from environment variables (loaded from .env by
python-dotenv, same as the rest of the framework). Nothing is hardcoded so no
credentials live in source.

Required env vars:
    REPORT_EMAIL_TO        comma-separated recipient address(es)
    REPORT_EMAIL_USER      the sending Gmail / Workspace account
    REPORT_EMAIL_PASSWORD  a 16-char Google App Password (NOT the login password)

Optional env vars:
    REPORT_EMAIL_FROM      From address (defaults to REPORT_EMAIL_USER)
    REPORT_EMAIL_HOST      SMTP host   (default smtp.gmail.com)
    REPORT_EMAIL_PORT      SMTP port   (default 587, STARTTLS)
"""
import html as _html
import mimetypes
import os
import smtplib
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any

_STATUS_COLOR = {"passed": "#1a7f37", "failed": "#d1242f", "xfailed": "#8250df", "skipped": "#9a6700"}


def _subject(summary: dict) -> str:
    return (
        f"Saathi API Automation Report [{summary.get('environment', '?')}] - "
        f"{summary.get('passed', 0)}/{summary.get('total_tests', 0)} passed, "
        f"{summary.get('failed', 0)} failed"
    )


def _failures(test_results: list[dict]) -> list[dict]:
    return [r for r in test_results if r.get("status") == "failed"]


def _api_of_test(exchanges: list[dict], node_id: str) -> str:
    """Best-effort: name the last (most likely offending) API call a failed
    test made, for the failure table."""
    calls = [e for e in exchanges if e["node_id"] == node_id]
    if not calls:
        return ""
    last = calls[-1]
    return f"{last['service']}.{last['api']}"


def _body(summary: dict, test_results: list[dict], exchanges: list[dict]) -> str:
    lines = [
        "Automated API pytest run finished.",
        "",
        f"  Environment: {summary.get('environment', '')}",
        f"  Base URL:    {summary.get('base_url', '')}",
        "",
        f"  Total:      {summary.get('total_tests', 0)}",
        f"  Passed:     {summary.get('passed', 0)}",
        f"  Failed:     {summary.get('failed', 0)}",
        f"  Known Bugs: {summary.get('xfailed', 0)}",
        f"  Skipped:    {summary.get('skipped', 0)}",
        f"  Pass rate:  {summary.get('pass_rate', '')}",
        "",
        f"  Total API calls: {summary.get('total_calls', 0)}",
        f"  API call failures: {summary.get('call_failures', 0)}",
        "",
    ]
    failures = _failures(test_results)
    if failures:
        lines.append("Failed tests:")
        for r in failures:
            api = _api_of_test(exchanges, r.get("node_id", ""))
            reason = (r.get("error") or "").split("\n")[0].strip()
            suffix = f"  [{api}]" if api else ""
            lines.append(f"  - {r.get('name', r.get('node_id', '?'))}{suffix}" + (f"  ({reason})" if reason else ""))
        lines.append("")

    if exchanges:
        lines.append(f"All API calls ({len(exchanges)}):")
        for ex in sorted(exchanges, key=lambda e: (e["service"], e["api"])):
            err = f"  - {ex['graphql_errors']}" if ex["graphql_errors"] else ""
            lines.append(
                f"  - [{ex['result']}] {ex['service']}.{ex['api']} ({ex['kind']}, {ex['method']}) "
                f"-> {ex['status']}, {ex['duration_ms']:.0f}ms{err}"
            )
        lines.append("")

    lines.append("Attached: full Excel report (Summary, API Calls, Tests sheets).")
    return "\n".join(lines)


def _html_body(summary: dict, test_results: list[dict], exchanges: list[dict]) -> str:
    """Self-rendering HTML summary shown directly in the inbox - Gmail strips
    <script>/<style>, so this is a static, inline-styled table."""
    def cell(txt, **style):
        st = ";".join(f"{k.replace('_', '-')}:{v}" for k, v in style.items())
        return f'<td style="padding:6px 10px;border-bottom:1px solid #eee;{st}">{_html.escape(str(txt))}</td>'

    total = summary.get("total_tests", 0)
    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    xfailed = summary.get("xfailed", 0)
    skipped = summary.get("skipped", 0)
    pass_rate = summary.get("pass_rate", "-")
    generated = datetime.now().strftime("%d %b %Y, %H:%M")

    failures = _failures(test_results)
    fail_block = ""
    if failures:
        items = "".join(
            "<li style='margin-bottom:4px'>"
            f"<b>{_html.escape(r.get('name') or r.get('node_id') or '?')}</b>"
            + (f" <span style='color:#888'>· {_html.escape(_api_of_test(exchanges, r.get('node_id', '')))}</span>"
               if _api_of_test(exchanges, r.get('node_id', '')) else "")
            + (f"<br><span style='color:#8a1f1f'>{_html.escape((r.get('error') or '').split(chr(10))[0].strip())}</span>"
               if (r.get('error') or '').strip() else "")
            + "</li>"
            for r in failures
        )
        fail_block = (
            '<div style="margin:0 0 20px;padding:12px 16px;background:#fff5f5;'
            'border:1px solid #f3c2c2;border-left:4px solid #d1242f;border-radius:4px">'
            f'<div style="font-weight:700;color:#d1242f;margin-bottom:8px">⚠ {len(failures)} failed test(s)</div>'
            f'<ul style="margin:0;padding-left:18px;font-size:14px;color:#1a1a1a">{items}</ul>'
            '</div>'
        )

    # Every API call made this run, grouped by service with a subheader per
    # group (mirrors the attached Excel's "API Calls" sheet) - the user wants
    # to see each API's status in the email itself, not just pass/fail totals.
    order, groups = [], {}
    for ex in exchanges:
        s = ex["service"]
        if s not in groups:
            groups[s] = []
            order.append(s)
        groups[s].append(ex)
    order.sort()

    api_rows = []
    for service in order:
        members = sorted(groups[service], key=lambda e: (0 if e["result"] == "FAIL" else 1, e["api"]))
        s_failed = sum(1 for e in members if e["result"] == "FAIL")
        api_rows.append(
            f'<tr><td colspan="6" style="padding:10px 10px 4px;font-weight:700;'
            f'background:#f0f3f6;border-top:1px solid #ddd">{_html.escape(service)} '
            f'<span style="font-weight:400;color:#666">· {len(members)} call(s)'
            + (f', <span style="color:#d1242f">{s_failed} failed</span>' if s_failed else '')
            + '</span></td></tr>'
        )
        for ex in members:
            color = "#d1242f" if ex["result"] == "FAIL" else "#1a7f37"
            api_rows.append(
                "<tr>"
                + cell(ex["api"])
                + cell(ex["kind"])
                + cell(ex["method"])
                + cell(ex["status"])
                + cell(ex["graphql_errors"] or "-")
                + f'<td style="padding:6px 10px;border-bottom:1px solid #eee;font-weight:600;color:{color}">{ex["result"]}</td>'
                + "</tr>"
            )
    api_calls_table = "".join(api_rows)

    return f"""\
<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#1a1a1a">
  <h2 style="margin:0 0 4px">Saathi API Automation Report</h2>
  <p style="margin:0 0 16px;color:#666">
    Environment: <b>{_html.escape(str(summary.get('environment', '')))}</b> ·
    {_html.escape(str(summary.get('base_url', '')))} · {generated}
  </p>
  {fail_block}
  <table style="border-collapse:collapse;margin-bottom:20px">
    <tr>
      <td style="padding:8px 16px;background:#f6f8fa;border:1px solid #eee">Total<br><b style="font-size:20px">{total}</b></td>
      <td style="padding:8px 16px;background:#f6f8fa;border:1px solid #eee;color:#1a7f37">Passed<br><b style="font-size:20px">{passed}</b></td>
      <td style="padding:8px 16px;background:#f6f8fa;border:1px solid #eee;color:#d1242f">Failed<br><b style="font-size:20px">{failed}</b></td>
      <td style="padding:8px 16px;background:#f6f8fa;border:1px solid #eee;color:#8250df">Known Bugs<br><b style="font-size:20px">{xfailed}</b></td>
      <td style="padding:8px 16px;background:#f6f8fa;border:1px solid #eee;color:#9a6700">Skipped<br><b style="font-size:20px">{skipped}</b></td>
      <td style="padding:8px 16px;background:#f6f8fa;border:1px solid #eee">Pass rate<br><b style="font-size:20px">{pass_rate}</b></td>
    </tr>
  </table>
  <p style="margin:0 0 6px;font-weight:700">All API calls ({len(exchanges)})</p>
  <table style="border-collapse:collapse;width:100%;font-size:14px;margin-bottom:20px">
    <tr style="text-align:left;background:#f6f8fa">
      <th style="padding:6px 10px;border-bottom:2px solid #ddd">API / Operation</th>
      <th style="padding:6px 10px;border-bottom:2px solid #ddd">Kind</th>
      <th style="padding:6px 10px;border-bottom:2px solid #ddd">Method</th>
      <th style="padding:6px 10px;border-bottom:2px solid #ddd">HTTP Status</th>
      <th style="padding:6px 10px;border-bottom:2px solid #ddd">GraphQL Error</th>
      <th style="padding:6px 10px;border-bottom:2px solid #ddd">Result</th>
    </tr>
    {api_calls_table}
  </table>
  <p style="margin-top:20px;color:#666;font-size:13px"><b>Attached:</b></p>
  <ul style="margin:4px 0 0;color:#666;font-size:13px">
    <li>Full Excel report (Summary, API Calls, Tests sheets) - every API call made this run</li>
  </ul>
</div>"""


def send_report_email(summary: dict[str, Any], test_results: list[dict], exchanges: list[dict],
                       attachments: list[str]) -> list[str]:
    """Send the run report. Raises on misconfiguration/SMTP errors so the
    caller can log it; never called unless the env is configured."""
    to_raw = os.getenv("REPORT_EMAIL_TO", "").strip()
    user = os.getenv("REPORT_EMAIL_USER", "").strip()
    # Google shows App Passwords as 4 space-separated groups ("abcd efgh ...").
    # SMTP wants them with no spaces, so strip all whitespace defensively.
    password = "".join(os.getenv("REPORT_EMAIL_PASSWORD", "").split())

    missing = [name for name, val in (
        ("REPORT_EMAIL_TO", to_raw),
        ("REPORT_EMAIL_USER", user),
        ("REPORT_EMAIL_PASSWORD", password),
    ) if not val]
    if missing:
        raise RuntimeError(f"email not sent - missing env var(s): {', '.join(missing)}")

    recipients = [addr.strip() for addr in to_raw.split(",") if addr.strip()]
    sender = os.getenv("REPORT_EMAIL_FROM", "").strip() or user
    host = os.getenv("REPORT_EMAIL_HOST", "smtp.gmail.com").strip()
    port = int(os.getenv("REPORT_EMAIL_PORT", "587"))

    msg = EmailMessage()
    msg["Subject"] = _subject(summary)
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.set_content(_body(summary, test_results, exchanges))
    msg.add_alternative(_html_body(summary, test_results, exchanges), subtype="html")

    for path_str in attachments:
        path = Path(path_str)
        if not path.exists():
            continue
        ctype, _ = mimetypes.guess_type(path.name)
        maintype, subtype = (ctype.split("/", 1) if ctype else ("application", "octet-stream"))
        msg.add_attachment(path.read_bytes(), maintype=maintype, subtype=subtype, filename=path.name)

    # Large attachments upload slowly; a short timeout aborts mid-send with
    # "Server not connected". Allow ample time.
    with smtplib.SMTP(host, port, timeout=300) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(msg)

    return recipients
