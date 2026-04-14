# career-ai

> AI-powered job search automation — YAML-driven, CLI-first, OpenClaw-optimized.

Built for engineers who want a systematic, low-cost way to discover relevant jobs, score them against their profile, and generate truthful ATS-optimized applications — without spamming companies or wasting tokens.

---

## How It Works

```
career scan → career score → career apply <id> → career track
```

| Stage | Command | AI Cost | What It Does |
|-------|---------|---------|--------------|
| Discover | `career scan` | **$0** | Hits Greenhouse / Lever / Ashby APIs directly |
| Score | `career score` | Claude (batched) | Scores all new jobs 0–100 against your profile |
| Apply | `career apply <id>` | Claude (1 call) | Generates ATS summary, cover letter, keywords |
| Auto-fill | `career autoapply <id>` | $0 | Playwright fills form — pauses before submit |
| Track | `career track` | **$0** | Rich table of all applications |

### OpenClaw Memory Layer

This system is built on OpenClaw principles — persistent context is never reprocessed:

- **`CLAUDE.md`** — loaded by Claude Code once per session; the agent already knows your profile
- **Zero-token scan** — `career scan` is pure HTTP with no AI calls whatsoever
- **Prompt caching** — your profile YAML is embedded as an Anthropic `cache_control: ephemeral` system block, tokenized exactly once per session regardless of how many jobs you score
- **Incremental pipeline** — each stage skips items it has already processed; running `career score` twice scores nothing the second time

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/AhsanKhaan/career-ai.git
cd career-ai
pip install -e .
playwright install chromium
```

### 2. Configure

```bash
cp config/profile.example.yml config/profile.yml
cp config/portals.example.yml config/portals.yml
cp .env.example .env
```

Edit `config/profile.yml` with your details:

```yaml
candidate:
  full_name: "Your Name"
  email: "you@example.com"
  location: "City, Country"

target_roles:
  primary:
    - "Senior Frontend Engineer"
    - "Full Stack Engineer"
```

Add your Anthropic API key to `.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Run the pipeline

```bash
# Discover new jobs (free — no AI)
career scan

# Score all new jobs against your profile
career score

# Generate application materials for a high-scored job
career apply abc123def456

# View all applications
career track
```

---

## Configuration

### `config/profile.yml` — Your Identity

The single source of truth for who you are. Never auto-modified.

```yaml
candidate:
  full_name: "Ahsan Khan"
  email: "you@example.com"
  phone: "+1-555-000-0000"
  location: "Karachi, Pakistan"
  linkedin: "linkedin.com/in/yourhandle"
  portfolio_url: "https://yourportfolio.com"

target_roles:
  primary:
    - "Senior Frontend Engineer"
    - "Full Stack Engineer"
  archetypes:
    - name: "Senior Frontend Engineer"
      level: "Senior"
      fit: "primary"

narrative:
  headline: "Senior Engineer | 5+ Years | React, TypeScript"
  superpowers:
    - "Frontend architecture at scale"
    - "Performance optimization"

compensation:
  target_range: "$120,000–$160,000/year"
  currency: "USD"

skills:
  languages: [TypeScript, JavaScript, Python]
  frameworks: [React, Next.js, Node.js]
```

### `config/portals.yml` — Job Sources

Controls which companies are scanned and which titles pass the filter.

```yaml
title_filter:
  positive: [Frontend, React, Full Stack, TypeScript]
  negative: [Junior, Intern, DevOps, Blockchain]

tracked_companies:
  - name: Anthropic
    careers_url: https://job-boards.greenhouse.io/anthropic
    api: https://boards-api.greenhouse.io/v1/boards/anthropic/jobs
    enabled: true

  - name: Mistral AI
    careers_url: https://jobs.lever.co/mistral
    enabled: true

  - name: ElevenLabs
    careers_url: https://jobs.ashbyhq.com/elevenlabs
    enabled: true
```

Supported portals: **Greenhouse**, **Lever**, **Ashby**, **Wellfound** (Playwright-based).

---

## CLI Reference

