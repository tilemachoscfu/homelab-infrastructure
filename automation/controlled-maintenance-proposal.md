# Controlled maintenance proposal

Status: proposal only. No replacement timer, service, notification, update
policy, or reboot workflow has been deployed.

## Verified containment

The infrastructure host's `homelab-daily-update-reboot.timer` is disabled
and inactive, with no next execution. Its associated service was inactive
when the timer was disabled. The service and executable remain unchanged
for redesign. Definitions and script were backed up privately before the
change; hashes were unchanged afterward. Other timer enablement was unchanged.
All 18 running containers retained their IDs, start times and restart counts;
none were unhealthy.

This containment applies only to that timer. It does not change or establish
the behavior of other APT, firmware, update, cron or reboot automations.
Existing update mechanisms must be inventoried before deploying a replacement
so that there are no overlapping policies or package-management jobs.

## Daily read-only checks

A small daily check should inspect existing APT metadata, candidate versions,
held packages, package database states, `dpkg --audit`, repository-index age,
available disk/inode space, existing reboot markers and installed/running
kernels. It must not install, configure, remove, download packages or refresh
APT indexes. `apt-get update` writes metadata and belongs to a separately
approved refresh policy, not the strictly read-only checker. If indexes are
stale or checks race with a package transaction, report UNKNOWN / stale and
retry the observation later rather than claiming there are no updates.

Use the existing authenticated Telegram notification integration, keeping
credentials in its existing private store. Notify when updates appear or
change, and send a periodic reminder for outstanding security updates.
Include host label, timestamp, metadata age, security/general update counts,
held packages, integrity failures and reboot-required evidence. Deduplicate
unchanged notifications. Do not send notifications until deployment is
explicitly approved.

## Controlled security update policy

Initially use approval per maintenance window. Identify security updates by
verified repository origin and release metadata, not a package-name heuristic.
Review the exact package/version plan, dependencies, held packages and expected
service restarts. Never use an automatic general `dist-upgrade` or autoremove.
Reject removals, downgrades, held-package changes, or critical Docker/network/
SSH/kernel changes unless explicitly reviewed and approved. Do not remove the
running kernel. A future narrow automatic security allowlist would require a
separate explicit policy decision; it is not part of this deployment proposal.

Before applying an approved transaction: verify a current restorable backup,
package consistency, dependencies, space/inodes, required mounts and service
baseline. Refresh metadata only under the approved policy, simulate the exact
transaction, and obtain approval for that concrete plan. Revalidate immediately
before execution because APT simulations do not hold package locks. Respect
APT/dpkg locks and any other maintenance workflow; if busy, defer. Never delete
lock files or terminate another package process.

## Finish package operations safely

Do not wrap APT/dpkg in a terminating timeout. A future package-application
service should use an unlimited start timeout (`TimeoutStartSec=infinity`)
and no runtime deadline that kills active package children. An independent
read-only observer can alert on unusually long runtime or lack of progress;
it must never kill the package transaction to clear the alert. Bound only
pre-transaction checks or lock-acquisition waits. Do not restart a failed
transaction blindly or enable an automatic restart loop.

After natural completion, validate `dpkg --audit`, pending configurations /
triggers, dependency consistency and the running kernel's installed state.
APT consistency checks that write package caches belong in the approved
maintenance phase, not the read-only daily checker. If validation fails,
preserve evidence, alert and stop the workflow; any repair gets a separate
reviewed plan. Recheck failed units, application endpoints, Docker counts /
health, SSH, Tailscale, storage and monitoring against the captured baseline.

## Reboot decision and approval

Detect `/run/reboot-required`, its package list where present, installed versus
running kernels and other supported package restart indicators. Report REQUIRED,
RECOMMENDED or NOT REQUIRED with evidence; do not reboot merely because an
upgrade finished. A kernel version mismatch is evidence to assess, not the
only decision rule. Never queue a delayed reboot without approval.

Present the reboot reason, service recovery policies, backup state and proposed
window, then wait for explicit approval. Only an approved reboot action should
run, followed by kernel/package, connectivity, container, application, storage
and monitoring validation. Failed upgrades or failed validation never reboot.

## Logs and failure alerts

Keep timestamped private per-run logs with the package plan, approvals, command
exit codes, durations, validation results and reboot decision. Redact secrets
and keep logs/backups outside Git. Send failure alerts through the existing
notification integration for stale checks, unhealthy package state, lock
contention, unusual runtime, transaction failure and failed postchecks. A
failure handler should report and preserve evidence, never upgrade, repair,
reset failures or reboot automatically. Failed notification delivery must be
recorded and visible locally.

## Reference documentation

- [APT behavior and simulation limitations](https://manpages.debian.org/trixie/apt/apt-get.8.en.html)
- [systemd service timeout behavior](https://manpages.debian.org/trixie/systemd/systemd.service.5.en.html)
