# Retained Routine profile reads

Supported plain Standard RLL replacement retains the last accepted selector `9`
component from the source-equivalent download. This is the observed 13-byte
profile accepted by the bounded download parser. It is separate from ELF code,
compressed RLL source and the edit transaction's post-source attachment.
The replacement does not implement a setter for this component.

Installation checks the actual retained download effect ledger and stores the
exact per-routine bytes and hash beside the original source snapshot. Missing
components stay missing. Readback requires the original catalog fingerprint,
same installed snapshot, complete current source, unchanged tag bindings and
the supported unprotected routine type. Changed bytes, wrong scope, replaced
catalogs and incomplete source cannot fall back to a generated constant.

Selector `4` also keeps the observed empty unprotected RLL stream after the
same checks. Selector `3` continues to return source that independently resolves
to current interpreter logic, including the exact accepted edit source.
Each fragment rechecks its model, installation and source. Another edit revokes
an existing continuation. None of these reads supplies an execution address,
executes native code or establishes a general compiled-component format.

The offline transfer analyzer now describes the inner target and selector of a
rejected `0x3A` read. These remain wrapper rejections and do not count as successful
stream frames. Initial read failures also appear in the endpoint's scoped native
rejection summary. This makes an unavailable component visible even when the SDK
reports only a higher-level Program upload failure. Journal framing analysis
does not authenticate old MACs or establish native upload acceptance.
