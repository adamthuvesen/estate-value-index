# shellcheck shell=bash
# Guard local GCP scripts from running against Adam's work account.

EXPECTED_GCLOUD_ACCOUNT="${EXPECTED_GCLOUD_ACCOUNT:-a.thuvesen@gmail.com}"
BLOCKED_GCLOUD_ACCOUNT="${BLOCKED_GCLOUD_ACCOUNT:-adam.thuvesen@mentimeter.com}"

require_personal_gcloud_account() {
  if [[ "${GITHUB_ACTIONS:-}" == "true" || "${SKIP_GCLOUD_ACCOUNT_CHECK:-false}" == "true" ]]; then
    return 0
  fi

  if ! command -v gcloud >/dev/null 2>&1; then
    echo "ERROR: gcloud CLI not found" >&2
    return 1
  fi

  local active_account
  active_account="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -n 1 || true)"

  if [[ -z "$active_account" ]]; then
    echo "ERROR: no active gcloud account. Run: gcloud auth login ${EXPECTED_GCLOUD_ACCOUNT}" >&2
    return 1
  fi

  if [[ "$active_account" == "$BLOCKED_GCLOUD_ACCOUNT" ]]; then
    echo "ERROR: active gcloud account is ${BLOCKED_GCLOUD_ACCOUNT}, Adam's work GCP account." >&2
    echo "Switch to the estate-value-index account: gcloud auth login ${EXPECTED_GCLOUD_ACCOUNT}" >&2
    return 1
  fi

  if [[ "$active_account" != "$EXPECTED_GCLOUD_ACCOUNT" ]]; then
    echo "ERROR: active gcloud account is ${active_account}; expected ${EXPECTED_GCLOUD_ACCOUNT}." >&2
    echo "Set EXPECTED_GCLOUD_ACCOUNT only if this project moves to a different personal GCP account." >&2
    return 1
  fi
}
