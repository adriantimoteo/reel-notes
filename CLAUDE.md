# CLAUDE.md — reel-capture-bot

Coding instructions for this project. Read this fully before writing any code.

---

## Development workflow

- Work **one ticket at a time** — tickets are in `./Tickets/` in the vault
- Each ticket is implemented in its **own git branch** (e.g. `ticket/P01T01-project-scaffold`)
- Spawn a **dev agent** for each ticket implementation
- After dev agent completes: update the ticket file with what was done and set `status: dev-complete`
- Spawn a separate **code review agent** to do a thorough review against the ticket's acceptance criteria
- After code review agent completes: update the ticket file with the review findings
- Code is **only merged to `main` after all acceptance criteria pass** and the review is clean
- After merge: set `status: done` in the ticket file

---

## Package management

UV is the package manager. Never use `pip` directly.

| Task | Command |
|---|---|
| Add a runtime dependency | `uv add <package>` |
| Add a dev/test dependency | `uv add --group dev <package>` |
| Install from lockfile | `uv sync` |
| Run tests | `uv run pytest` |
| Run any script | `uv run <script>` |

- `pyproject.toml` + `uv.lock` are the source of truth for dependencies — not `requirements.txt`
- Do not create or modify `requirements.txt`
- Do not modify `[tool.*]` sections in `pyproject.toml` without asking
- `uv.lock` is committed — do not delete or manually edit it
- Do not add new dependencies without asking first

---

## Architecture

The module layout and layered architecture are defined in `03-implementation.md`. Follow them exactly.

Ownership rules — each layer has one job, do not scatter logic:

| Layer | Owns |
|---|---|
| `bot/` | Telegram I/O only — no pipeline logic |
| `pipeline/` | Processing stages — no direct Telegram or SQL calls |
| `storage/` | All SQL — no other module writes SQL directly |
| `output/` | Rendering and file writing only |
| `config.py` | All env var loading — no other module reads env vars directly |

Two constraints that cut across layers:

- **Platform-specific code lives only in `pipeline/downloader.py`.** Once `ReelMetadata` is produced, the rest of the pipeline is platform-agnostic.
- **`ExtractionResult` is the refactor boundary.** Nothing downstream of `pipeline/extractor.py` cares how it was produced. Do not let extractor implementation details leak into the renderer, storage, or bot layers.

---

## Ticket discipline

Work one ticket at a time. The tickets are in `./Tickets/`. Each ticket specifies exactly what to implement.

- Read the full ticket before writing any code
- Check `depends_on` in the ticket frontmatter — if a dependency is not done, flag it rather than implement it yourself
- Implement only what the current ticket requires — do not implement adjacent tickets even if they are unblocked or seem obvious
- Ask before making any decision not covered by the ticket or the spec docs

**Two things agents commonly get ahead of — do not do either:**

1. **Do not implement Path A extractor** (Whisper + OCR + text-only LLM). Path B — a single Gemini call — is the current choice per `02-architecture.md`. Path A is a documented future refactor path, not current scope.
2. **Do not add retry logic** on Gemini, yt-dlp, or Telegram failures. The spec explicitly requires failing loudly with a diagnostic message. Retries are not in scope.

---

## Code style

- **Type hints required** on all function signatures — parameters and return types
- **Dataclasses** for all models (`ReelMetadata`, `ExtractionResult`, `Item`) — not Pydantic, not plain dicts
- **`async`/`await` throughout** — all pipeline stages, bot handlers, and status updates are async. Do not introduce synchronous blocking calls in async contexts
- **Exceptions** for error handling — not Result types, not `(value, error)` tuples. The exception hierarchy lives in `pipeline/exceptions.py`
- **No comments** unless the *why* is non-obvious (a hidden constraint, a workaround, a subtle invariant). Do not comment what the code does

---

## Testing

- Tests live in `tests/unit/` and `tests/integration/`
- JSON fixtures and expected output files live in `tests/fixtures/`
- Run with: `uv run pytest`
- Write tests as part of implementing the ticket — not in a separate pass
- Each ticket's acceptance criteria map directly to test cases — use them as the test specification
- **All external services are mocked in tests** — no real Telegram, Gemini, or yt-dlp calls. The mocking strategy for each ticket is prescribed in the ticket file; follow it rather than inventing a different approach
- Integration tests per phase live in `tests/integration/test_phaseN.py`

---

## Do not

- Add non-goal features from `01-spec.md` — no multi-user support, no web UI, no geocoding, no aggregation
- Add logging frameworks — `print()` to stdout is sufficient for a personal tool at this scale
- Auto-format files you have not touched in the current ticket
- Modify `pyproject.toml` `[tool.*]` sections without asking
- Add error handling or fallbacks for scenarios that cannot happen — trust internal guarantees
- Add features, refactor, or introduce abstractions beyond what the ticket requires