```
career scan                          Discover new jobs — zero AI cost
career score                         Score unscored jobs via Claude (batched)
career apply <job_id>                Generate ATS summary, cover letter, keywords
career autoapply <job_id>            Playwright form fill → pause → you confirm
career track                         Show application status table
career status <job_id> <status>      Update application status
```

**Valid statuses:** `pending` `scored` `applied` `interview` `offer` `rejected` `discarded`

---

## Output Format

Every processed job produces a standard JSON record in the cache:

```json
{
  "job_id": "a3f9c12b4e51",
  "company": "Acme Corp",
  "title": "Senior Frontend Engineer",
  "location": "Remote",
  "score": 82,
  "decision": "strong",
  "ats_summary": "Senior Frontend Engineer with 5+ years building React systems at scale...",
  "cover_letter": "Dear Hiring Team...",
  "keywords": ["React", "TypeScript", "Next.js", "AWS", "Node.js"]
}
```

---

## Auto-Apply

`career autoapply <job_id>` uses Playwright to fill application forms. **It never submits without your explicit confirmation.**

```
Auto-apply will:
  1. Open the job URL
  2. Fill form fields from your profile
  3. Upload your resume (if found in output/)
  4. PAUSE — you review in the browser
  5. Submit only after you press Enter in the terminal
```

Supported form types: **Greenhouse**, **Lever**, **Ashby**.

---

## Data Storage

```
data/cache/                   Job scan results (JSON, one file per date)
  └── 2026-04-14.json         Append-only; scores/materials written back in-place
data/career-ai.db             SQLite application tracker
output/                       Resume PDFs (for upload during autoapply)
```

**Data contract:**

| Path | Owner | Rule |
|------|-------|------|
| `config/profile.yml` | **You** | Never auto-modified |
| `config/portals.yml` | **You** | Never auto-modified |
| `data/` | System | Runtime data, gitignored |
| `prompts/` | System | Prompt templates, safe to update |

---

## Architecture

```
career_ai/
├── cli.py              Typer CLI — lazy imports, no startup cost
├── config.py           Singleton loader — profile + portals read once
├── models.py           Job, Application dataclasses
├── session.py          In-process dedup state
├── ai/
│   ├── client.py       Anthropic wrapper — profile in ephemeral cache block
│   └── prompts.py      On-demand loader from prompts/*.md
├── pipeline/
│   ├── scan.py         Zero-token HTTP scraping + dedup
│   ├── score.py        Batched Claude scoring (20 jobs/call)
│   ├── apply.py        Single-job application generation
│   └── track.py        SQLite → Rich table
├── scrapers/
│   ├── greenhouse.py   boards-api.greenhouse.io — single call with content
│   ├── lever.py        api.lever.co/v0/postings — top-level list
│   ├── ashby.py        api.ashbyhq.com — list + per-job detail
│   └── wellfound.py    Playwright-based (optional)
├── storage/
│   ├── cache.py        JSON file operations — append, dedup, update in-place
│   └── tracker.py      SQLite CRUD — applications table
└── autoapply/
    ├── runner.py        Safety gate + handler dispatch
    └── forms/           Greenhouse / Lever / Ashby form handlers
```

---

## Requirements

- Python 3.11+
- `ANTHROPIC_API_KEY` — only needed for `career score` and `career apply`
- Playwright Chromium — only needed for `career autoapply` and Wellfound scraping

---

## Customization

The system is designed to be edited directly. Ask your AI agent to:

```
"Add these companies to portals.yml: Linear, Figma, Notion"
"Update my target roles to include Backend Engineer"
"Change the scoring prompt to weight TypeScript experience more heavily"
"Translate the prompts to German for DACH market applications"
```

All user data lives in `config/profile.yml` and `config/portals.yml` — never in source files.

---

## Ethical Use

- Applications are **never submitted automatically** — `autoapply` always pauses for your review
- The generator uses **only facts from your profile** — no hallucinated experience
- Score below 50 means skip — quality applications to fewer companies beats spam
- Every application a recruiter reads costs their attention — make it worth reading

---

## Related

- **[career-ops](https://github.com/santifer/career-ops)** — the Node.js system this is inspired by, built by [@santifer](https://santifer.io)

---

## License

MIT
