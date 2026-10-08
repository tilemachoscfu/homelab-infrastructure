# Optional Netdata collection intervals

`netdata.conf.5s.example` records a validated, opt-in configuration for process
and cgroup collection. It is not enabled by the Compose template automatically.
Back up the existing configuration and merge only its two sections into
`config/netdata.conf`. Preserve every other setting and restart only Netdata.

Measure Netdata CPU and I/O against independent kernel counters. Also check
whole-host CPU, Docker/containerd CPU, container health, required charts and
alerts. A restart can activate previously inactive stock collectors: lower
Netdata CPU alone is insufficient to accept a pilot. Host charts should retain
their existing collection interval. Five-second collection loses finer process
and container detail, including some short-lived processes.

Keep the change only when the host passes validation. On degradation, restore
the exact configuration backup, restart only Netdata and recheck host load and
monitoring. Configuration rollback may not restore prior collector runtime
state. Any further collector enablement change requires a separate decision.
