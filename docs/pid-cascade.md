# Ladder PID cascade

The bounded v35 ControlLogix 5580 ladder solver can cascade two logical PID
records. It samples the master's output percentage into the slave's engineering
setpoint. This is a one-way software model; native startup, feedback, solver
coefficients, status and fault equivalence remain unqualified.

```text
PID(Master,MasterPV,0,MasterCV,0,0,0);
PID(Slave,SlavePV,0,SlaveCV,Master,0,0);
```

Set Master.CL and Master.CT true. Set Slave.CL true and Slave.CT false. The
master uses its own SP and requires literal zero in the master operand. The
slave requires a distinct logical PID record. With CL false, CT is retained
and ignored; a supplied master is structurally checked but its values are not
sampled. The master operand cannot reference the executing record, and CV
cannot overwrite the master record.

On an automatic slave call, require known master CTL with CL/CT set and a known
finite OUT in 0..100. Compute float32:

```text
SP = MINS + Master.OUT * (MAXS - MINS) / 100
```

Use that SP for error, derivative-on-error, deadband signatures and alarms,
then publish it to SP and DATA[4] on success. A missing saved slave SP may be
established by the cascade sample. Scaling and numeric CV conversion follow
the ordinary [PID contract](ladder-pid.md).

The master is read-only to the slave. Slave saturation does not back-propagate
an inhibit, tracking value or anti-windup request. Multi-level slave/master
chains, reverse feedback and automatic role changes remain outside this model.
Invalid role combinations fault; the model does not silently pick a role.

## Order, manual operation and transactions

Ladder order determines the sampled value. A master executed earlier in the
same advance supplies its updated OUT. A later, false or skipped master supplies
its last represented OUT; EN is not a freshness guarantee. Arrange call order
and release rates explicitly. UPD remains the PID integration interval.

False slave calls clear EN and skip numeric sampling. [Manual/inhold modes](pid-restart.md)
bypass the master sample: manual PVT may establish SP from scaled PV; ordinary
manual and inhold consume the retained SP. Role/reference validation still
applies. Returning to auto consumes the current master OUT. Later faults roll
back both loops, sampled SP, hidden history and scheduler state together.

## Try the PID lab

Load **PID lab**. Enable Execute, IntExecute, Cascade, CascadeMaster and
IntCascade; leave IntCascadeMaster false. On successive steps the REAL master
CV is 45 then 60; the INT slave SP is 45 then 60 and RawCV is 6553 then 11468.
The slave raw PV 8000 represents engineering PV 25. Disabling Execute holds the
last master OUT for later slave calls. FaultDivisor zero exercises rollback.

Reference basis: installed Studio 5000 v35 PID help 14709, 14712 (Cascading
Loops) and 14737 (Configuration), plus the cascade section of the
[Logix general instruction reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm003_-en-p.pdf).
These references establish the percentage-to-engineering relationship; the
bounded lifecycle, role checks and fault transaction remain simulator choices.
