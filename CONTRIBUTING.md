# Contributing to PhotoPrune

Thanks for your interest. This is a small project; the contribution flow is intentionally lightweight.

## Quick start

```bash
brew install uv                          # one-time
git clone https://github.com/YashBhalodi/PhotoPrune.git && cd PhotoPrune
uv sync --extra dev --extra heic
uv run pytest                            # tests must stay green
```

Run the CLI from the checkout without installing:

```bash
uv run photoprune ~/Pictures/Trip
```

## Workflow

1. Open an issue first for anything non-trivial — saves wasted work if the change isn't a fit.
2. Branch off `main`, work in a topic branch.
3. Keep commits focused. The commit message should explain the **why**, not just the what.
4. Run `uv run pytest` locally before pushing. CI runs the same matrix on Linux + macOS × Python 3.11 + 3.12.
5. Open a PR. CI must pass; the PR template will prompt you for what changed and how to test.

## What we'll merge

- Bug fixes with a regression test.
- Small, well-scoped features that fit PhotoPrune's offline-CLI niche. New flags or modes need a clear use case.
- Performance improvements with a measurable before/after.
- Documentation improvements.

## What's a harder sell

- New hard dependencies. The dep tree is already heavy (torch, faiss, CLIP); we'd rather make the existing path faster than add more.
- New file formats unless they have native Python decoder support.
- Backend rewrites (Go / Rust / ONNX) — these are interesting but a separate conversation; please open an issue first.

## Style

- Python: standard PEP 8. Type-hint new public functions. No formatter is enforced — match the style of the file you're editing.
- HTML / CSS / JS in [`reporter.py`](photoprune/reporter.py): keep the report self-contained (no external CDN, no remote fonts). Click-to-toggle Keep / Trash is the core mental model — don't reintroduce checkboxes.
- Tests use synthetic fixtures (small in-memory images) so the suite doesn't require model downloads. Keep that property.

## Cutting a release (maintainers)

The flow is two human steps; the rest is automated.

### 1. Land a release-prep PR

In one PR on `main`:

- Bump `version` in `pyproject.toml` and `__version__` in `photoprune/__init__.py`.
- Add a new section to `CHANGELOG.md` describing what's in the release.
- Run `uv lock` so the lockfile picks up the new version.
- Open + merge the PR (CI must pass).

### 2. Tag

```bash
git checkout main && git pull
git tag vX.Y.Z
git push origin vX.Y.Z
```

The [release workflow](.github/workflows/release.yml) takes over from there:

- Verifies the tag matches the version in `pyproject.toml` (fails fast if you forgot step 1).
- Creates a GitHub release with auto-generated notes.
- Computes the source-tarball sha256.
- Opens (and admin-merges) a PR on the [homebrew tap](https://github.com/YashBhalodi/homebrew-photoprune) that bumps the formula's `url` and `sha256`.

If the workflow fails mid-release, the tag and GitHub release are already created — manually edit the formula via PR as a fallback for that one version.

