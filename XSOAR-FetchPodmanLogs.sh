#!/usr/bin/env bash

LOG_DIR="/var/log/demisto/contaienr-logs" # where to save logfiles
mkdir -p "$LOG_DIR"

# get all container IDs
CONTAINERS=$(podman ps -a -q)

TIMESTAMP=$(date +"%Y%m%d-%H%M%S")

for CONTAINER_ID in $CONTAINERS; do
    # get container name for logfile name
    CONTAINER_NAME=$(podman inspect -f '{{.Name}}' "$CONTAINER_ID" | sed 's/^\/\(.*\)/\1/')

    # if container name = empty use container id
    if [[ -z "$CONTAINER_NAME" ]]; then
        FILENAME="container_${CONTAINER_ID}_${TIMESTAMP}.log"
    else
        FILENAME="${CONTAINER_NAME}_${CONTAINER_ID}_${TIMESTAMP}.log"
    fi

    # extract logs and save to logfile
    podman logs "$CONTAINER_ID" &> "${LOG_DIR}/${FILENAME}"

    echo "Logs for container $CONTAINER_ID ($CONTAINER_NAME) saved to ${LOG_DIR}/${FILENAME}"
done