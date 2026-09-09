#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

readonly SOURCE_ROOT="${DOCKER_ROOT:-/opt/homelab}"
readonly JELLYFIN_CONFIG="/srv/docker/jellyfin/config"
readonly BACKUP_MOUNT="${MEDIA_ROOT:-/srv/media}"
readonly BACKUP_ROOT="${MEDIA_ROOT:-/srv/media}/HomelabBackups"
readonly RETENTION_DAYS=30
readonly LOCK_FILE="${DOCKER_ROOT:-/opt/homelab}/backup/.backup.lock"
readonly ALPINE_IMAGE="alpine:3.23"

exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "Another homelab backup is already running." >&2
  exit 1
fi

timestamp="$(date '+%Y-%m-%dT%H%M%S')"
snapshot_dir="${BACKUP_ROOT}/${timestamp}"
incomplete_dir="${BACKUP_ROOT}/.incomplete-${timestamp}"
paused_containers=()

cleanup() {
  local container
  for container in "${paused_containers[@]}"; do
    docker unpause "${container}" >/dev/null 2>&1 || true
  done
  if [[ -d "${incomplete_dir}" ]]; then
    find "${incomplete_dir}" -mindepth 1 -delete 2>/dev/null || true
    rmdir "${incomplete_dir}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

pause_containers() {
  local container
  for container in "$@"; do
    if [[ "$(docker inspect -f '{{.State.Running}}' "${container}")" == "true" ]]; then
      docker pause "${container}" >/dev/null
      paused_containers+=("${container}")
    fi
  done
}

unpause_containers() {
  local container
  for container in "${paused_containers[@]}"; do
    docker unpause "${container}" >/dev/null
  done
  paused_containers=()
}

compress_archive() {
  local archive="$1"
  gzip -1 "${archive}"
}

if ! mountpoint -q -- "${BACKUP_MOUNT}"; then
  echo "Backup target is not mounted: ${BACKUP_MOUNT}" >&2
  exit 1
fi

mkdir -p "${BACKUP_ROOT}" "${incomplete_dir}"
touch "${BACKUP_ROOT}/.write-test"
find "${BACKUP_ROOT}/.write-test" -delete

mapfile -t running_containers < <(docker ps --format '{{.Names}}' | sort)

# Copy bind-mounted application state while it is quiet. Compression happens
# after unpausing, so this interruption is limited to the raw disk copy.
if ((${#running_containers[@]})); then
  pause_containers "${running_containers[@]}"
fi
docker run --rm \
  -v "${SOURCE_ROOT}:/source:ro" \
  -v "${incomplete_dir}:/backup" \
  "${ALPINE_IMAGE}" \
  tar --exclude='./qbittorrent/qbittorrent/qBittorrent/ipc-socket' \
      --exclude='./backup/backup.log' \
      -cf /backup/docker-configs.tar -C /source .
unpause_containers
compress_archive "${incomplete_dir}/docker-configs.tar"

# Jellyfin artwork, logs, trickplay previews and its old built-in backups are
# rebuildable and intentionally omitted. The critical state below is small.
pause_containers jellyfin
docker run --rm \
  -v "${JELLYFIN_CONFIG}:/source:ro" \
  -v "${incomplete_dir}:/backup" \
  "${ALPINE_IMAGE}" \
  tar -cf /backup/jellyfin-critical.tar -C /source \
      config plugins root \
      data/ScheduledTasks data/SQLiteBackups data/collections \
      data/playlists data/subtitles data/device.txt data/jellyfin.db
unpause_containers
compress_archive "${incomplete_dir}/jellyfin-critical.tar"

volumes=(
  adguard-home_adguard-config
  adguard-home_adguard-work
  portainer_data
  uptime-kuma_uptime-kuma-data
)

declare -A volume_owner=(
  [adguard-home_adguard-config]="adguard-home"
  [adguard-home_adguard-work]="adguard-home"
  [portainer_data]="portainer"
  [uptime-kuma_uptime-kuma-data]="uptime-kuma"
)

# Pause only the owner of each named volume and resume it before compression.
for volume in "${volumes[@]}"; do
  docker volume inspect "${volume}" >/dev/null
  pause_containers "${volume_owner[$volume]}"
  docker run --rm \
    -v "${volume}:/source:ro" \
    -v "${incomplete_dir}:/backup" \
    "${ALPINE_IMAGE}" \
    tar -cf "/backup/volume-${volume}.tar" -C /source .
  unpause_containers
  compress_archive "${incomplete_dir}/volume-${volume}.tar"
done

if ((${#running_containers[@]})); then
  docker inspect "${running_containers[@]}" > "${incomplete_dir}/docker-inspect.json"
else
  printf '[]\n' > "${incomplete_dir}/docker-inspect.json"
fi
docker image ls --digests --no-trunc > "${incomplete_dir}/docker-images.txt"
docker volume ls > "${incomplete_dir}/docker-volumes.txt"

cat > "${incomplete_dir}/CONTENTS.txt" <<'CONTENTS'
docker-configs.tar.gz: ${DOCKER_ROOT:-/opt/homelab}, excluding runtime socket/log
jellyfin-critical.tar.gz: database, settings, plugins, collections, playlists and subtitles
volume-*.tar.gz: AdGuard Home, Portainer and Uptime Kuma named volumes

Jellyfin metadata artwork, logs, cache, trickplay previews and data/backups are
not included because they are large and can be recreated by Jellyfin.
CONTENTS

(
  cd "${incomplete_dir}"
  sha256sum ./*.tar.gz CONTENTS.txt docker-inspect.json docker-images.txt docker-volumes.txt > SHA256SUMS
)

mv "${incomplete_dir}" "${snapshot_dir}"

find "${BACKUP_ROOT}" \
  -mindepth 1 -maxdepth 1 -type d \
  -name '20??-??-??T??????' -mtime "+${RETENTION_DAYS}" \
  -exec find '{}' -mindepth 1 -delete ';' \
  -exec rmdir '{}' ';'

trap - EXIT INT TERM
echo "Backup completed: ${snapshot_dir}"
