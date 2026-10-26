#!/usr/bin/env bash
# Installs Zeno as a systemd *user* service (runs as you, starts with your session).
#   ./linux/install-service.sh            install, enable and start
#   ./linux/install-service.sh --linger   also start at boot without logging in
#   ./linux/install-service.sh --remove   stop, disable and delete the unit
# Logs: journalctl --user -u zeno -f
set -euo pipefail
BRAIN="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT="$UNIT_DIR/zeno.service"
LINGER=0; REMOVE=0
for arg in "$@"; do
  case "$arg" in
    --linger) LINGER=1 ;;
    --remove) REMOVE=1 ;;
    *) echo "usage: $0 [--linger | --remove]" >&2; exit 2 ;;
  esac
done

if [ "$REMOVE" = 1 ]; then
  systemctl --user disable --now zeno.service 2>/dev/null || true
  rm -f "$UNIT"
  systemctl --user daemon-reload
  echo "Removed $UNIT"
  exit 0
fi

[ -x "$BRAIN/.venv/bin/python" ] || { echo "Run $BRAIN/setup.sh first (no .venv)." >&2; exit 1; }
[ -f "$BRAIN/.env" ] || { echo "Create $BRAIN/.env from .env.example first (ZENO_MODEL_PATH)." >&2; exit 1; }

mkdir -p "$UNIT_DIR"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
# The template assumes ~/nexus-2.o/brain; point it at this checkout instead.
sed "s#%h/nexus-2.o/brain#$BRAIN#g" "$BRAIN/linux/zeno.service" > "$STAGE/zeno.service"
if systemd-analyze --user verify "$STAGE/zeno.service" 2>&1 | grep -F "$STAGE/zeno.service"; then
  echo "The unit file has problems (above); not installing." >&2
  exit 1
fi
mv "$STAGE/zeno.service" "$UNIT"
systemctl --user daemon-reload
systemctl --user enable --now zeno.service
if [ "$LINGER" = 1 ]; then loginctl enable-linger "$USER"; fi
echo "Zeno is installed. Status: systemctl --user status zeno"
