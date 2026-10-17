# Contributing

Bug reports, questions and pull requests are welcome through the repository's
[issues](https://github.com/votecoffee/Studio5000Emulator/issues) and
[pull requests](https://github.com/votecoffee/Studio5000Emulator/pulls).

## Repository layout

- `source/logixlab/`: project import, execution model and EtherNet/IP endpoint.
- `source/web/`: local browser interface.
- `source/tests/`: behavioral tests and optional integration probes.
- `source/samples/`: public, source-authored L5X fixtures.
- `source/research/`: optional native interoperability diagnostics.
- `docs/`: shared technical documentation.
- `.local/`: ignored, machine-local notes, settings, private inputs and receipts.
- `dist/`: ignored executable build output.

Application development is maintained on `main`. Keep changes
focused and update the root README when user-visible behavior or setup changes.

## Checks

From `source/`, run:

```powershell
py -3.13 -X utf8 -m unittest discover -s tests -v
```

Use relevant independent-client probes for protocol changes. See
[development guidance](docs/development.md). Prefer tests that exercise observable
behavior, bounds, unsupported requests and state preservation. Changes to docs
should preserve working relative links and accurate command examples.

When adding an instruction or protocol service, document its supported operand
forms and limits. Distinguish software-model tests, independent client results
and native controller/Studio evidence. A passing client probe does not establish
native runtime equivalence or Studio project correlation.

## Public repository hygiene

- Use synthetic examples and public L5X fixtures in commits.
- Keep private ACD/L5X projects, machine paths, local SDK results, protocol
  captures, screenshots and personal workflows under `.local/` or outside the
  checkout. ACD files are ignored; native checks accept an explicit private path.
- Keep credentials and environment configuration out of Git. Configure the
  converter through Import settings, `LOGIXLAB_CONVERTER`, or `PATH`.
- Keep generated binaries, build directories and local receipts untracked.
- Inspect `git status` and the staged diff before committing; ignore rules do
  not remove files that are already tracked.
- Share only the smallest reproducible example needed for an issue or pull
  request. Review exports and logs for project-specific information first.

Changes are made available under the repository's [MIT license](LICENSE).
