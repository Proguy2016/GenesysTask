"""Turn a generated HTML report into a PDF.

Strategy, in order of preference:

1. A locally installed Chrome or Edge in headless mode. Zero extra packages,
   and it is the same engine the report was designed against, so the `@media
   print` rules in `theme.py` are honoured exactly.
2. Playwright's bundled Chromium, if the package is installed.
3. WeasyPrint, if the package is installed.

Everything runs locally: the HTML file is loaded over `file://` and nothing is
uploaded anywhere. The only network access is the Google Fonts stylesheet the
page links; with no connection the report falls back to its local font stack and
still renders correctly.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile

log = logging.getLogger(__name__)

WINDOWS_BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]
UNIX_BROWSERS = [
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
    "microsoft-edge", "microsoft-edge-stable",
]


class PdfUnavailable(RuntimeError):
    """No local renderer could be found."""


def find_browser() -> str | None:
    """Path to a locally installed Chromium-family browser, if there is one."""
    for candidate in WINDOWS_BROWSERS:
        if os.path.isfile(candidate):
            return candidate
    for name in UNIX_BROWSERS:
        found = shutil.which(name)
        if found:
            return found
    return None


def _file_url(path: str) -> str:
    from urllib.parse import quote

    return "file:///" + quote(os.path.abspath(path).replace(os.sep, "/"))


def _via_browser(browser: str, html_path: str, pdf_path: str, timeout: int) -> None:
    # A fresh profile directory keeps the run from touching the user's own
    # browser profile, and keeps concurrent conversions from colliding.
    with tempfile.TemporaryDirectory(prefix="flowdoc-pdf-") as profile:
        command = [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox" if os.name != "nt" else "--disable-extensions",
            f"--user-data-dir={profile}",
            "--no-pdf-header-footer",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=8000",
            f"--print-to-pdf={os.path.abspath(pdf_path)}",
            _file_url(html_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        if not os.path.isfile(pdf_path) or os.path.getsize(pdf_path) == 0:
            detail = (result.stderr or result.stdout or "").strip()[:500]
            raise PdfUnavailable(f"{os.path.basename(browser)} produced no PDF. {detail}")


def _via_playwright(html_path: str, pdf_path: str) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        browser = play.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(_file_url(html_path), wait_until="networkidle")
            page.pdf(path=os.path.abspath(pdf_path), format="A4", print_background=True,
                     margin={"top": "14mm", "bottom": "14mm", "left": "12mm", "right": "12mm"})
        finally:
            browser.close()


def _via_weasyprint(html_path: str, pdf_path: str) -> None:
    from weasyprint import HTML  # type: ignore

    HTML(filename=os.path.abspath(html_path)).write_pdf(os.path.abspath(pdf_path))


def prepare_for_print(html_path: str, work_dir: str) -> str:
    """Write a print-ready copy of the report and return its path.

    Collapsed `<details>` sections print as nothing but their summary line, so
    a technical specification would lose every configuration table. Opening
    them for the PDF keeps the on-screen document compact while making the
    printed one complete. The screen file itself is never modified.
    """
    with open(html_path, encoding="utf-8") as handle:
        markup = handle.read()
    markup = re.sub(r"<details(?![^>]*\bopen\b)", "<details open", markup)

    printable = os.path.join(work_dir, os.path.basename(html_path))
    with open(printable, "w", encoding="utf-8") as handle:
        handle.write(markup)
    return printable


def html_to_pdf(html_path: str, pdf_path: str | None = None, timeout: int = 120) -> str:
    """Render `html_path` to PDF and return the path written."""
    if not os.path.isfile(html_path):
        raise FileNotFoundError(html_path)
    # Strip only the .html suffix, so `x.business.html` becomes `x.business.pdf`
    # and does not collide with `x.technical.html`.
    pdf_path = pdf_path or os.path.splitext(html_path)[0] + ".pdf"
    if not pdf_path.endswith(".pdf"):
        pdf_path += ".pdf"
    os.makedirs(os.path.dirname(os.path.abspath(pdf_path)) or ".", exist_ok=True)

    problems: list[str] = []

    with tempfile.TemporaryDirectory(prefix="flowdoc-src-") as work_dir:
        printable = prepare_for_print(html_path, work_dir)

        browser = find_browser()
        if browser:
            try:
                _via_browser(browser, printable, pdf_path, timeout)
                log.info("Rendered %s with %s", os.path.basename(pdf_path),
                         os.path.basename(browser))
                return pdf_path
            except Exception as exc:                   # noqa: BLE001 - try the next one
                problems.append(f"{os.path.basename(browser)}: {exc}")

        for label, renderer in (("playwright", _via_playwright),
                                ("weasyprint", _via_weasyprint)):
            try:
                renderer(printable, pdf_path)
                log.info("Rendered %s with %s", os.path.basename(pdf_path), label)
                return pdf_path
            except ImportError:
                continue
            except Exception as exc:                   # noqa: BLE001
                problems.append(f"{label}: {exc}")

    raise PdfUnavailable(
        "No local PDF renderer worked. Install Google Chrome or Microsoft Edge, or "
        "run `pip install playwright && playwright install chromium`.\n"
        + "\n".join(f"  - {p}" for p in problems)
    )


def convert_all(paths: list[str]) -> list[str]:
    """Convert several reports, carrying on past any that fail."""
    written: list[str] = []
    for path in paths:
        if not path.endswith(".html"):
            continue
        try:
            written.append(html_to_pdf(path))
        except Exception as exc:                       # noqa: BLE001
            log.warning("Could not convert %s: %s", os.path.basename(path), exc)
    return written
