#!/usr/bin/env bash
set -Eeuo pipefail

readonly SOURCE_SCRIPT="${DOCKER_ROOT:-/opt/homelab}/monitoring/nightly-maintenance.sh"
readonly INSTALLED_SCRIPT="/usr/local/sbin/homelab-nightly-maintenance"
readonly CRON_FILE="/etc/cron.d/homelab-nightly-maintenance"
readonly BACKUP_DIR="${DOCKER_ROOT:-/opt/homelab}/backup/$(date '+%Y-%m-%dT%H%M%S')-nightly-maintenance"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this installer with sudo." >&2
  exit 1
fi

mkdir -p "${BACKUP_DIR}"
chmod 700 "${BACKUP_DIR}"
if [[ -e "${INSTALLED_SCRIPT}" ]]; then
  cp -a -- "${INSTALLED_SCRIPT}" "${BACKUP_DIR}/homelab-nightly-maintenance.before"
fi
if [[ -e "${CRON_FILE}" ]]; then
  cp -a -- "${CRON_FILE}" "${BACKUP_DIR}/cron.before"
fi

install -o root -g root -m 0755 "${SOURCE_SCRIPT}" "${INSTALLED_SCRIPT}"

temporary_cron="$(mktemp)"
trap 'rm -f -- "${temporary_cron}"' EXIT
cat >"${temporary_cron}" <<'CRON'
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Install package updates and reboot every day at 04:00 local time.
0 4 * * * root /usr/local/sbin/homelab-nightly-maintenance >> /var/log/homelab-nightly-maintenance.log 2>&1
CRON
install -o root -g root -m 0644 "${temporary_cron}" "${CRON_FILE}"

bash -n "${INSTALLED_SCRIPT}"
run-parts --test /etc/cron.d >/dev/null
systemctl restart cron

echo "Nightly maintenance installed for 04:00."
