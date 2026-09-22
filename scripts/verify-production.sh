#!/usr/bin/env bash

set -euo pipefail

h5_url="${H5_URL:-}"
api_url="${API_URL:-}"
private_object_url="${R2_PRIVATE_OBJECT_URL:-}"

if [[ ! "$h5_url" =~ ^https://[^/]+/?$ ]]; then
  echo "H5_URL must be an HTTPS origin, for example https://app.example.com" >&2
  exit 1
fi
if [[ ! "$api_url" =~ ^https://[^/]+/?$ ]]; then
  echo "API_URL must be an HTTPS origin, for example https://api.example.com" >&2
  exit 1
fi

h5_url="${h5_url%/}"
api_url="${api_url%/}"

echo "Checking H5 deployment"
h5_html="$(curl --fail --silent --show-error "$h5_url/")"
if [[ "$h5_html" != *"name=\"vireal-api-base-url\" content=\"$api_url\""* ]]; then
  echo "H5 does not contain the expected production API origin" >&2
  exit 1
fi
if [[ "$h5_html" != *"name=\"vireal-backend-mode\" content=\"1\""* ]]; then
  echo "H5 production backend mode is not enabled" >&2
  exit 1
fi
if [[ "$h5_html" != *"name=\"clerk-publishable-key\" content=\"pk_live_"* ]]; then
  echo "H5 does not contain a Clerk production publishable key" >&2
  exit 1
fi
for forbidden_marker in "123456" "device-login" "virealAppAccessToken"; do
  if [[ "$h5_html" == *"$forbidden_marker"* ]]; then
    echo "H5 still contains legacy authentication marker: $forbidden_marker" >&2
    exit 1
  fi
done

echo "Checking API health"
health_body="$(curl --fail --silent --show-error "$api_url/api/v1/utils/health-check/")"
if [[ "$health_body" != "true" ]]; then
  echo "Unexpected API health response: $health_body" >&2
  exit 1
fi

echo "Checking production authentication and documentation policy"
device_login_status="$(curl --silent --show-error --output /dev/null \
  --request POST \
  --header 'Content-Type: application/json' \
  --data '{"device_uuid":"production-policy-check","platform":"ios"}' \
  --write-out '%{http_code}' \
  "$api_url/api/v1/app/auth/device-login")"
if [[ "$device_login_status" != "410" ]]; then
  echo "Production device login must return HTTP 410; received $device_login_status" >&2
  exit 1
fi

docs_status="$(curl --silent --show-error --output /dev/null \
  --write-out '%{http_code}' "$api_url/docs")"
if [[ "$docs_status" != "404" ]]; then
  echo "Public API docs must return HTTP 404; received $docs_status" >&2
  exit 1
fi

echo "Checking Replicate webhook reachability and redirect policy"
webhook_result="$(curl --silent --show-error --output /dev/null \
  --request POST \
  --header 'Content-Type: application/json' \
  --data '{}' \
  --write-out '%{http_code} %{redirect_url}' \
  "$api_url/api/v1/webhooks/replicate")"
webhook_status="${webhook_result%% *}"
webhook_redirect="${webhook_result#* }"
if [[ -n "$webhook_redirect" ]]; then
  echo "Webhook unexpectedly redirects to $webhook_redirect" >&2
  exit 1
fi
case "$webhook_status" in
  400|401|403|422) ;;
  *)
    echo "Unexpected unsigned webhook response: HTTP $webhook_status" >&2
    exit 1
    ;;
esac

if [[ -n "$private_object_url" ]]; then
  echo "Checking that the unsigned R2 object is private"
  private_status="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' "$private_object_url")"
  case "$private_status" in
    401|403|404) ;;
    *)
      echo "Unsigned R2 object must not be readable; received HTTP $private_status" >&2
      exit 1
      ;;
  esac
fi

echo "Production edge checks passed"
