#!/usr/bin/env bash
# headersHelper for the BigQuery MCP server in .mcp.json (D-088): prints auth headers as JSON.
# Uses the project-local gcloud with the hireme-engage-dev configuration, never the global default.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOKEN="$(CLOUDSDK_ACTIVE_CONFIG_NAME=hireme-engage-dev "$ROOT/.venv/bin/gcloud" auth print-access-token)"
printf '{"Authorization": "Bearer %s", "x-goog-user-project": "hireme-engage-dev"}\n' "$TOKEN"
