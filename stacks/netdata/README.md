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

## Optional Docker API module isolation

`go.d.conf.docker-disabled.example` records a separately validated opt-in
setting for the `go.d` Docker API module. One-second API polling can create
substantial Docker/containerd CPU load even when Netdata itself uses little CPU.
Disabling this module leaves the cgroups collector available for CPU, memory,
I/O and network metrics, but intentionally removes Docker API inventory, image,
state and health charts.

Back up the existing configuration and record whether user `go.d.conf` exists.
Preserve every current stock/user default and other module setting; change only
`modules.docker` to `no`. Restart only Netdata, then compare equal CPU sampling
windows, daemon process lifetimes, required chart/alert coverage and application
health. Preserve existing collection intervals and resources.

Containers sharing a network namespace may have their common NIC counters
attributed to a different namespace member after Netdata restarts. Verify the
namespace and equivalent fresh metric before treating a chart-name change as
missing data. Do not weaken per-container CPU/memory/I/O checks.

Rollback restores the exact previous override. If it originally did not exist,
move only the newly created file into its private backup directory and restart
Netdata. Preserve data and recheck host load; re-enabling the API module may
recreate the CPU regression.
