#!/bin/sh
# Install short DDStation launchers. Usage: sh scripts/install_ddm2_commands.sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VENV_PY="$ROOT/../.venv/bin/python"
DEST="${HOME}/.local/bin"
if [ ! -x "$VENV_PY" ]; then
    printf 'Missing Python environment: %s\n' "$VENV_PY" >&2
    exit 1
fi
mkdir -p "$DEST"
for spec in 'ddm:ddm2_manual_control.py' 'dda:ddm2_ai_control.py'; do
    cmd=${spec%%:*}
    script=${spec#*:}
    cat > "$DEST/$cmd" <<EOF
#!/bin/sh
set -eu
cd "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:\$PYTHONPATH}"
export DDM2_LIVE_MANUAL=1
exec "$VENV_PY" "$ROOT/experiments/$script" "\$@"
EOF
    chmod 755 "$DEST/$cmd"
    printf 'Installed %s -> %s\n' "$DEST/$cmd" "$script"
done
printf '%s\n' 'Add $HOME/.local/bin to PATH if not already present.'
