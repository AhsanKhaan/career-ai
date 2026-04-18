"""Lever application form handler."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

from career_ai.models import Job

console = Console()


class LeverFormHandler:
    async def fill_and_pause(
        self,
        job: Job,
        profile: dict,
        resume_pdf: Path | None = None,
    ) -> None:
        from playwright.async_api import async_playwright

        candidate = profile.get("candidate", {})
        full_name = candidate.get("full_name", "")
        email = candidate.get("email", "")
        phone = candidate.get("phone", "")
        portfolio = candidate.get("portfolio_url", "")
        linkedin = candidate.get("linkedin", "")
        resume_path = resume_pdf if resume_pdf and Path(resume_pdf).exists() else _find_resume()

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()

            console.print(f"[cyan]Opening: {job.url}[/cyan]")
            await page.goto(job.url, timeout=30000)
            await page.wait_for_load_state("networkidle", timeout=15000)

            # Lever uses a single "name" field
            await _try_fill(page, 'input[name="name"]', full_name)
            await _try_fill(page, 'input[name="email"], input[type="email"]', email)
            await _try_fill(page, 'input[name="phone"], input[type="tel"]', phone)

            if portfolio:
                await _try_fill(page, 'input[name="urls[Portfolio]"], input[placeholder*="portfolio"]', portfolio)
            if linkedin:
                await _try_fill(page, 'input[name="urls[LinkedIn]"], input[placeholder*="linkedin"]', linkedin)

            if job.cover_letter:
                await _try_fill(
                    page,
                    'textarea[name*="comments"], textarea[name*="cover"]',
                    job.cover_letter,
                )

            if resume_path:
                file_input = await page.query_selector('input[type="file"]')
                if file_input:
                    await file_input.set_input_files(str(resume_path))
                    console.print(f"[green]Resume uploaded: {resume_path.name}[/green]")

            console.print(
                "\n[bold yellow]Form filled.[/bold yellow] "
                "Review the browser, then press Enter here to submit (or Ctrl+C to abort)."
            )
            input()

            submit = await page.query_selector(
                'button[type="submit"], input[type="submit"], button:text("Submit application")'
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
    candidates = [Path("output/resume.pdf"), Path("output/cv.pdf"), Path("cv.pdf"), Path("resume.pdf")]
    for p in candidates:
        if p.exists():
            return p
    return None
