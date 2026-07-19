#!/usr/bin/env bash
# Container entrypoint: activate ESP-IDF, then run whatever was asked for.
# MUST keep LF line endings -- CRLF here fails with a confusing "not found".
set -e

. /opt/esp/idf/export.sh >/dev/null 2>&1

exec "$@"
