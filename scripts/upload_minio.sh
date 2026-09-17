#!/bin/bash
# Upload release artifacts under a local directory to MinIO (S3 V2 signed PUT).

set -euo pipefail

# ========= Configuration =========
MINIO_ENDPOINT="http://minio.hcrobots.com:9000"
ACCESS_KEY="${MINIO_ACCESS_KEY:-}"
SECRET_KEY="${MINIO_SECRET_KEY:-}"
BUCKET_NAME="hc-release"
PROJECT_NAME="wormhole-auto-config"
# =================================

COMMIT_ID=$(git rev-parse --short HEAD)
TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "v0.0.0")

if [ -n "${WH_BUILD_TAG:-}" ]; then
    VERSION="${WH_BUILD_TAG}"
else
    VERSION="${TAG}-${COMMIT_ID}"
fi

if [ -z "${MINIO_ACCESS_KEY:-}" ]; then
    echo "Error: MINIO_ACCESS_KEY is not set"
    exit 1
fi

if [ -z "${MINIO_SECRET_KEY:-}" ]; then
    echo "Error: MINIO_SECRET_KEY is not set"
    exit 1
fi

if [ $# -lt 1 ]; then
    echo "Usage: $0 <local-directory>"
    echo "Example: $0 dist"
    exit 1
fi

SOURCE_DIR="$1"

if [ ! -d "${SOURCE_DIR}" ]; then
    echo "Error: directory ${SOURCE_DIR} does not exist"
    exit 1
fi

# Collect files with NUL separators to handle spaces safely.
mapfile -d '' FILES < <(find "${SOURCE_DIR}" -type f -print0)

if [ ${#FILES[@]} -eq 0 ]; then
    echo "Error: directory ${SOURCE_DIR} is empty"
    exit 1
fi

upload_file() {
    local LOCAL_FILE="$1"
    local OBJECT_NAME="$2"
    local CONTENT_TYPE
    local DATE_VALUE
    local STRING_TO_SIGN
    local SIGNATURE
    local RESPONSE
    local MAX_RETRIES=3
    local RETRY_COUNT=0
    local UPLOAD_SUCCESS=false

    CONTENT_TYPE=$(file --mime-type -b "${LOCAL_FILE}")
    DATE_VALUE=$(date -R)
    STRING_TO_SIGN="PUT\n\n${CONTENT_TYPE}\n${DATE_VALUE}\n/${BUCKET_NAME}/${OBJECT_NAME}"
    SIGNATURE=$(echo -en "${STRING_TO_SIGN}" | openssl sha1 -hmac "${SECRET_KEY}" -binary | base64)

    echo "Uploading: ${LOCAL_FILE} -> ${MINIO_ENDPOINT}/${BUCKET_NAME}/${OBJECT_NAME}"

    while [ ${RETRY_COUNT} -lt ${MAX_RETRIES} ] && [ "${UPLOAD_SUCCESS}" = false ]; do
        RESPONSE=$(curl -sS -v -X PUT \
            -H "Date: ${DATE_VALUE}" \
            -H "Content-Type: ${CONTENT_TYPE}" \
            -H "Authorization: AWS ${ACCESS_KEY}:${SIGNATURE}" \
            --upload-file "${LOCAL_FILE}" \
            "${MINIO_ENDPOINT}/${BUCKET_NAME}/${OBJECT_NAME}" 2>&1)

        if echo "${RESPONSE}" | grep -qE "HTTP/1\.[01] 200"; then
            UPLOAD_SUCCESS=true
            echo "Uploaded: ${LOCAL_FILE} -> ${MINIO_ENDPOINT}/${BUCKET_NAME}/${OBJECT_NAME}"
        else
            RETRY_COUNT=$((RETRY_COUNT + 1))
            if [ ${RETRY_COUNT} -lt ${MAX_RETRIES} ]; then
                echo "Upload failed, retry ${RETRY_COUNT}/${MAX_RETRIES}..."
                echo "Response: ${RESPONSE}"
                sleep 1
                # Refresh Date/signature for each retry.
                DATE_VALUE=$(date -R)
                STRING_TO_SIGN="PUT\n\n${CONTENT_TYPE}\n${DATE_VALUE}\n/${BUCKET_NAME}/${OBJECT_NAME}"
                SIGNATURE=$(echo -en "${STRING_TO_SIGN}" | openssl sha1 -hmac "${SECRET_KEY}" -binary | base64)
            else
                echo "Error: failed to upload ${LOCAL_FILE} after ${MAX_RETRIES} retries"
                echo "Response: ${RESPONSE}"
                exit 1
            fi
        fi
    done
}

for LOCAL_FILE in "${FILES[@]}"; do
    REL_PATH=${LOCAL_FILE#"${SOURCE_DIR}"}
    REL_PATH=${REL_PATH#/}
    OBJECT_NAME="${PROJECT_NAME}/${VERSION}/${REL_PATH}"
    upload_file "${LOCAL_FILE}" "${OBJECT_NAME}"
done

# Also publish versions.json at a fixed project root path for clients.
INDEX_FILE="${SOURCE_DIR}/versions.json"
if [ -f "${INDEX_FILE}" ]; then
    upload_file "${INDEX_FILE}" "${PROJECT_NAME}/versions.json"
fi
