# Contributor and agent guidance

- Read optional checkout-local instructions in `.local/AGENTS.md` when present.
- Keep the root README current and follow the repository's Standard Readme structure.
- Put shared technical documentation in `docs/`; keep personal notes, machine paths,
  private PLC projects, logs and generated validation reports in ignored `.local/` storage.
- Application code, tests, public L5X fixtures and browser assets are under `source/`.
- Run relevant checks before committing. The behavioral suite runs from `source/`:
  `py -3.13 -X utf8 -m unittest discover -s tests -v`.
- Keep changes focused. Preserve the distinction between software-model/protocol
  tests and demonstrated native Studio 5000 Go Online behavior.
