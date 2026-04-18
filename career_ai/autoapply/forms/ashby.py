"""Ashby application form handler."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

from career_ai.models import Job

console = Console()


class AshbyFormHandler:
    async def fill_and_pause(
        self,
        job: Job,
        profile: dict,
        resume_pdf: Path | None = None,
    ) -> None:
        from playwright.async_api import async_playwright

        candidate = profile.get("candidate", {})
        full_name = candidate.get("full_name", "")
        first_name = full_name.split()[0] if full_name else ""
        last_name = full_name.split()[-1] if len(full_name.split()) > 1 else ""
        email = candidate.get("email", "")
        phone = candidate.get("phone", "")
        linkedin = candidate.get("linkedin", "")
        resume_path = resume_pdf if resume_pdf and Path(resume_pdf).exists() else _find_resume()

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()

            console.print(f"[cyan]Opening: {job.url}[/cyan]")
            await page.goto(job.url, timeout=30000)
            await page.wait_for_load_state("networkidle", timeout=15000)

            # Ashby uses label-based form fields
            await _try_fill_by_label(page, "First Name", first_name)
            await _try_fill_by_label(page, "Last Name", last_name)
            await _try_fill_by_label(page, "Email", email)
            await _try_fill_by_label(page, "Phone", phone)

            if linkedin:
                await _try_fill_by_label(page, "LinkedIn", linkedin)

            if job.cover_letter:
                await _try_fill_by_label(page, "Cover Letter", job.cover_letter)

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
                'button[type="submit"], button:text("Submit"), button:text("Apply")'
            )
            if submit:
                await submit.click()
                console.print("[green]✓ Application submitted.[/green]")
                await page.wait_for_load_state("networkidle", timeout=15000)
            else:
                console.print("[yellow]Submit button not found — please submit manually.[/yellow]")
                input("Press Enter when done...")

            await browser.close()


async def _try_fill_by_label(page, label_text: str, value: str) -> None:
    if not value:
        return
    try:
        # Find input associated with a label containing label_text
        label = await page.query_selector(f'label:has-text("{label_text}")')
        if label:
            for_attr = await label.get_attribute("for")
            if for_attr:
                el = await page.query_selector(f"#{for_attr}")
                if el:
                    tag = await el.evaluate("el => el.tagName.toLowerCase()")
                    if tag == "textarea":
                        await el.fill(value)
                    else:
                        await el.fill(value)
    except Exception:
        pass


def _find_resume() -> Path | None:
    candidates = [Path("output/resume.pdf"), Path("output/cv.pdf"), Path("cv.pdf"), Path("resume.pdf")]
    for p in candidates:
        if p.exists():
            return p
    return None
