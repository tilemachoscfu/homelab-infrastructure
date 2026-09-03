#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

readonly BACKUP_ROOT="${MEDIA_ROOT:-/srv/media}/HomelabBackups"
readonly BACKUP_LOG="${DOCKER_ROOT:-/opt/homelab}/backup/backup.log"
readonly WATCHDOG_EVENT="/var/lib/homelab-display-watchdog/last-event"
readonly SCRUTINY_URL="http://127.0.0.1:8082/api/summary"
readonly HOST_LABEL="HP Homelab · ${HOMELAB_IP:?Set HOMELAB_IP}"

send_report=true
if [[ "${1:-}" == "--dry-run" ]]; then
  send_report=false
elif [[ $# -gt 0 ]]; then
  echo "Usage: $0 [--dry-run]" >&2
  exit 2
fi

warnings=()
details=()

add_warning() {
  warnings+=("$1")
}

html_escape() {
  sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'
}

join_by() {
  local separator="$1"
  shift
  local joined=""
  local item
  for item in "$@"; do
    if [[ -n "${joined}" ]]; then
      joined+="${separator}"
    fi
    joined+="${item}"
  done
  printf '%s' "${joined}"
}

# Docker: anything not running is urgent; explicit unhealthy/restarting states
# are called out separately. Containers without a Docker healthcheck are still
# considered running, not unhealthy.
mapfile -t stopped_containers < <(
  docker ps -a --filter status=created --filter status=exited \
    --filter status=dead --filter status=removing \
    --format '{{.Names}} ({{.Status}})' | sort
)
mapfile -t unhealthy_containers < <(
  docker ps -a --format '{{.Names}}|{{.Status}}' |
    awk -F'|' 'tolower($2) ~ /unhealthy|restarting/ {print $1 " (" $2 ")"}' | sort
)
running_count="$(docker ps -q | wc -l)"
total_count="$(docker ps -aq | wc -l)"
if ((${#stopped_containers[@]})); then
  add_warning "Docker stopped: ${stopped_containers[*]}"
fi
if ((${#unhealthy_containers[@]})); then
  add_warning "Docker unhealthy: ${unhealthy_containers[*]}"
fi
details+=("🐳 Docker  ·  ${running_count}/${total_count} ενεργά")

# Mounted filesystems: warn at 80%, urgent at 90%. Exclude pseudo filesystems.
disk_summary=()
while read -r filesystem size used available percent mountpoint; do
  usage="${percent%%%}"
  case "${mountpoint}" in
    /) disk_summary+=("SSD ${percent} (${available} ελεύθερα)") ;;
    ${MEDIA_ROOT:-/srv/media}) disk_summary+=("HDD ${percent} (${available} ελεύθερα)") ;;
  esac
  if ((usage >= 90)); then
    add_warning "ΚΡΙΣΙΜΟ: ${mountpoint} στο ${percent}"
  elif ((usage >= 80)); then
    add_warning "Χώρος: ${mountpoint} στο ${percent}"
  fi
done < <(df -hP -x tmpfs -x devtmpfs -x efivarfs | awk 'NR>1 {print $1,$2,$3,$4,$5,$6}')
details+=("💾 Δίσκοι  ·  $(join_by '  ·  ' "${disk_summary[@]}")")

# Scrutiny has privileged SMART access. Require fresh data and check drive
# temperatures. Its JSON contains no credentials, and only a compact summary
# is emitted here.
scrutiny_json="$(curl -fsS --max-time 8 "${SCRUTINY_URL}" 2>/dev/null || true)"
if [[ -z "${scrutiny_json}" ]]; then
  add_warning "SMART/Scrutiny: δεν απαντά"
  details+=("🩺 SMART  ·  μη διαθέσιμο")
else
  smart_output="$(python3 -c '
import datetime, json, sys
d = json.load(sys.stdin)["data"]["summary"]
now = datetime.datetime.now(datetime.timezone.utc)
for value in d.values():
    device = value.get("device", {}).get("device_name", "disk")
    smart = value.get("smart", {})
    temp = smart.get("temp")
    stamp = smart.get("collector_date", "")
    stale = True
    try:
        stale = (now - datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))).total_seconds() > 36 * 3600
    except (TypeError, ValueError):
        pass
    print(f"{device}|{temp if temp is not None else -1}|{1 if stale else 0}")
' <<<"${scrutiny_json}" 2>/dev/null || true)"
  if [[ -z "${smart_output}" ]]; then
    add_warning "SMART/Scrutiny: μη έγκυρα δεδομένα"
    details+=("🩺 SMART  ·  μη διαθέσιμο")
  else
    smart_summary=()
    while IFS='|' read -r device temperature stale; do
      [[ -z "${device}" ]] && continue
      if ((temperature >= 55)); then
        add_warning "Θερμοκρασία δίσκου ${device}: ${temperature}°C"
      fi
      if ((stale == 1)); then
        add_warning "SMART ${device}: στοιχεία παλαιότερα από 36 ώρες"
      fi
      smart_summary+=("${device} ${temperature}°C")
    done <<<"${smart_output}"
    details+=("🩺 SMART  ·  ${smart_summary[*]}")
  fi
fi

# CPU/GPU/NVMe thermal overview from lm-sensors. The highest current reading
# is used; known bogus critical thresholds do not affect the check.
max_temp="$(sensors 2>/dev/null | awk '
  {
    current=$0
    sub(/[[:space:]]*\(.*/, "", current)
  }
  match(current, /\+[0-9]+([.][0-9]+)?°C/) {
    value=substr(current, RSTART+1, RLENGTH-3)+0
    if (value>max) max=value
  }
  END {printf "%.1f", max}
')"
if [[ "${max_temp}" != "0.0" ]]; then
  if awk "BEGIN {exit !(${max_temp} >= 85)}"; then
    add_warning "ΚΡΙΣΙΜΗ θερμοκρασία συστήματος: ${max_temp}°C"
  elif awk "BEGIN {exit !(${max_temp} >= 75)}"; then
    add_warning "Υψηλή θερμοκρασία συστήματος: ${max_temp}°C"
  fi
  details+=("🌡 Θερμοκρασία  ·  ${max_temp}°C max")
fi

# A successful snapshot must be recent, complete and accompanied by its hash
# manifest. The 03:15 job should comfortably satisfy the 30-hour window.
latest_backup="$(find "${BACKUP_ROOT}" -mindepth 1 -maxdepth 1 -type d \
  -name '20??-??-??T??????' -printf '%T@|%p\n' 2>/dev/null | sort -nr | head -1 || true)"
if [[ -z "${latest_backup}" ]]; then
  add_warning "Backup: δεν βρέθηκε snapshot"
  details+=("🛡 Backup  ·  δεν βρέθηκε")
else
  backup_epoch="${latest_backup%%|*}"
  backup_path="${latest_backup#*|}"
  backup_age_hours="$(( ($(date +%s) - ${backup_epoch%.*}) / 3600 ))"
  backup_name="${backup_path##*/}"
  backup_time="$(date -d "@${backup_epoch%.*}" '+%d/%m %H:%M')"
  if ((backup_age_hours > 30)); then
    add_warning "Backup: τελευταίο πριν ${backup_age_hours} ώρες"
  fi
  if [[ ! -s "${backup_path}/SHA256SUMS" ]]; then
    add_warning "Backup ${backup_name}: λείπει SHA256SUMS"
    backup_integrity="χωρίς checksum"
  elif (cd "${backup_path}" && sha256sum --quiet -c SHA256SUMS); then
    backup_integrity="επαληθευμένο"
  else
    add_warning "Backup ${backup_name}: αποτυχία checksum"
    backup_integrity="ΑΠΟΤΥΧΙΑ checksum"
  fi
  if ! tail -20 "${BACKUP_LOG}" 2>/dev/null | grep -Fq "Backup completed: ${backup_path}"; then
    add_warning "Backup ${backup_name}: δεν επιβεβαιώνεται στο log"
  fi
  details+=("🛡 Backup  ·  ${backup_time} (${backup_age_hours} ώρες πριν, ${backup_integrity})")
fi

mapfile -t failed_units < <(systemctl --failed --no-legend --plain 2>/dev/null | awk '{print $1}')
if ((${#failed_units[@]})); then
  add_warning "Failed systemd: ${failed_units[*]}"
fi
details+=("⚙️ Υπηρεσίες  ·  ${#failed_units[@]} failed")

# A container can recover after the kernel kills a process at its memory
# limit, leaving Docker healthy by report time. Surface recent OOM kills so
# transient resource exhaustion is not silently missed.
mapfile -t oom_processes < <(
  journalctl --since '24 hours ago' --no-pager _TRANSPORT=kernel 2>/dev/null |
    sed -nE 's/.*Killed process [0-9]+ \(([^)]+)\).*/\1/p' |
    sort -u
)
if ((${#oom_processes[@]})); then
  add_warning "OOM τελευταίου 24ώρου: ${oom_processes[*]}"
fi
details+=("🧠 Μνήμη  ·  ${#oom_processes[@]} OOM kills / 24ωρο")

if ! systemctl is-active --quiet homelab-display-watchdog.timer; then
  add_warning "Display watchdog timer: ανενεργό"
fi
if ! systemctl is-active --quiet homelab-watchdog-status.service; then
  add_warning "Watchdog status service: ανενεργό"
fi
if [[ -r "${WATCHDOG_EVENT}" ]]; then
  last_action="$(awk -F= '$1=="action" {print $2}' "${WATCHDOG_EVENT}")"
  last_time="$(awk -F= '$1=="time" {print $2}' "${WATCHDOG_EVENT}")"
  [[ -n "${last_action}" ]] && details+=("👁 Watchdog  ·  ${last_action} ${last_time}")
else
  details+=("👁 Watchdog  ·  ενεργό, χωρίς συμβάν")
fi

ethernet_state="$(cat /sys/class/net/eno1/operstate 2>/dev/null || echo unknown)"
if [[ "${ethernet_state}" != "up" ]]; then
  add_warning "Ethernet eno1: ${ethernet_state}"
fi
if ! timeout 3 ping -c 1 -W 2 ${LAN_GATEWAY:?Set LAN_GATEWAY} >/dev/null 2>&1; then
  add_warning "Δίκτυο: το gateway ${LAN_GATEWAY:?Set LAN_GATEWAY} δεν απαντά"
fi
if [[ "${ethernet_state}" == "up" ]]; then
  ethernet_label="ενεργό"
else
  ethernet_label="${ethernet_state}"
fi
details+=("🌐 Δίκτυο  ·  Ethernet ${ethernet_label}")

update_count="$(apt list --upgradable 2>/dev/null | awk 'NR>1 {count++} END {print count+0}')"
details+=("📦 Updates  ·  ${update_count} διαθέσιμα")

if ((${#warnings[@]} == 0)); then
  headline="✅ <b>Όλα λειτουργούν κανονικά</b>"
else
  headline="⚠️ <b>${#warnings[@]} θέματα χρειάζονται προσοχή</b>"
fi

report="🏠 <b>HOMELAB · DAILY STATUS</b>
<code>${HOST_LABEL}</code>

${headline}
━━━━━━━━━━━━━━━━━━
<b>Σύστημα</b>"
for item in "${details[@]}"; do
  report+=$'\n'"$(printf '%s' "${item}" | html_escape)"
done

if ((${#warnings[@]})); then
  report+=$'\n\n'"━━━━━━━━━━━━━━━━━━"
  report+=$'\n'"🚨 <b>Χρειάζεται προσοχή</b>"
  for item in "${warnings[@]}"; do
    report+=$'\n'"🔸 $(printf '%s' "${item}" | html_escape)"
  done
fi

case "$(date +%u)" in
  1) weekday="Δευτέρα" ;;
  2) weekday="Τρίτη" ;;
  3) weekday="Τετάρτη" ;;
  4) weekday="Πέμπτη" ;;
  5) weekday="Παρασκευή" ;;
  6) weekday="Σάββατο" ;;
  7) weekday="Κυριακή" ;;
esac
report+=$'\n\n'"━━━━━━━━━━━━━━━━━━"
report+=$'\n'"🕣 ${weekday}, $(date '+%d/%m/%Y · %H:%M')"

if [[ "${send_report}" == false ]]; then
  # Strip the small fixed set of HTML tags for a readable terminal preview.
  printf '%s\n' "${report}" | sed -E 's#</?(b|code)>##g; s/&amp;/\&/g; s/&lt;/</g; s/&gt;/>/g'
  exit 0
fi

telegram_config="$(docker exec uptime-kuma sqlite3 /app/data/kuma.db \
  "select config from notification where active=1 and config like '%\"type\":\"telegram\"%' order by id limit 1;" 2>/dev/null || true)"
readarray -t telegram_credentials < <(python3 -c '
import json, sys
telegram = json.load(sys.stdin)
print(telegram.get("telegramBotToken", ""))
print(telegram.get("telegramChatID", ""))
' <<<"${telegram_config}" 2>/dev/null || true)

bot_token="${telegram_credentials[0]:-}"
chat_id="${telegram_credentials[1]:-}"
if [[ -z "${bot_token}" || -z "${chat_id}" ]]; then
  echo "An active Telegram notification is missing from Uptime Kuma." >&2
  exit 1
fi

response_file="$(mktemp)"
trap 'rm -f -- "${response_file}"' EXIT
http_code="$(curl -sS --max-time 20 -o "${response_file}" -w '%{http_code}' \
  --request POST "https://api.telegram.org/bot${bot_token}/sendMessage" \
  --data-urlencode "chat_id=${chat_id}" \
  --data-urlencode "parse_mode=HTML" \
  --data-urlencode "disable_web_page_preview=true" \
  --data-urlencode "text=${report}")"

if [[ "${http_code}" != "200" ]] || ! grep -q '"ok":true' "${response_file}"; then
  echo "Telegram delivery failed (HTTP ${http_code})." >&2
  exit 1
fi

echo "Telegram health report delivered successfully."
