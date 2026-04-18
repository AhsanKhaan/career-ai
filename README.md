# career-ai

> AI-powered job search automation — YAML-driven, CLI-first, OpenClaw-optimized.

Built for engineers who want a systematic way to discover relevant jobs, score them against their profile, and generate truthful ATS-optimized applications — without an API key, without spamming companies, and without wasting tokens.

**No API key required.** Uses the `claude` CLI with a Claude Max/Pro subscription — the same pattern as [career-ops](https://github.com/santifer/career-ops).

---

## How It Works

```
career scan → career score → career apply <id> → career track
              ─── or ───
career auto   (all stages in one command)
```

| Stage | Command | AI Cost | What It Does |
|-------|---------|---------|--------------|
| Discover | `career scan` | **$0** | Hits Greenhouse / Lever / Ashby APIs directly |
| Score | `career score` | claude CLI (batched) | Scores all new jobs 0–100 against your profile |
| Apply | `career apply <id>` | claude CLI (1 call) | Generates ATS summary, cover letter, keywords |
| **Paste-a-link** | **`career applylink <url>`** | **claude CLI (3 calls)** | **Paste any job URL → fetches JD, tailors an ATS résumé (DOCX+PDF), fills the form, pauses before submit** |
| Auto | `career auto` | claude CLI | Full pipeline: scan → score → apply all strong matches |
| Batch | `career batch` | claude CLI | Parallel workers — deep A-G evaluation per job |
| Auto-fill | `career autoapply <id>` | $0 | Playwright fills form — pauses before submit |
| Track | `career track` | **$0** | Rich table of all applications |

### OpenClaw Memory Layer

This system is built on OpenClaw principles — persistent context is never reprocessed:

- **`CLAUDE.md`** — loaded by Claude Code once per session; the agent already knows your pipeline
- **Zero-token scan** — `career scan` is pure HTTP with no AI calls whatsoever
- **Profile context** — your profile YAML is written to `batch/.profile-context.md` once per session and passed via `--append-system-prompt-file` on every `claude -p` call
- **Incremental pipeline** — each stage skips items it has already processed; running `career score` twice scores nothing the second time

---

## Quick Start

### 1. Prerequisites

```bash
# Install Claude Code CLI
# https://claude.ai/download
claude login   # Claude Max or Pro subscription — no API key
```

### 2. Install

```bash
git clone https://github.com/AhsanKhaan/career-ai.git
cd career-ai
pip install -e .
playwright install chromium
```

### 3. Configure

```bash
cp config/profile.example.yml config/profile.yml
cp config/portals.example.yml config/portals.yml
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

### 4. Run the pipeline

```bash
# Option A — Step by step
career scan                        # Discover new jobs (free)
career score                       # Score jobs against your profile
career apply abc123def456          # Generate application for a high-scored job
career track                       # View all applications

# Option B — Fully automated
career auto                        # scan + score + apply all strong matches
career auto --min-score 80         # Only apply for score >= 80

# Option C — Paste-a-link (one-shot, no scan required)
career applylink https://jobs.lever.co/<company>/<posting-id>
# → fetches JD via claude WebFetch
# → generates ATS summary, cover letter, keywords
# → tailors a résumé → output/resume-<job_id>.docx + .pdf
# → if Greenhouse/Lever/Ashby: opens browser, fills form, PAUSES
# → you press Enter to submit
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
career score                         Score unscored jobs via claude CLI (batched)
career apply <job_id>                Generate ATS summary, cover letter, keywords
career applylink <url>               Paste-a-link: URL → résumé (DOCX+PDF) → fill form → pause to submit
career auto [--min-score N]          Full pipeline: scan + score + apply all ≥ N
career autoapply <job_id>            Playwright form fill → pause → you confirm
career track                         Show application status table
career status <job_id> <status>      Update application status
career batch [options]               Parallel claude workers — deep per-job analysis
```

**Valid statuses:** `pending` `scored` `applied` `interview` `offer` `rejected` `discarded`

---

## Batch Mode (Deep Evaluation)

`career batch` spawns parallel `claude -p` workers for deep per-job evaluation using a 5-block analysis template:

- **A** — Role summary (fetches live job description)
- **B** — Profile match score (0-100) with reasoning
- **C** — Level strategy and gaps
- **D** — ATS materials (summary + cover letter + keywords)
- **E** — Interview prep questions

```bash
# Add jobs to the batch queue
career batch --add https://jobs.lever.co/company/abc123
career batch --add https://job-boards.greenhouse.io/acme/jobs/456

# Run all pending jobs (1 worker at a time)
career batch

# Run 3 workers in parallel
career batch --parallel 3

# Retry failed jobs
career batch --retry-failed

# Preview without executing
career batch --dry-run

# View batch state
career batch --status
```

You can also drive the batch runner directly from bash:

```bash
./batch/batch-runner.sh --parallel 3
./batch/batch-runner.sh --retry-failed
```

---

## Paste-a-Link Mode (`career applylink`)

The fastest path from "I just saw a job post" to "form is filled, ready to submit."

```bash
career applylink https://jobs.lever.co/acme/abc-123
```

What happens, in order:

1. **Fetch** — the `claude` CLI's WebFetch reads the job page and returns a structured JSON blob (title, company, location, description, requirements). Works for SPA boards where raw HTML scraping fails.
2. **Materials** — ATS summary (≤80 words), cover letter (≤120 words), and 5 ATS keywords.
3. **Résumé** — a fresh **ATS-friendly DOCX and PDF** rendered at `output/resume-<job_id>.docx` / `.pdf`. Single column, Calibri 11pt, Word's built-in "List Bullet" style, no tables or text boxes — the formula every major ATS parser handles cleanly. Bullets are pulled from your `profile.yml` and ordered/filtered by how well they match the job.
4. **Tracker** — SQLite row created with status `scored`.
5. **Fill** — if the URL is Greenhouse/Lever/Ashby, the browser opens and fills the form using your profile + the freshly tailored résumé.
6. **Pause** — you visually verify the form in the browser, then press Enter to submit. No auto-submit. Ever.
7. **Tracker** — status flipped to `applied` once you confirm.

**Unsupported URL hosts** (Workday, iCIMS, Taleo, etc.) still produce the tailored résumé + materials — you just apply manually and upload the generated PDF.

**Re-running with the same URL** is idempotent: steps 1–2 are skipped, the résumé is regenerated, and you jump straight to the preview panel.

### Requirements for PDF output

`docx2pdf` converts the DOCX to PDF using **Word on Windows** or **LibreOffice on Linux/macOS**. If neither is installed, the flow still succeeds — the form handler uploads the DOCX directly, which every major ATS (Greenhouse, Lever, Ashby, Workday) accepts.

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
batch/                        Batch runner inputs, state, and worker logs
  ├── batch-input.tsv         Job queue (you manage this)
  ├── batch-state.tsv         Auto-managed state (resumable, gitignored)
  ├── .profile-context.md     Profile written once per session (gitignored)
  ├── logs/                   Per-job worker logs (gitignored)
  └── tracker-additions/      Worker JSON output before merge (gitignored)
output/                       Resume PDFs (for upload during autoapply)
```

**Data contract:**

| Path | Owner | Rule |
|------|-------|------|
| `config/profile.yml` | **You** | Never auto-modified |
| `config/portals.yml` | **You** | Never auto-modified |
| `data/` | System | Runtime data, gitignored |
| `prompts/` | System | Prompt templates, safe to update |
| `batch/batch-input.tsv` | **You** | Your job queue — edit manually or via `--add` |

---

## Architecture

```
career_ai/
├── cli.py              Typer CLI — lazy imports, no startup cost
├── config.py           Singleton loader — profile + portals read once
├── models.py           Job, Application dataclasses
├── session.py          In-process dedup state
├── ai/
│   ├── client.py       claude CLI wrapper — profile in .profile-context.md
│   └── prompts.py      On-demand loader from prompts/*.md
├── pipeline/
│   ├── scan.py         Zero-token HTTP scraping + dedup
│   ├── score.py        Batched claude scoring (20 jobs/call)
│   ├── apply.py        Single-job application generation
│   ├── applylink.py    Paste-a-link: URL → JD → résumé → fill form
│   ├── batch.py        Parallel worker orchestration + merge
│   ├── auto.py         Full automated pipeline (scan+score+apply)
│   └── track.py        SQLite → Rich table
├── scrapers/
│   ├── greenhouse.py   boards-api.greenhouse.io — single call with content
│   ├── lever.py        api.lever.co/v0/postings — top-level list
│   ├── ashby.py        api.ashbyhq.com — list + per-job detail
│   ├── url_fetcher.py  Arbitrary URL → Job via claude WebFetch
│   └── wellfound.py    Playwright-based (optional)
├── resume/
│   ├── generator.py    claude → structured résumé JSON (tailored to job)
│   └── renderer.py     JSON → ATS-friendly DOCX + PDF
├── storage/
│   ├── cache.py        JSON file operations — append, dedup, update in-place
│   └── tracker.py      SQLite CRUD — applications table
└── autoapply/
    ├── runner.py        Safety gate + handler dispatch
    └── forms/           Greenhouse / Lever / Ashby form handlers

batch/
├── batch-runner.sh      Bash orchestrator — parallel claude -p workers
├── batch-prompt.md      Worker evaluation template (A-E blocks)
├── batch-input.tsv      Your job queue
└── logs/                Per-worker output logs
```

---

## Requirements

- Python 3.11+
- `claude` CLI installed and logged in (`claude login`) — Claude Max or Pro subscription
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
