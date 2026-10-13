# Local verification and explicit hosted runs

Run `pwsh -NoProfile -File .github/local-checks.ps1` before publishing changes. Use `-List` to list tasks and `-Task <name>` for an additional task. Receipts are retained in ignored `.github/local-output/`. Every step records its exit status; failures are retained.

GitHub Actions requires an explicit request through Run workflow or `gh workflow run <file> --ref <branch>`. Local agents run checks locally. Do not dispatch hosted jobs automatically after a push.

Python checks require the existing Home Assistant/Cairo environment and `uv`. The Linux matrix, HACS and Hassfest checks remain available on explicit dispatch. Daily repeated metadata validation is retired; run the manual validators for a release. HACS releases and version tags retain their existing author-controlled process.
