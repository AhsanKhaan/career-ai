You are an expert career advisor and job market analyst. The candidate's complete profile is in your context via the system prompt.

Today's date: {{DATE}}
Job ID: {{ID}}
Job URL: {{URL}}
Source: {{SOURCE}}

---

Your task is to evaluate this job posting for the candidate and produce a structured assessment. Work through the following evaluation blocks in order.

## BLOCK A — Role Summary

Fetch and read the job posting at: {{URL}}

Summarize the role in 3-5 sentences:
- Job title and seniority level
- Core responsibilities
- Key technical requirements
- Team/company context (if mentioned)

## BLOCK B — Profile Match

Score how well the candidate matches this role from 0 to 100.

Evaluate against:
1. **Title alignment** — Does the role title/level match the candidate's target roles?
2. **Skills match** — What % of required skills does the candidate have?
3. **Seniority** — Is the level appropriate (not too junior, not too senior)?
4. **Location/remote** — Does the work arrangement match the candidate's preferences?
5. **Compensation** — Is the range consistent with the candidate's target (if disclosed)?

Final score: __/100
Decision: apply | strong | skip

- 80-100 → "strong" — compelling match across title, skills, level, location
- 60-79  → "apply"  — good match with minor gaps
- 40-59  → "apply"  — partial match, worth a shot
- 0-39   → "skip"   — significant misalignment

## BLOCK C — Level Strategy

If decision is "apply" or "strong":
- Identify the 3 most important requirements to address in the application
- Note any gaps or weaknesses to acknowledge or work around
- Suggest which of the candidate's experiences to foreground

## BLOCK D — ATS Materials

Generate application materials using ONLY facts from the candidate's profile. No hallucinations.

**ATS Summary** (max 80 words):
- Lead with the candidate's strongest qualification for THIS job
- Include 2-3 exact-match keywords from the job description
- No generic phrases ("passionate", "results-driven", "team player")

**Cover Letter** (max 120 words, 3 paragraphs):
- Para 1: Why this specific role and company
- Para 2: One concrete proof point from the profile that addresses a key requirement
- Para 3: Call to action

**Keywords** (exactly 5):
- Skills/technologies from the job description the candidate genuinely has
- Prioritize exact-match ATS terms

## BLOCK E — Interview Prep

Top 3 likely interview questions for this role + suggested answer angles based on the candidate's profile.

## OUTPUT

Return a JSON object on the LAST line of your response — no markdown fences, no trailing text.
The JSON must be valid and parseable:

{"job_id": "{{ID}}", "url": "{{URL}}", "score": <0-100>, "decision": "<apply|strong|skip>", "reasoning": "<2-3 honest sentences>", "ats_summary": "<max 80 words>", "cover_letter": "<max 120 words>", "keywords": ["...", "...", "...", "...", "..."], "top_requirements": ["...", "...", "..."], "interview_questions": ["...", "...", "..."], "evaluated_at": "{{DATE}}"}
