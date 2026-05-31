# shellcheck shell=bash
# Shared strict-mode preamble for deployment / GCP scripts.
#
# This file is meant to be `source`d, NOT executed:
#   source "$(dirname "${BASH_SOURCE[0]}")/lib/preamble.sh"
#
# Scripts in scripts/ also inline `set -euo pipefail` + IFS so they don't
# depend on this file being on disk, but new scripts can source this for
# the canonical baseline.

set -euo pipefail
IFS=$'\n\t'
