#!/usr/bin/env bash

set -euo pipefail

workspace_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_dir="$workspace_dir/outputs/vireal-wan-video-h5/prototype"
source_file="$source_dir/prototype_v1.0.html"
output_dir="$workspace_dir/dist/vireal-pages"
api_base_url="${VIREAL_API_BASE_URL:-}"

if [[ -z "$api_base_url" ]]; then
  echo "VIREAL_API_BASE_URL is required, for example https://api.example.com" >&2
  exit 1
fi

api_base_url="${api_base_url%/}"
if [[ ! "$api_base_url" =~ ^https://[A-Za-z0-9.-]+(:[0-9]+)?$ ]]; then
  echo "VIREAL_API_BASE_URL must be an HTTPS origin without a path or query" >&2
  exit 1
fi

escaped_api_base_url="${api_base_url//&/\\&}"
escaped_api_base_url="${escaped_api_base_url//|/\\|}"

rm -rf "$output_dir"
mkdir -p "$output_dir"

sed \
  -e "s|__VIREAL_API_BASE_URL__|$escaped_api_base_url|g" \
  -e "s|__VIREAL_BACKEND_MODE__|1|g" \
  "$source_file" > "$output_dir/index.html"

cp "$source_dir/_headers" "$output_dir/_headers"
printf 'User-agent: *\nDisallow: /\n' > "$output_dir/robots.txt"

if grep -Eq '__VIREAL_API_BASE_URL__|__VIREAL_BACKEND_MODE__' "$output_dir/index.html"; then
  echo "Cloudflare Pages placeholders were not fully replaced" >&2
  exit 1
fi

echo "Built Cloudflare Pages site in $output_dir"
