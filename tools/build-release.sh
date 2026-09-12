#!/usr/bin/env bash
#
# build-release.sh: Package all widgets into installable ZIPs and .icuewidget files.
#
# Scans widgets/ for EA* directories containing index.html,
# packages each into a ZIP (preserving folder structure) and
# a flat .icuewidget archive (for iCUE's import button), and
# builds an all-widgets bundle.
# Output goes to dist/.
#
# Usage: ./tools/build-release.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST="$REPO_ROOT/dist"

rm -rf "$DIST"
mkdir -p "$DIST"

BUNDLE_DIR=$(mktemp -d)
COUNT=0

# Widgets to exclude from release builds
EXCLUDE_WIDGETS="EATest"

for WIDGET_DIR in "$REPO_ROOT"/widgets/EA*/; do
    [ -d "$WIDGET_DIR" ] || continue

    # Skip directories without an index.html
    [ -f "$WIDGET_DIR/index.html" ] || continue

    WIDGET=$(basename "$WIDGET_DIR")

    # Skip excluded widgets
    case ",$EXCLUDE_WIDGETS," in *",$WIDGET,"*) echo "Skipping $WIDGET"; continue ;; esac

    ZIP_NAME="${WIDGET}.zip"
    ICUE_NAME="${WIDGET}.icuewidget"
    echo "Packaging $ZIP_NAME + $ICUE_NAME..."

    # Create a temp staging dir
    STAGE=$(mktemp -d)
    mkdir -p "$STAGE/$WIDGET"

    # Copy installable files: index.html, manifest.json, translation.json, resources/, modules/
    cp "$WIDGET_DIR/index.html" "$STAGE/$WIDGET/"
    [ -f "$WIDGET_DIR/manifest.json" ] && cp "$WIDGET_DIR/manifest.json" "$STAGE/$WIDGET/"
    [ -f "$WIDGET_DIR/translation.json" ] && cp "$WIDGET_DIR/translation.json" "$STAGE/$WIDGET/"
    [ -d "$WIDGET_DIR/resources" ] && cp -r "$WIDGET_DIR/resources" "$STAGE/$WIDGET/"
    [ -d "$WIDGET_DIR/modules" ] && cp -r "$WIDGET_DIR/modules" "$STAGE/$WIDGET/"

    # Build per-widget ZIP (folder-wrapped, for manual install)
    (cd "$STAGE" && zip -r "$DIST/$ZIP_NAME" "$WIDGET" -x ".*") > /dev/null

    # Build .icuewidget (flat, for iCUE import)
    (cd "$STAGE/$WIDGET" && zip -r "$DIST/$ICUE_NAME" . -x ".*") > /dev/null

    # Also copy to bundle staging
    cp -r "$STAGE/$WIDGET" "$BUNDLE_DIR/"

    rm -rf "$STAGE"
    COUNT=$((COUNT + 1))
done

# Build all-widgets bundle
if [ "$COUNT" -gt 0 ]; then
    TAG="${GITHUB_REF_NAME:-$(date +%Y.%m)}"
    BUNDLE_NAME="all-widgets-${TAG}.zip"
    echo "Packaging $BUNDLE_NAME..."
    (cd "$BUNDLE_DIR" && zip -r "$DIST/$BUNDLE_NAME" . -x ".*") > /dev/null
fi

rm -rf "$BUNDLE_DIR"

# Package Claude Usage companion server as a ZIP
CU_SERVER_DIR="$REPO_ROOT/widgets/EAClaudeUsage/server"
if [ -f "$CU_SERVER_DIR/ClaudeUsageServer.pyw" ]; then
    CU_STAGE=$(mktemp -d)
    cp "$CU_SERVER_DIR"/ClaudeUsageServer.pyw "$CU_STAGE/"
    cp "$CU_SERVER_DIR"/StartServer.bat "$CU_STAGE/" 2>/dev/null || true
    (cd "$CU_STAGE" && zip -r "$DIST/ClaudeUsageServer.zip" . -x ".*") > /dev/null
    rm -rf "$CU_STAGE"
    echo "Packaged ClaudeUsageServer.zip"
fi

echo ""
echo "Packaged $COUNT widgets."
echo "Release artifacts in $DIST/:"
ls -1 "$DIST/"
