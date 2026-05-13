cat > /home/rusbeh_ab/project/AkbarOurDearFriend/MD_Print.py <<'PY'
from pathlib import Path
import subprocess
import sys
import re
import shutil


MD_FILE = Path("/home/rusbeh_ab/project/AkbarOurDearFriend/ErsteSchritte_AGENT_CHATGTP.md")
PDF_FILE = MD_FILE.with_suffix(".pdf")
HTML_FILE = MD_FILE.with_suffix(".preview.html")


def log(text: str) -> None:
    print(text, flush=True)


def run_cmd(cmd: list[str]) -> None:
    log("RUN: " + " ".join(cmd))
    subprocess.check_call(cmd)


def ensure_python_package(import_name: str, pip_name: str | None = None) -> None:
    pip_name = pip_name or import_name
    try:
        __import__(import_name)
        log(f"OK: Python package '{import_name}' is already installed.")
    except ImportError:
        log(f"INSTALL: Python package '{pip_name}'")
        run_cmd([sys.executable, "-m", "pip", "install", pip_name])


def prepare_markdown(md_text: str) -> str:
    md_text = re.sub(
        r"^- \[ \] (.+)$",
        r"- <span class='checkbox'></span> \1",
        md_text,
        flags=re.MULTILINE,
    )
    return md_text


def build_html(body_html: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>Erste Schritte</title>

<style>
@page {{
    size: A4;
    margin: 20mm 16mm 20mm 16mm;
}}

body {{
    font-family: Arial, "Liberation Sans", sans-serif;
    font-size: 11pt;
    line-height: 1.5;
    color: #222;
}}

h1 {{
    font-size: 22pt;
    margin-top: 0;
    margin-bottom: 18px;
    border-bottom: 2px solid #333;
    padding-bottom: 8px;
}}

h2 {{
    font-size: 15pt;
    margin-top: 26px;
    margin-bottom: 10px;
    border-bottom: 1px solid #bbb;
    padding-bottom: 4px;
    break-after: avoid;
}}

h3 {{
    font-size: 13pt;
    margin-top: 20px;
    margin-bottom: 8px;
}}

p {{
    margin: 6px 0 10px 0;
}}

ul {{
    margin-top: 6px;
    margin-bottom: 12px;
    padding-left: 22px;
}}

li {{
    margin-bottom: 6px;
}}

hr {{
    border: none;
    border-top: 1px solid #ccc;
    margin: 22px 0;
}}

.checkbox {{
    display: inline-block;
    width: 11px;
    height: 11px;
    border: 1.5px solid #333;
    margin-right: 7px;
    vertical-align: -1px;
}}

code {{
    font-family: Consolas, "Liberation Mono", monospace;
    font-size: 10pt;
}}

strong {{
    font-weight: 600;
}}
</style>
</head>

<body>
{body_html}
</body>
</html>
"""


def open_pdf_in_windows(pdf_file: Path) -> None:
    if shutil.which("wslpath") and shutil.which("explorer.exe"):
        win_path = subprocess.check_output(
            ["wslpath", "-w", str(pdf_file)],
            text=True
        ).strip()

        log(f"OPEN: {win_path}")
        subprocess.Popen(["explorer.exe", win_path])
    else:
        log("PDF created, but automatic Windows opening is not available in this environment.")


def main() -> None:
    log("START: Markdown to PDF")
    log(f"Markdown file: {MD_FILE}")
    log(f"HTML output:   {HTML_FILE}")
    log(f"PDF output:    {PDF_FILE}")

    if not MD_FILE.exists():
        raise FileNotFoundError(f"Markdown file not found: {MD_FILE}")

    ensure_python_package("markdown", "markdown")
    ensure_python_package("playwright", "playwright")

    import markdown
    from playwright.sync_api import sync_playwright

    md_text = MD_FILE.read_text(encoding="utf-8")
    md_text = prepare_markdown(md_text)

    body_html = markdown.markdown(
        md_text,
        extensions=["extra", "sane_lists", "toc"]
    )

    full_html = build_html(body_html)
    HTML_FILE.write_text(full_html, encoding="utf-8")

    log("HTML created successfully.")

    try:
        with sync_playwright() as p:
            log("Launching Chromium...")
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(HTML_FILE.as_uri(), wait_until="networkidle")
            page.pdf(
                path=str(PDF_FILE),
                format="A4",
                print_background=True,
                margin={
                    "top": "18mm",
                    "right": "16mm",
                    "bottom": "18mm",
                    "left": "16mm",
                },
            )
            browser.close()

    except Exception as exc:
        log("Chromium was missing or failed.")
        log(f"Reason: {exc}")
        log("Installing Chromium for Playwright...")
        run_cmd([sys.executable, "-m", "playwright", "install", "chromium"])

        with sync_playwright() as p:
            log("Launching Chromium again...")
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(HTML_FILE.as_uri(), wait_until="networkidle")
            page.pdf(
                path=str(PDF_FILE),
                format="A4",
                print_background=True,
                margin={
                    "top": "18mm",
                    "right": "16mm",
                    "bottom": "18mm",
                    "left": "16mm",
                },
            )
            browser.close()

    if not PDF_FILE.exists():
        raise RuntimeError("PDF was not created.")

    log("SUCCESS: PDF created.")
    log(str(PDF_FILE))

    open_pdf_in_windows(PDF_FILE)


if __name__ == "__main__":
    main()
PY