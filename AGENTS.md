# Studio5000Emulator repository instructions

- The canonical working repository is `C:\~LocalWork\Repos\Programming\~Github\Studio5000Emulator`.
- Continue emulator and Studio 5000 connectivity development on `feature/studio5000-connectivity` unless the user directs a branch change.
- Commit small, coherent increments frequently after appropriate verification.
- Do not push to `origin`. The user will push commits themselves.
- Preserve the original v0.5 history on `baseline/logixlab-v0.5` and the existing GitHub history and LICENSE.
- Application code and UI are under `source/`; run the behavioral suite from there with `py -3.13 -X utf8 -m unittest discover -s tests -v`.
- Distinguish protocol/client tests from demonstrated native Studio Go Online behavior when reporting results.
