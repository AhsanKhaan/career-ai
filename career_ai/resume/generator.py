"""Generate a tailored résumé as structured JSON.

Asks claude (via the shared CareerAIClient) to pull bullets from the
candidate's profile that best match the target job and its keywords.
Strict JSON-only output, single retry on parse failure.
"""

from __future__ import annotations

import json
import re

from career_ai.ai.client import get_claude_client
from career_ai.ai.prompts import load_prompt
from career_ai.models import Job


def generate_resume(job: Job, keywords: list[str]) -> dict:
    """Return a résumé dict tailored to `job`. Never raises on empty output.

    Shape:
        {
          "name": str,
          "contact": {"email": str, "phone": str, "location": str, "links": [str]},
          "summary": str,
          "experience": [{"company", "title", "dates", "location", "bullets": [str]}],
          "skills": [str],
          "education": [{"school", "degree", "dates"}]
        }

    If claude fails twice, returns an empty-but-valid skeleton so the
    caller can decide whether to fall back to a generic résumé.
    """
    client = get_claude_client()
    prompt = load_prompt(
        "resume",
        job_title=job.title,
        job_company=job.company,
        job_location=job.location,
        job_url=job.url,
        job_description=job.description[:4000],
        keywords_json=json.dumps(keywords, ensure_ascii=False),
    )

    raw = client._call(prompt)
    data = _parse_json_object(raw)

    if data is None:
        raw = client._call(prompt + "\n\nReturn ONLY the JSON object. No other text.")
        data = _parse_json_object(raw)

    if data is None:
        return _empty_skeleton()

    return _normalize(data)


def _parse_json_object(text: str) -> dict | None:
    text = text.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        result = json.loads(match.group())
        return result if isinstance(result, dict) else None
    except json.JSONDecodeError:
        return None


def _normalize(data: dict) -> dict:
    """Coerce claude's output into the canonical shape with safe defaults."""
    contact_in = data.get("contact") or {}
    contact = {
        "email": str(contact_in.get("email", "")).strip(),
        "phone": str(contact_in.get("phone", "")).strip(),
        "location": str(contact_in.get("location", "")).strip(),
        "links": [str(link).strip() for link in (contact_in.get("links") or []) if str(link).strip()],
    }

    experience = []
    for role in data.get("experience") or []:
        if not isinstance(role, dict):
            continue
        experience.append({
            "company": str(role.get("company", "")).strip(),
            "title": str(role.get("title", "")).strip(),
            "dates": str(role.get("dates", "")).strip(),
            "location": str(role.get("location", "")).strip(),
            "bullets": [str(b).strip() for b in (role.get("bullets") or []) if str(b).strip()],
        })

    education = []
    for edu in data.get("education") or []:
        if not isinstance(edu, dict):
            continue
        education.append({
            "school": str(edu.get("school", "")).strip(),
            "degree": str(edu.get("degree", "")).strip(),
            "dates": str(edu.get("dates", "")).strip(),
        })

    return {
        "name": str(data.get("name", "")).strip(),
        "contact": contact,
        "summary": str(data.get("summary", "")).strip(),
        "experience": experience,
        "skills": [str(s).strip() for s in (data.get("skills") or []) if str(s).strip()],
        "education": education,
    }


def _empty_skeleton() -> dict:
    return {
        "name": "",
        "contact": {"email": "", "phone": "", "location": "", "links": []},
        "summary": "",
        "experience": [],
        "skills": [],
        "education": [],
    }
