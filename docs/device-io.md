# External monitoring and device simulation

LogixLab publishes committed tag snapshots and accepts queued input transactions.
Use this interface for a separate robot, servo, sensor or other device simulator.
The PLC engine remains the source of truth for modeled memory.

Monitoring uses immutable cached snapshots. Readers never acquire the simulation
lock or walk live memory. JSON encoding and network transmission happen outside
that lock. The optional MQTT bridge runs in another process, so a disconnected
broker or slow subscriber cannot hold the simulation lock.

This is a best-effort software interface, not a real-time motion bus. Snapshot
capture still has a fixed copying cost. It publishes current state, with bounded
buffers and coalescing; it does not record every intermediate tag transition.

## Start with MQTT

Use an MQTT 3.1.1 broker, such as [Eclipse Mosquitto](https://mosquitto.org/).
The broker is separately managed; LogixLab does not install or start a broker.
Monitoring works with any number of broker subscribers without adding a polling
client to the PLC engine for each subscriber.

From the repository root, create an optional bridge environment:

```powershell
py -3.13 -m venv .local/mqtt-venv
.local/mqtt-venv/Scripts/python.exe -m pip install -r source/requirements-mqtt.txt
.local/mqtt-venv/Scripts/python.exe source/tools/mqtt_bridge.py --source http://127.0.0.1:8786 --broker 127.0.0.1 --topic-prefix logixlab/plc
```

Use the current app URL for `--source`. The example port is the appliance's
default UI tunnel; desktop sessions may use another port. The bridge accepts a
loopback source URL, including the appliance's local tunnel. It never needs a
Studio connection or the application's simulation-control token.

For external writes, enable **Device I/O → Allow external tag writes → Apply
device access** in the webpage, and start the bridge with `--allow-writes`.
Source launches can instead use `--device-writes`. These settings are independent
of EtherNet/IP write access and native Studio's read-only session.

The bridge defaults to a 100 ms polling/publishing interval. Use `--interval-ms`
to change it, within 20–60000 ms. It keeps one MQTT QoS-1 packet in flight, one
latest pending snapshot/status per topic, and at most 64 pending acknowledgement
topics. Paho's own queue and in-flight limits are also one. Broker outages do
not accumulate an unbounded history. A reconnect republishes the latest image.

For broker authentication, set `LOGIXLAB_MQTT_USERNAME` and
`LOGIXLAB_MQTT_PASSWORD` in the bridge process's environment. `--tls` enables
TLS with system certificate authorities; set the appropriate broker `--port`.
Use separate prefixes for separate PLC instances. Configure broker permissions
so device tools can publish commands and read snapshots/acknowledgements.

| Topic under the configured prefix | Direction | Meaning |
| --- | --- | --- |
| `snapshot` | PLC → devices | Retained complete snapshot, including app/project identity, sequence, scan, simulated time and tag quality |
| `status` | Bridge → devices | Retained source connection/write status and wall-clock freshness; an MQTT Will marks unexpected bridge disconnection |
| `commands` | Device → PLC | Non-retained atomic write transaction; requires both write enable switches |
| `acks/<request_id>` | PLC → device | Non-retained queued/applied/rejected result; QoS-1 duplicates are possible |

Consumers must check `status`, snapshot `captured_at`, `instance_id` and
`project_generation`. A retained snapshot can outlive its source. A stopped scan
does not imply that the bridge is disconnected. `scan` and `simulation_ms` show
simulation progress; wall-clock timestamps show observation freshness.

## Submit a device input

Read the current `instance_id` and `project_generation` from a snapshot, then
publish a transaction to `commands` with **retain=false**:

```json
{
  "request_id": "robot1-cycle-42",
  "instance_id": "<current snapshot instance_id>",
  "project_generation": 1,
  "ttl_ms": 5000,
  "writes": [
    {"tag": "Program:Cell.Robot1.Ready", "value": true},
    {"tag": "Program:Cell.Robot1.ActualPosition", "value": 125.5}
  ]
}
```

The example names must exist in the loaded project. Root tags, static array
elements and structure members are supported, including modeled strings.
Assign each device its own input tags and monitor the PLC's command/output tags.

The HTTP side accepts at most 64 pending transactions, with up to 128 scalar or
string writes per transaction and 64 KiB per request. At most four transactions
are applied before each scan, in arrival order. Access checks reuse the same
external-access rules as CIP, including aliases, constants and hidden/AOI
members. Overlapping destinations in one batch are rejected. If any write is
invalid, the entire batch is rolled back.

Writes wait while the simulation is paused. **Run** or **Step scan** consumes
them; the bridge cannot start scans, change modes or replace projects. Inputs
expire after 5000 ms by default; `ttl_ms` accepts 1–60000. Reset, execution-scope
changes, project replacement and disabling writes reject pending transactions.

An applied receipt identifies `applied_before_scan`. It means the inputs were
committed before that scan; PLC logic may overwrite them during the scan. A
failed scan rolls back logic to the already-committed input values and publishes
the fault with that state.

`request_id` is idempotent while its receipt is retained: an identical retry
returns the previous result, and different content with that ID returns conflict.
The source retains the latest 256 receipts. The bridge tracks up to 64 pending
receipts. This is a bounded acknowledgement interface, not a durable command log;
do not reuse expired IDs. Retained command replays are ignored by the bridge.

## Direct HTTP clients

All device routes use the existing loopback HTTP port and host/origin checks.
They are available without MQTT or additional runtime packages.

| Route | Authorization | Result |
| --- | --- | --- |
| `GET /api/device-io/session` | Local session | Scoped read token and, when enabled, write token |
| `GET /api/device-io/snapshot` | Read token | Cached JSON image; use `If-None-Match`/`ETag` for HTTP 304 when unchanged |
| `POST /api/device-io/write` | Write token | HTTP 202 queued receipt, or a previous terminal receipt for an identical retry |
| `GET /api/device-io/requests/<request_id>` | Read token | Current acknowledgement; HTTP 404 after receipt eviction |

Pass scoped tokens in `X-Logix-Device-Token`. They do not authorize the control
API. Write tokens rotate on enable/disable and project-generation changes.
Refresh the device session after an authorization error. Tokens are not MQTT
payloads. Source app state contains only non-secret Device I/O status.

Snapshots include primitive leaf values, data types and good/unknown/bad quality.
Wide integer values retain their decimal-text representation. Unknown values are
null. Capture is bounded to 50,000 leaves and an 8 MB encoded payload;
`truncated`/`error` explicitly report omitted data. Snapshot reads never trigger
capture. Producers capture committed command boundaries and sample intermediate
boundaries within a multi-scan batch.

## Other adapters

The snapshot and transaction interface is transport-independent. An OPC UA
adapter can expose typed subscriptions and writes using it; a DDS adapter can
serve device-simulation ecosystems that already use DDS. A SQL consumer can
store a historian without putting database writes in the scan path. These
adapters are planned, not implemented. SQL is not used as live PLC memory.

MQTT distributes messages; it does not make Studio 5000's native tag-address
cache valid. Native Studio/SDK monitoring remains separate work.

## Validation

The standard suite tests reader independence from the runtime lock, consistent
snapshots, queue bounds, expiry, atomic rollback, access checks, idempotency,
source changes and scoped HTTP tokens. The optional real-broker check starts an
isolated app and bridge against an explicitly supplied loopback test broker:

```powershell
.local/mqtt-venv/Scripts/python.exe source/tests/interop_device_mqtt.py --broker-port 1883 --out .local/mqtt-validation.json
```

It uses a unique test prefix and public NetworkLab fixture, then cleans its
retained topics. It verifies queued/applied acknowledgements, logic seeing device
inputs, output monitoring, invalid/duplicate/stale writes and late subscribers.
It does not connect to physical devices or establish native controller parity.

Protocol references: [MQTT 3.1.1](https://docs.oasis-open.org/mqtt/mqtt/v3.1.1/os/mqtt-v3.1.1-os.html),
[Paho client API](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html),
[OPC UA subscription model](https://reference.opcfoundation.org/specs/OPC-10000-4/5.14.1).
