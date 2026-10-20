# Isolated anonymous protocol probe

The research probe creates a private emulator instance on an automatic loopback
port, imports a matching ACD/L5X pair, and tests the anonymous compatibility
protocol through a real TCP connection. It never retargets the running app,
connects to a physical controller or calls the Studio SDK or Windows services.

The client generates its own ephemeral RSA key with the optional `cryptography`
package. It decrypts the emulator's challenge and verifies signed replies using
that newly negotiated session key. The server's nonce is not patched. This
observed compatibility dialect provides no peer-identity authentication or
vendor trust; it is not an implementation of CIP Security.

From the repository root:

```powershell
py -3.13 -m pip install cryptography
py -3.13 -X utf8 source/tools/probe_research_session.py --acd .local/Controller.ACD --l5x .local/Controller.L5X --output .local/research-session.json
```

Select a complete L5X converted from the same unchanged ACD. The tool binds
metadata to both input hashes, checks them again afterward and preserves both
files. Reports require a new path and should stay in ignored `.local/` storage.
Reports contain source hashes and protocol counts. Add `--inventory` to read
the owned emulator through a fresh independent session and include its
[Task, Program and tag inventory](upload-inventory-client.md). That optional
report also contains names, values and raw read traffic; keep it private.

The basic case exercises anonymous context binding, a supported BOOL value,
available Controller source settings, the edit reservation, Program Disabled
readback, source-bound Task settings, scheduling/time fields and reservation
release. The client checks the same application,
endpoint, project generation, source hash and read-only policy before and after
every transport request. It cannot accept an arbitrary network address.

For an owned captured device payload, also supply `--device-payload` and
`--expanded-bytes`. This separately acquires the programming reservation,
inhibits scans, sends signed fragments, starts the real temporary download
image, and verifies every retained preparation effect. Historical coordination
transitions are counted separately from current resource readbacks. The still
unsupported result request must be rejected; transport, inhibit and lease must
then clear. The temporary app closes even if a check fails.

The `.79` owned-payload case passes 18 protocol checks and verifies all 904
preparation outcomes with unchanged source/model state. It includes 902 current
resource readbacks and two historical coordination transitions. This establishes
the custom emulator's tested behavior. Native Studio Go Online, tag-address
discovery, complete upload/download and online-edit acceptance remain separate
tests. An unavailable SDK service does not prevent this isolated probe.

The `.81` owned-payload case passes 24 signed protocol checks, including the
ordered Task Program list, explicit watchdog time and unavailable Task execution
slot. With `--inventory`, a separate session completes 56 inventory reads and
checks the discovered Task-to-Program links. The source and model are preserved;
the report still marks complete native upload and SDK acceptance as unassessed.

The `.83` owned-payload case passes 31 signed checks, including the explicit
Controller overflow-reporting flag and Program-scoped Routine catalogs. The
independent inventory session completes 60 reads. All 904 temporary preparation
results remain verifiable, and source/model state is preserved. These checks
use the custom protocol client; native SDK results are recorded separately.

The `.84` owned-payload case passes 33 signed checks. It adds a source-bound
Program reservation and release, checks that scans are inhibited only while
reserved, and preserves all 904 temporary preparation readbacks. The separate
inventory still completes 60 reads. It does not supply hypothetical Controller
replies or enable accepted edits.
