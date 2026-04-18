"""Résumé generation: tailor + render a DOCX/PDF for a specific job.

Two-step flow:
  1. generator.generate_resume(profile, job, keywords) → structured JSON
  2. renderer.render_docx(resume_json, path)          → output/resume-<id>.docx
     renderer.convert_to_pdf(docx_path, pdf_path)      → output/resume-<id>.pdf
"""

from career_ai.resume.generator import generate_resume
from career_ai.resume.renderer import convert_to_pdf, render_docx

__all__ = ["generate_resume", "render_docx", "convert_to_pdf"]
