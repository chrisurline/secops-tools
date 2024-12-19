#! /usr/bin/bash

LOG_DIR="/var/log/demisto/container-logs" # where to save logfiles
mkdir -p "$LOG_DIR"

# get all container IDs
CONTAINERS=$(sudo -u demisto podman ps -a -q)

TIMESTAMP=$(date +"%Y%m%d-%H%M%S")

for CONTAINER_ID in $CONTAINERS; do
    # use container name for logfile name if possible
    CONTAINER_NAME=$(sudo -u demisto podman inspect -f '{{.Name}}' "$CONTAINER_ID" | sed 's/^\/\(.*\)/\1/')

    # if container name = empty, use container id
    if [[ -z "$CONTAINER_NAME" ]]; then
        FILENAME="container_${CONTAINER_ID}_${TIMESTAMP}.log"
    else
        FILENAME="${CONTAINER_NAME}_${CONTAINER_ID}_${TIMESTAMP}.log"
    fi

    # extract logs and save to logfile
    sudo -u demisto podman logs "$CONTAINER_ID" &> "${LOG_DIR}/${FILENAME}"

    echo "Logs for container $CONTAINER_ID ($CONTAINER_NAME) saved to ${LOG_DIR}/${FILENAME}"
done