#!/usr/bin/env bash
# SessionStart hook for CTK plugin
# Ensures CTK binary is installed and up-to-date with plugin version

set -euo pipefail

# Determine plugin root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Get plugin version from plugin.json
PLUGIN_VERSION=$(cat "$PLUGIN_ROOT/.claude-plugin/plugin.json" 2>/dev/null | grep -o '"version"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | cut -d'"' -f4 || echo "unknown")

# Get installed ctk version
INSTALLED_VERSION=$(ctk --version 2>/dev/null | grep -oP 'version \K[\d.]+' || echo "none")

# Check if we need to install/update
NEEDS_UPDATE="false"

if ! command -v ctk &>/dev/null; then
    NEEDS_UPDATE="true"
    REASON="not installed"
elif [ "$PLUGIN_VERSION" != "$INSTALLED_VERSION" ] && [ "$PLUGIN_VERSION" != "unknown" ]; then
    NEEDS_UPDATE="true"
    REASON="version mismatch (plugin: $PLUGIN_VERSION, installed: $INSTALLED_VERSION)"
fi

# Install/update if needed
if [ "$NEEDS_UPDATE" = "true" ]; then
    echo "[CTK] Updating ($REASON)..."

    # Use pip to install from plugin directory
    # Try without --break-system-packages first, then fallback to it for PEP 668 managed environments
    pip3 install -e "$PLUGIN_ROOT" --quiet 2>/dev/null || \
        pip3 install -e "$PLUGIN_ROOT" --break-system-packages --quiet 2>/dev/null || \
        pip3 install -e "$PLUGIN_ROOT" --break-system-packages

    # Ensure data directories exist
    mkdir -p "$HOME/.local/share/ctk"
    mkdir -p "$HOME/.config/ctk"

    # Verify and show version
    NEW_VERSION=$(ctk --version 2>/dev/null | head -1 || echo "installed")
    echo "[CTK] ✓ Updated to $NEW_VERSION"
fi

# Ensure hook script is current in manual location (for users with manual setup)
if [ -d "$HOME/.claude/hooks" ]; then
    cp "$PLUGIN_ROOT/hooks/ctk-rewrite.sh" "$HOME/.claude/hooks/ctk-rewrite.sh" 2>/dev/null || true
    chmod +x "$HOME/.claude/hooks/ctk-rewrite.sh" 2>/dev/null || true
fi

# Silent exit - no output on normal startup
exit 0
