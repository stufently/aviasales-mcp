#!/usr/bin/env bash
# Add SHA256 lines for every *.mcpb in DIR to a sha256sum file.
#
# Usage: mcpb-checksums.sh DIR SUMS
#
# SUMS may already hold lines for other release files. Those lines stay, byte
# for byte and in their original order, including a final line with no
# trailing newline. Lines whose filename ends in .mcpb — plain or GNU-escaped
# (`\<64 hex>  <name>`) — are replaced, so a second run does not duplicate
# them. A directory with no bundles is an error and leaves SUMS untouched.
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: mcpb-checksums.sh DIR SUMS" >&2
  exit 2
fi

dir=$1
sums=$2

if [ ! -d "$dir" ]; then
  echo "mcpb-checksums: not a directory: ${dir}" >&2
  exit 1
fi

bundles=()
for path in "$dir"/*.mcpb; do
  # No match leaves the glob literal; a directory named *.mcpb is not a bundle.
  if [ -f "$path" ]; then
    base=$(basename -- "$path")
    bundles+=("$base")
  fi
done

if [ "${#bundles[@]}" -eq 0 ]; then
  echo "mcpb-checksums: no .mcpb files in ${dir}" >&2
  exit 1
fi

# NUL-delimited so a bundle name that contains a newline stays one name.
mapfile -d '' names < <(printf '%s\0' "${bundles[@]}" | LC_ALL=C sort -z)

sums_dir=$(dirname -- "$sums")
tmp=$(mktemp "${sums_dir}/.mcpb-checksums.XXXXXX")
cleanup() {
  if [ -n "${tmp:-}" ] && [ -f "$tmp" ]; then
    rm -f -- "$tmp"
  fi
}
trap cleanup EXIT

# A bundle line is sha256sum text mode, optionally in the GNU escaped form
# that starts with a backslash. Anything else is kept whole.
is_mcpb_sum() {
  local body=$1
  local filename=""
  if [ "${body#\\}" != "$body" ]; then
    body=${body#\\}
  fi
  if [[ "$body" =~ ^[[:xdigit:]]{64}\ \ (.*)$ ]]; then
    filename=${BASH_REMATCH[1]}
    filename=${filename%$'\r'}
  fi
  [ -n "$filename" ] && [[ "$filename" == *.mcpb ]]
}

if [ -f "$sums" ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    if is_mcpb_sum "$line"; then
      continue
    fi
    printf '%s\n' "$line" >> "$tmp"
  done < "$sums"
fi

(
  cd -- "$dir" || exit 1
  sha256sum -- "${names[@]}"
) >> "$tmp"

if [ -f "$sums" ]; then
  chmod --reference="$sums" -- "$tmp"
else
  chmod 644 -- "$tmp"
fi

# Check the bundle lines we just wrote before publishing them over SUMS.
# A preserved note that merely ends in .mcpb is not a checksum line; feeding
# it to sha256sum -c --strict would reject an update the file is allowed to hold.
# A mismatch must not replace a checksum file the release already published.
if ! check_out=$(
  grep -E '^\\?[0-9a-f]{64}  .*\.mcpb$' -- "$tmp" | (
    cd -- "$dir" || exit 1
    sha256sum -c --strict -
  )
); then
  if [ -n "$check_out" ]; then
    printf '%s\n' "$check_out" >&2
  fi
  echo "mcpb-checksums: sha256sum -c failed for .mcpb lines" >&2
  exit 1
fi

mv -f -- "$tmp" "$sums"
tmp=""
