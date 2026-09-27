#!/bin/bash
# Build PokeHunt.app — double-clickable macOS launcher for the controller GUI.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="PokeHunt"
APP_DIR="${ROOT}/${APP_NAME}.app"
CONTENTS="${APP_DIR}/Contents"
MACOS="${CONTENTS}/MacOS"
RESOURCES="${CONTENTS}/Resources"
VENV_PY="${ROOT}/.venv/bin/python"

if [[ ! -x "${VENV_PY}" ]]; then
  echo "Missing venv. Creating one…"
  python3 -m venv "${ROOT}/.venv"
  "${ROOT}/.venv/bin/pip" install -q --upgrade pip
  "${ROOT}/.venv/bin/pip" install -q customtkinter keyring pillow
fi

# Ensure icon exists
if [[ ! -f "${ROOT}/assets/PokeHunt.icns" ]]; then
  "${VENV_PY}" "${ROOT}/scripts/make_icon.py"
fi

rm -rf "${APP_DIR}"
mkdir -p "${MACOS}" "${RESOURCES}"

# Copy icon
cp "${ROOT}/assets/PokeHunt.icns" "${RESOURCES}/AppIcon.icns"

# Info.plist
cat > "${CONTENTS}/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>
  <string>${APP_NAME}</string>
  <key>CFBundleDisplayName</key>
  <string>${APP_NAME} Controller</string>
  <key>CFBundleIdentifier</key>
  <string>com.pokehunt.controller</string>
  <key>CFBundleVersion</key>
  <string>1.0.0</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0.0</string>
  <key>CFBundleExecutable</key>
  <string>${APP_NAME}</string>
  <key>CFBundleIconFile</key>
  <string>AppIcon</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>LSMinimumSystemVersion</key>
  <string>11.0</string>
  <key>NSHighResolutionCapable</key>
  <true/>
  <key>LSUIElement</key>
  <false/>
</dict>
</plist>
PLIST

# Launcher — always boots from the project so credentials + bot.py stay in sync
cat > "${MACOS}/${APP_NAME}" <<LAUNCHER
#!/bin/bash
export POKEHUNT_ROOT="${ROOT}"
export PYTHONUNBUFFERED=1
cd "${ROOT}" || exit 1
exec "${VENV_PY}" -m gui
LAUNCHER
chmod +x "${MACOS}/${APP_NAME}"

# PkgInfo
echo -n "APPL????" > "${CONTENTS}/PkgInfo"

echo "Built ${APP_DIR}"
echo "Launch with: open \"${APP_DIR}\""
echo "Optional: cp -R \"${APP_DIR}\" /Applications/"
