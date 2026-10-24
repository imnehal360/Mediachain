#!/usr/bin/env bash
set -euo pipefail

base_url="${MEDIACHAIN_SMOKE_URL:-http://127.0.0.1:18000}"
api_key="${MEDIACHAIN_SMOKE_API_KEY:-ci-test-key}"
compose_file="${MEDIACHAIN_SMOKE_COMPOSE_FILE:-docker-compose.test.yml}"
auth_header="Authorization: Bearer ${api_key}"

wait_until_ready() {
  for _ in $(seq 1 90); do
    if curl --fail --silent "${base_url}/ready" >/dev/null; then
      return 0
    fi
    sleep 2
  done
  echo "MediaChain did not become ready" >&2
  return 1
}

json_field() {
  python3 -c "import json,sys; print(json.load(sys.stdin)$1)"
}

wait_until_ready

upload_response=$(curl --fail --silent --show-error \
  -H "${auth_header}" \
  -F "file=@notes.txt;type=text/plain" \
  "${base_url}/api/v1/media")
asset_id=$(printf '%s' "${upload_response}" | json_field "['id']")

job_response=$(curl --fail --silent --show-error \
  -X POST -H "${auth_header}" \
  "${base_url}/api/v1/media/${asset_id}/process")
job_id=$(printf '%s' "${job_response}" | json_field "['id']")

job_status="queued"
for _ in $(seq 1 90); do
  job_response=$(curl --fail --silent --show-error \
    -H "${auth_header}" "${base_url}/api/v1/jobs/${job_id}")
  job_status=$(printf '%s' "${job_response}" | json_field "['status']")
  if [ "${job_status}" = "completed" ]; then
    break
  fi
  if [ "${job_status}" = "failed" ] || [ "${job_status}" = "cancelled" ]; then
    echo "Processing job ended with ${job_status}: ${job_response}" >&2
    exit 1
  fi
  sleep 2
done
test "${job_status}" = "completed"

query_response=$(curl --fail --silent --show-error \
  -H "${auth_header}" -H "Content-Type: application/json" \
  -d "{\"question\":\"What does this say about artificial intelligence?\",\"media_ids\":[\"${asset_id}\"]}" \
  "${base_url}/api/v1/query")
printf '%s' "${query_response}" | python3 -c \
  "import json,sys; body=json.load(sys.stdin); assert body['sources'][0]['media_id'] == '${asset_id}'"

# Restart both application processes and prove that PostgreSQL, Qdrant, Redis, and S3 state survives.
docker compose -f "${compose_file}" restart api worker
wait_until_ready
listing=$(curl --fail --silent --show-error -H "${auth_header}" "${base_url}/api/v1/media")
printf '%s' "${listing}" | python3 -c \
  "import json,sys; assert any(item['id'] == '${asset_id}' for item in json.load(sys.stdin))"

query_response=$(curl --fail --silent --show-error \
  -H "${auth_header}" -H "Content-Type: application/json" \
  -d "{\"question\":\"artificial intelligence\",\"media_ids\":[\"${asset_id}\"]}" \
  "${base_url}/api/v1/query")
printf '%s' "${query_response}" | python3 -c \
  "import json,sys; body=json.load(sys.stdin); assert body['sources'][0]['media_id'] == '${asset_id}'"

curl --fail --silent --show-error -X DELETE -H "${auth_header}" \
  "${base_url}/api/v1/media/${asset_id}" >/dev/null
status=$(curl --silent --output /dev/null --write-out '%{http_code}' \
  -H "${auth_header}" "${base_url}/api/v1/media/${asset_id}")
test "${status}" = "404"
echo "Compose smoke test passed: upload, queued processing, query, restart, persistence, and deletion"
