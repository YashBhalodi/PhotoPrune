# Security Policy

## Supported versions

PhotoPrune is in early-alpha development. Security fixes are applied to the latest tagged release on `main`. Older versions are not separately maintained.

| Version | Supported       |
|---------|-----------------|
| 0.1.x   | ✅ (latest)     |
| < 0.1   | ❌              |

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Instead, use GitHub's private vulnerability reporting:

1. Go to <https://github.com/YashBhalodi/PhotoPrune/security/advisories/new>
2. Fill in the disclosure form

Or email the maintainer (commit history shows the author email).

We aim to acknowledge reports within 5 business days, and to ship a fix or workaround within 30 days for confirmed high-severity issues.

## Scope

PhotoPrune runs entirely locally — no network calls, no cloud upload — so the threat surface is intentionally small. The most relevant categories are:

- **Path traversal** in the cleanup phase (the tool moves files based on a user-saved `selections.json`).
- **HTML injection** in the review report (filenames are rendered into HTML).
- **Supply-chain concerns** in our dependency tree (PyTorch, faiss, CLIP, etc.).
- **Arbitrary-code execution** triggered by reading a malicious image (the underlying decoders are PIL, OpenCV, and pillow-heif).

Out of scope: bugs in the upstream libraries we depend on (please report those upstream).

## Data handling

PhotoPrune does not collect, transmit, or persist any user data outside the user's own filesystem. The on-disk artifacts (`embeddings_cache.npy`, `audit_log.csv`, etc.) live in the user's specified output directory. Model weights are pulled from official Hugging Face / torchvision caches on first run; everything after that is offline.
