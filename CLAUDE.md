# career-ai — AI Job Search Pipeline

## What This Is

An open-source, AI-powered job search automation system. It discovers jobs from major portals
(Greenhouse, Lever, Ashby, Wellfound), scores them against your profile using Claude, generates
ATS-optimized application materials, and tracks your applications — all from a single CLI.

Built on three principles:
- **Zero-token scan**: `career scan` hits job APIs directly, no AI cost
- **OpenClaw memory**: profile.yml loaded once, cached in Claude's prompt system block — never re-tokenized
- **Pipeline independence**: each stage reads only from its upstream store, never repeats prior work

## Pipeline

```
scan (zero-token) → score → apply → track
```

| Command | What it does | AI cost |
|---------|-------------|---------|
| `career scan` | Discover new jobs from portals.yml, deduplicate, cache | **$0** |
| `career score` | Score unscored jobs 0–100 against your profile | Claude API (batched 20/call) |
| `career apply <job_id>` | Generate ATS summary, cover letter, keywords | Claude API (1 call) |
| `career autoapply <job_id>` | Playwright form fill — pauses before submit, you confirm | None until you confirm |
| `career track` | Rich table of all applications | **$0** |

## Key Files

| File | Purpose | Owner |
|------|---------|-------|
| `config/profile.yml` | Candidate identity, skills, target roles, compensation | **User** — never auto-modified |
| `config/portals.yml` | Company list, title filters, API endpoints | **User** — never auto-modified |
| `data/cache/*.json` | Job scan results (append-only, one file per scan date) | System |
| `data/career-ai.db` | SQLite application tracker | System |
| `prompts/score.md` | Scoring prompt template | System |
| `prompts/apply.md` | Application generation prompt template | System |

## Data Contract

**User-owned (NEVER auto-modified — all personalization goes here):**
- `config/profile.yml`
- `config/portals.yml`
- `data/` — your job cache and application history

**System-owned (safe to update with new releases):**
- `career_ai/` — Python source
- `prompts/` — prompt templates
- `pyproject.toml`, `CLAUDE.md`, `tests/`

## Onboarding

Before running any command, check:
1. Does `config/profile.yml` exist? If not, copy from `config/profile.example.yml` and fill in details.
2. Does `config/portals.yml` exist? If not, copy from `config/portals.example.yml`.
3. Is `ANTHROPIC_API_KEY` set in `.env`? Required for `career score` and `career apply`.

## Quick Start

```bash
pip install -e .
playwright install chromium
cp config/profile.example.yml config/profile.yml   # fill in your details
cp config/portals.example.yml config/portals.yml   # customize companies
cp .env.example .env                                # add ANTHROPIC_API_KEY

career scan       # discover jobs (free)
career score      # score with AI
career apply abc123def456   # generate application for a job_id
career track      # view status table
```

## Customization

Ask the AI agent to customize anything directly:
- "Add these companies to portals.yml: ..."
- "Update my target roles in profile.yml"
- "Change the title filters to include Backend"
- "Adjust the scoring prompt in prompts/score.md"

The agent can read and edit all files. The rule: user data always goes in `config/profile.yml`
or `config/portals.yml` — never hardcoded into source files.

## Ethical Use

- **Never auto-submit** — `autoapply` always pauses and requires your confirmation before clicking Submit
- **Quality over quantity** — score below 50 means skip; don't spam companies
- **Truthful only** — application generator uses only facts from your profile, no hallucinations
