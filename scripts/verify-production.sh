#!/usr/bin/env bash

set -euo pipefail

h5_url="${H5_URL:-}"
api_url="${API_URL:-}"
private_object_url="${R2_PRIVATE_OBJECT_URL:-}"
release_mode="${RELEASE_CHECK_MODE:-closed}"
expected_commit="${EXPECTED_RELEASE_COMMIT:-}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python_bin="${PYTHON_BIN:-python3}"

if [[ "$release_mode" != "closed" && "$release_mode" != "public" ]]; then
  echo "RELEASE_CHECK_MODE must be closed or public" >&2
  exit 1
fi
if [[ ! "$expected_commit" =~ ^[0-9a-f]{40}$ ]]; then
  echo "EXPECTED_RELEASE_COMMIT must identify the reviewed 40-character Git commit" >&2
  exit 1
fi

if [[ ! "$h5_url" =~ ^https://[A-Za-z0-9.-]+(:[0-9]+)?/?$ ]]; then
  echo "H5_URL must be an HTTPS origin, for example https://app.example.com" >&2
  exit 1
fi
if [[ ! "$api_url" =~ ^https://[A-Za-z0-9.-]+(:[0-9]+)?/?$ ]]; then
  echo "API_URL must be an HTTPS origin, for example https://api.example.com" >&2
  exit 1
fi

h5_url="${h5_url%/}"
api_url="${api_url%/}"

fetch() {
  curl --connect-timeout 5 --max-time 20 --proto '=https' "$@"
}

echo "Checking H5 deployment"
h5_html="$(fetch --fail --silent --show-error "$h5_url/")"
if [[ "$h5_html" != *"name=\"vireal-api-base-url\" content=\"$api_url\""* ]]; then
  echo "H5 does not contain the expected production API origin" >&2
  exit 1
fi
if [[ "$h5_html" != *"name=\"vireal-backend-mode\" content=\"1\""* ]]; then
  echo "H5 production backend mode is not enabled" >&2
  exit 1
fi
if [[ "$h5_html" != *"name=\"vireal-release\" content=\"v1.2-production\""* ]]; then
  echo "H5 is not the v1.2 production build" >&2
  exit 1
fi
if [[ "$h5_html" != *"name=\"vireal-release-commit\" content=\"$expected_commit\""* ]]; then
  echo "H5 is missing the reviewed release commit or serves a different version" >&2
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

h5_app_js="$(fetch --fail --silent --show-error "$h5_url/assets/vireal-app.js")"
for forbidden_marker in "data-pack" "确认充值" "adult_authorization"; do
  if [[ "$h5_app_js" == *"$forbidden_marker"* ]]; then
    echo "H5 contains a forbidden v1.2 marker: $forbidden_marker" >&2
    exit 1
  fi
done
if [[ "$h5_app_js" != *"/api/v1/app/effect-catalog"* ]]; then
  echo "H5 does not load the dynamic effect catalog" >&2
  exit 1
fi
for required_marker in "/api/v1/app/paypal/orders" "data-refresh-task" "data-download-task" "playback_url_expires_at"; do
  if [[ "$h5_app_js" != *"$required_marker"* ]]; then
    echo "H5 is missing the selected release feature: $required_marker" >&2
    exit 1
  fi
done

echo "Checking API health"
health_body="$(fetch --fail --silent --show-error "$api_url/api/v1/utils/health-check/")"
if [[ "$health_body" != "true" ]]; then
  echo "Unexpected API health response" >&2
  exit 1
fi

echo "Checking the public v1.2 effect catalog"
fetch --fail --silent --show-error "$api_url/api/v1/app/effect-catalog" \
  | "$python_bin" "$script_dir/verify-release-contract.py" catalog "$release_mode"

echo "Checking the observable PayPal/recharge contract"
fetch --fail --silent --show-error "$api_url/api/v1/app/paypal/config" \
  | "$python_bin" "$script_dir/verify-release-contract.py" commerce "$release_mode"

echo "Checking production authentication and documentation policy"
# Do not POST a valid device-login payload: a misconfigured older backend could
# create an account during a supposed read-only release check.
for protected_path in "wallet" "video-tasks/00000000-0000-0000-0000-000000000000/download"; do
  protected_status="$(fetch --silent --show-error --output /dev/null \
    --write-out '%{http_code}' "$api_url/api/v1/app/$protected_path")"
  case "$protected_status" in
    401|403) ;;
    *)
      echo "Wallet/download must reject anonymous access; received HTTP $protected_status" >&2
      exit 1
      ;;
  esac
done

docs_status="$(fetch --silent --show-error --output /dev/null \
  --write-out '%{http_code}' "$api_url/docs")"
# Cloudflare blocks non-/api/ paths before FastAPI's disabled docs return 404.
case "$docs_status" in
  403|404) ;;
  *)
    echo "Public API docs must be blocked (HTTP 403 or 404); received $docs_status" >&2
    exit 1
    ;;
esac

echo "Checking Replicate webhook reachability and redirect policy"
webhook_result="$(fetch --silent --show-error --output /dev/null \
  --request POST \
  --header 'Content-Type: application/json' \
  --data '{}' \
  --write-out '%{http_code} %{redirect_url}' \
  "$api_url/api/v1/webhooks/replicate")"
webhook_status="${webhook_result%% *}"
webhook_redirect="${webhook_result#* }"
if [[ -n "$webhook_redirect" ]]; then
  echo "Webhook unexpectedly redirects" >&2
  exit 1
fi
case "$webhook_status" in
  400|401|403|422) ;;
  *)
    echo "Unexpected unsigned webhook response: HTTP $webhook_status" >&2
    exit 1
    ;;
esac

echo "Checking that the PayPal receiver exists and rejects malformed unsigned input"
paypal_result="$(fetch --silent --show-error --output /dev/null \
  --request POST --header 'Content-Type: application/json' --data '{}' \
  --write-out '%{http_code} %{redirect_url}' \
  "$api_url/api/v1/webhooks/payments/paypal")"
if [[ "$paypal_result" != "422 " ]]; then
  echo "PayPal receiver must reject malformed input without redirect or acknowledgement" >&2
  exit 1
fi

if [[ -n "$private_object_url" ]]; then
  echo "Checking that the unsigned R2 object is private"
  private_status="$(fetch --silent --show-error --output /dev/null --write-out '%{http_code}' "$private_object_url")"
  # R2's S3 endpoint may reject a missing signature with HTTP 400 InvalidArgument.
  case "$private_status" in
    400|401|403|404) ;;
    *)
      echo "Unsigned R2 object must not be readable; received HTTP $private_status" >&2
      exit 1
      ;;
  esac
fi

echo "Selected release observable checks passed ($release_mode); no payment or generation was exercised"
echo "Region-scoped checks do not prove global switches, merchant approval, media rights or real acceptance"
