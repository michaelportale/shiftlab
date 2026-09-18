#!/usr/bin/env bash
# Pre-erase checks that can be answered from the Mac.
# Run from your own Terminal with the venv active and the phone plugged in.
set -uo pipefail
cd "$(dirname "$0")/.."

blue()  { printf '\033[36m%s\033[0m\n' "$1"; }
warn()  { printf '\033[33m  ! %s\033[0m\n' "$1"; }
ok()    { printf '\033[32m  ok %s\033[0m\n' "$1"; }

blue "== Mac free space (the backup lands here) =="
df -h / | awk 'NR==2 {print "  " $4 " available on the boot volume"}'

blue "== existing backups =="
BK_ROOT="$HOME/Library/Application Support/MobileSync/Backup"
if [ -d "$BK_ROOT" ]; then
  for d in "$BK_ROOT"/*/; do
    [ -d "$d" ] || continue
    enc=$(plutil -extract IsEncrypted raw "$d/Manifest.plist" 2>/dev/null || echo "?")
    when=$(plutil -extract Date raw "$d/Info.plist" 2>/dev/null | cut -c1-16 || echo "?")
    size=$(du -sh "$d" 2>/dev/null | cut -f1)
    echo "  $(basename "$d" | cut -c1-16)...  encrypted=$enc  size=$size  date=$when"
  done
else
  warn "no backup directory found. Terminal may lack Full Disk Access:"
  warn "System Settings > Privacy & Security > Full Disk Access > add Terminal"
fi

blue "== phone: local files on the media partition =="
# AFC reaches the media partition. Files app 'On My iPhone' app containers are
# NOT visible here, so check those by hand in the Files app as well.
pymobiledevice3 afc ls / 2>/dev/null | head -20 || warn "afc unreachable"
echo
echo "  Downloads:"
pymobiledevice3 afc ls /Downloads 2>/dev/null | head -20 || echo "    (empty or unreachable)"

blue "== phone: supervision state =="
pymobiledevice3 profile cloud-configuration 2>/dev/null | grep -iE "IsSupervised|OrganizationName" || echo "  not supervised"

blue "== phone: storage =="
pymobiledevice3 lockdown info 2>/dev/null | grep -iE "TotalDiskCapacity|TotalDataAvailable" || true

blue "== reminders that no script can check =="
cat <<'NOTE'
  [ ] Settings > [name] > iCloud > Photos is ON, and Photos says "Updated just
      now" at the bottom of Library. If iCloud Photos is off, your photos live
      only in the local backup and skipping the restore loses them.
  [ ] Files app > Browse > On My iPhone is empty, or you moved it to iCloud Drive
  [ ] Screenshots taken and imported to the Mac via Image Capture
  [ ] Settings > Face ID & Passcode > Stolen Device Protection OFF
  [ ] Settings > [name] > Find My > Find My iPhone OFF
NOTE
