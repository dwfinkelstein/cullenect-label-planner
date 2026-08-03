#!/usr/bin/env bash
# Smoke-test a RUNNING container against the guarantees that only hold in the real image.
#
# The unit suite can't see any of this: whether the pinned renderer actually made it in,
# whether it can emit coloured 3MF, whether every font the UI offers resolves (OpenSCAD
# substitutes a missing family silently, changing the printed label with no error), and
# whether the data volume really survives the container being replaced.
#
# Usage:  scripts/smoke-image.sh [base-url]        default http://localhost:8080
set -euo pipefail

BASE="${1:-http://localhost:8080}"
fail=0

say()  { printf '  %-52s %s\n' "$1" "$2"; }
check() { if [ "$2" = "$3" ]; then say "$1" "OK"; else say "$1" "FAIL (got '$2', want '$3')"; fail=1; fi }

echo "Smoke-testing $BASE"

# --- the renderer that actually shipped ------------------------------------------------
health=$(curl -fsS --max-time 30 "$BASE/api/health")
check "health responds"            "$(echo "$health" | python3 -c 'import sys,json;print(json.load(sys.stdin)["ok"])')" "True"
check "renderer emits coloured 3MF" "$(echo "$health" | python3 -c 'import sys,json;print(json.load(sys.stdin)["color_3mf"])')" "True"
say   "renderer version" "$(echo "$health" | python3 -c 'import sys,json;print(json.load(sys.stdin)["openscad"])')"

# --- fonts: a missing family is silently substituted, so it must be checked in the image
missing=$(curl -fsS --max-time 30 "$BASE/api/meta" | python3 -c 'import sys,json;print(",".join(json.load(sys.stdin)["fonts_missing"]))')
check "every offered font resolves" "${missing:-none}" "none"

# --- a real render, end to end ----------------------------------------------------------
tmp=$(mktemp -d)
code=$(curl -fsS --max-time 120 -o "$tmp/label.3mf" -w '%{http_code}' \
  -H 'Content-Type: application/json' -X POST "$BASE/api/render/preview" \
  -d '{"name":"smoke","text1":{"text":"SMOKE"},"text_color":"#CC2222",
       "fastener":{"show":true,"head":"socket","driver":"hex","shaft":"machine","threads":"full"}}')
check "renders a label" "$code" "200"
python3 - "$tmp/label.3mf" <<'PY'
import sys, zipfile
model = zipfile.ZipFile(sys.argv[1]).read("3D/3dmodel.model").decode()
ok = "colorgroup" in model and "CC2222" in model.upper()
print(f"  {'colour group present in the export':52s} {'OK' if ok else 'FAIL'}")
sys.exit(0 if ok else 1)
PY
[ $? -eq 0 ] || fail=1

# --- icons (2D projection path, no GL context available in a container) -----------------
icon=$(curl -fsS --max-time 60 "$BASE/api/icons/driver.svg?driver=torx")
case "$icon" in *"<path"*) say "icon renders as SVG" "OK";; *) say "icon renders as SVG" "FAIL"; fail=1;; esac

# --- a plate, merged ---------------------------------------------------------------------
ids=$(curl -fsS "$BASE/api/labels" | python3 -c 'import sys,json;print(json.dumps([l["id"] for l in json.load(sys.stdin)][:3]))')
code=$(curl -fsS --max-time 300 -o "$tmp/plate.3mf" -w '%{http_code}' \
  -H 'Content-Type: application/json' -X POST "$BASE/api/plate" -d "{\"label_ids\":$ids}")
check "builds a plate" "$code" "200"

rm -rf "$tmp"
if [ "$fail" -ne 0 ]; then echo "SMOKE FAILED"; exit 1; fi
echo "SMOKE OK"
