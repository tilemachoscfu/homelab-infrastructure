#!/usr/bin/env bash
set -Eeuo pipefail

export DEBIAN_FRONTEND=noninteractive
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

readonly BACKUP_LOCK="/tmp/homelab-backup.lock"
readonly LOG_TAG="homelab-nightly-maintenance"

if [[ "${EUID}" -ne 0 ]]; then
  echo "This maintenance task must run as root." >&2
  exit 1
fi

log_message() {
  logger -t "${LOG_TAG}" -- "$1"
  echo "$(date --iso-8601=seconds) $1"
}

# Never update or reboot while the 03:15 backup is still writing. Wait up to
# one hour; on timeout, fail safely and leave the host running.
exec 9>"${BACKUP_LOCK}"
if ! flock -w 3600 9; then
  log_message "Backup lock remained busy; updates and reboot skipped."
  exit 1
fi

log_message "Starting nightly package update."
apt-get update
apt-get \
  -o Dpkg::Options::="--force-confold" \
  -o APT::Get::Assume-Yes="true" \
  upgrade

log_message "Package update completed successfully; rebooting now."
sync
systemctl reboot
