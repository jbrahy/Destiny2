#!/usr/bin/env bash
# Generate a double-clickable macOS app (~/Applications/Destiny 2 Advisor.app)
# that launches the Destiny 2 Advisor single-server and opens it in the browser.
# Drag the app from ~/Applications onto your Dock to pin it to the app bar.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"          # destiny-weapon-advisor/
APP_DIR="$HOME/Applications/Destiny 2 Advisor.app"
MACOS_DIR="$APP_DIR/Contents/MacOS"
LOG="$HOME/Library/Logs/destiny2-advisor.log"

echo "==> Installing $APP_DIR"
rm -rf "$APP_DIR"
mkdir -p "$MACOS_DIR"

cat > "$APP_DIR/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Destiny 2 Advisor</string>
  <key>CFBundleDisplayName</key><string>Destiny 2 Advisor</string>
  <key>CFBundleIdentifier</key><string>com.destinyopt.advisor</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>launch</string>
  <key>LSUIElement</key><true/>
</dict>
</plist>
PLIST

# The launcher script baked with this repo's absolute path.
cat > "$MACOS_DIR/launch" <<LAUNCH
#!/usr/bin/env bash
set -uo pipefail
REPO="$REPO"
LOG="$LOG"
URL="https://localhost:8443"

mkdir -p "\$(dirname "\$LOG")"

# Build the frontend once if it has never been built.
if [ ! -d "\$REPO/frontend/dist" ]; then
  ( cd "\$REPO/frontend" && npm install && npm run build ) >>"\$LOG" 2>&1
fi

# Start the backend only if it isn't already responding.
if ! curl -sk -o /dev/null "\$URL/api/health"; then
  ( cd "\$REPO/backend" && nohup python -m app.main >>"\$LOG" 2>&1 & )
fi

# Wait for health, then open the browser.
for _ in \$(seq 1 30); do
  if curl -sk -o /dev/null "\$URL/api/health"; then break; fi
  sleep 1
done
open "\$URL"
LAUNCH

chmod +x "$MACOS_DIR/launch"

echo "==> Done."
echo "    Open it from Spotlight/Launchpad ('Destiny 2 Advisor'), or open ~/Applications and"
echo "    drag it onto your Dock to pin it to the app bar."
echo "    Logs: $LOG"
echo "    To stop the server: pkill -f 'app.main'"
