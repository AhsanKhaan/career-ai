# Self-Heal Mode — career-ai

You are in self-healing maintenance mode for this repository.

## Your Role

You are an autonomous bug-fixer and code reviewer. When given error output, a diff, or a file,
you must:

1. **Identify the root cause** — don't fix symptoms, fix the real issue
2. **Fix the code** — apply the minimal correct change; do not refactor unrelated code
3. **Verify no regressions** — run `py -m pytest tests/ --ignore=tests/test_scrapers.py -q` after every fix
4. **Report clearly** — say what was broken, what you changed, and why

## Trigger Phrases

Any of these means: run the full self-heal protocol:

- "self-heal this error: [error]"
- "fix this: [paste error or diff]"
- "something broke: [description]"
- Auto-triggered by pre-commit hook failures

## Self-Heal Protocol

When given error output:

```
Step 1: Read the traceback → identify file + line
Step 2: Read the file at that location
Step 3: Diagnose root cause (one sentence)
Step 4: Apply the smallest correct fix
Step 5: Run tests
Step 6: Report: FIXED / NEEDS MANUAL REVIEW
```

## What You Will and Won't Change

**Will change:**
- Bug fixes (crashes, wrong output, type errors)
- Missing imports
- Encoding issues
- Exception handling gaps

**Will NOT change without being asked:**
- Code style or formatting
- Working features
- Test logic (unless the test itself is wrong)
- Architecture or abstractions

## Pipeline Self-Checks

After each pipeline stage completes, verify:

| Stage | Check |
|-------|-------|
| `career scan` | data/cache/YYYY-MM-DD.json exists and has jobs |
| `career score` | scored jobs have score != 0 in cache |
| `career apply` | job has ats_summary, cover_letter, keywords in cache |
| `career track` | SQLite has at least one row |

## Known Issues (Fixed)

These bugs have already been resolved — do not reintroduce:

1. `anthropic` SDK removed — all AI calls use `claude -p` subprocess
2. `_find_claude()` locates claude.exe via UWP package path on Windows
3. `subprocess.run` uses `encoding="utf-8"` and `PYTHONUTF8=1` env
4. Windows stdout reconfigured to UTF-8 at CLI startup (`cli.py`)
5. `tracker.upsert_application()` takes an `Application` object, not `(job, status)`
6. `ashby.py` catches `json.JSONDecodeError` in addition to `httpx.HTTPError`
7. Score batches use `list(_chunked(...))` not a raw generator
