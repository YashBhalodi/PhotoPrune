<!--
Thanks for the PR. Keep this short — a few sentences each is plenty.
-->

## What changed

<!-- A one-paragraph summary of the change. Focus on *why*, not *what*. -->

## How to test

<!--
Reproduction steps for a reviewer. If applicable:
- The command(s) to run
- The album / fixture used
- The expected before/after
-->

## Checklist

- [ ] `uv run pytest` passes locally
- [ ] CI (`pytest` matrix on Linux + macOS) is green
- [ ] If user-facing: README / `--help` updated
- [ ] If a new dep was added: justification noted in the description
- [ ] No secrets, no real photo paths, no large binary assets in the diff
