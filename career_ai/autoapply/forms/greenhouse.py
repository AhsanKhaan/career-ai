"""Greenhouse application form handler.

Fills fields, then STOPS. User must press Enter to submit.
Never auto-clicks the submit button without human confirmation.
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

from career_ai.models import Job

console = Console()


class GreenhouseFormHandler:
    async def fill_and_pause(self, job: Job, profile: dict) -> None:
        from playwright.async_api import async_playwright

        candidate = profile.get("candidate", {})
        full_name = candidate.get("full_name", "")
        first_name = full_name.split()[0] if full_name else ""
        last_name = full_name.split()[-1] if len(full_name.split()) > 1 else ""
        email = candidate.get("email", "")
        phone = candidate.get("phone", "")

        resume_path = _find_resume()

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)  # visible so user can review
            page = await browser.new_page()

            console.print(f"[cyan]Opening: {job.url}[/cyan]")
            await page.goto(job.url, timeout=30000)
            await page.wait_for_load_state("networkidle", timeout=15000)

            # Fill name fields
            await _try_fill(page, 'input[name="first_name"], input[id*="first_name"]', first_name)
            await _try_fill(page, 'input[name="last_name"], input[id*="last_name"]', last_name)
            await _try_fill(page, 'input[name="email"], input[type="email"]', email)
            await _try_fill(page, 'input[name="phone"], input[type="tel"]', phone)

            # Cover letter
            if job.cover_letter:
                await _try_fill(
                    page,
                    'textarea[name*="cover"], textarea[id*="cover"]',
                    job.cover_letter,
                )

            # Resume upload
            if resume_path:
                file_input = await page.query_selector('input[type="file"]')
                if file_input:
                    await file_input.set_input_files(str(resume_path))
                    console.print(f"[green]Resume uploaded: {resume_path.name}[/green]")

            console.print(
                "\n[bold yellow]Form filled.[/bold yellow] "
                "Review the browser window, then press Enter here to submit "
                "(or Ctrl+C to abort without submitting)."
            )
            input()

            # Submit
            submit = await page.query_selector(
                'input[type="submit"], button[type="submit"], button:text("Submit")'
            )
            if submit:
                await submit.click()
                console.print("[green]✓ Application submitted.[/green]")
                await page.wait_for_load_state("networkidle", timeout=15000)
            else:
                console.print("[yellow]Submit button not found — please submit manually.[/yellow]")
                input("Press Enter when done...")

            await browser.close()


async def _try_fill(page, selector: str, value: str) -> None:
    if not value:
        return
    try:
        el = await page.query_selector(selector)
        if el:
            await el.fill(value)
    except Exception:
        pass


def _find_resume() -> Path | None:
    """Look for resume file in common locations."""
    candidates = [
        Path("output/resume.pdf"),
        Path("output/cv.pdf"),
        Path("cv.pdf"),
        Path("resume.pdf"),
    ]
    for p in candidates:
        if p.exists():
            return p
    return None
