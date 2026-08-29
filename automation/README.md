# Homelab automation

This directory contains sanitized, version-controlled copies of the live
Homelab automation. The export process replaces machine-specific paths,
addresses and credentials with portable variables or runtime lookups.

## Daily health report

`daily-health-report.sh` runs at 08:30 and sends a compact Telegram dashboard
covering Docker health, disk usage and SMART data, temperatures, backups,
systemd services, watchdog state, Ethernet connectivity and pending updates.
It reads the active Telegram notification configuration from Uptime Kuma at
runtime, so no bot token or chat ID is stored in Git.

## Nightly maintenance

`nightly-maintenance.sh` runs as root at 04:00. It waits for the 03:15 backup
lock, updates system packages and reboots only after a successful upgrade.
`install-nightly-maintenance.sh` installs the root-owned executable and cron
entry. `crontab.example` documents the user-level backup, power guard and
health-report schedules.
