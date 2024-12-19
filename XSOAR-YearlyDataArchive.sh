#!/usr/bin/env bash
#
# Archive all data for a specified year into an archive folder. 
# This was created and tested for a single-tenant deployment of XSOAR 6.13 on RHEL 9.4, unsure about compatability. 
# This script follows the instruction provided for maintaining and optomizing XSOAR on-prem performance:
# https://docs-cortex.paloaltonetworks.com/r/Cortex-XSOAR/6.13/Cortex-XSOAR-Administrator-Guide/Free-up-Disk-Space-with-Data-Archiving 
#
# This script takes two arguments:
#  1) The output path for the final tar archive (e.g. /tmp or /var/tmp)
#  2) The year to archive (e.g. 2019)
#
# Example usage:
#  ./archive_demisto_data.sh /var/tmp 2019
#
# - The script will:
#    - Stop the demisto service
#    - Create archive directories
#    - Move monthly data for the specified year into the archive directory
#    - If a direct mv of monthly data fails, use the backup approach (per-month)
#    - Create a compressed tar archive of the archived data
#    - Restart the demisto service

set -euo pipefail

if [[ $# -ne 2 ]]; then
    echo "Usage: $0 <output_path> <year>"
    exit 1
fi

OUTPUT_PATH="$1"
YEAR="$2"

ARCHIVE_BASE="${OUTPUT_PATH}/demisto-archive"
ARCHIVE_DIR="${ARCHIVE_BASE}/archived-${YEAR}"
DEMISTO_DATA_DIR="/var/lib/demisto/data"

# 1. Stop the Cortex XSOAR service
echo "Stopping Demisto service..."
sudo service demisto stop

# 2. Create the directories
echo "Creating archive directories..."
sudo mkdir -p "${ARCHIVE_DIR}"

# 3. Navigate to the archive base directory
cd "${ARCHIVE_BASE}"

# 4. Move data for each month of the given year
for MONTH in {01..12}; do
    DATE_TO_ARCHIVE="${MONTH}${YEAR}"
    echo "Attempting to archive data for ${DATE_TO_ARCHIVE}..."

    # Attempt the broad mv command first
    set +e
    sudo mv ${DEMISTO_DATA_DIR}/**/*_${DATE_TO_ARCHIVE}* "${ARCHIVE_DIR}/" 2>/dev/null
    MV_EXIT_CODE=$?
    set -e

    if [[ $MV_EXIT_CODE -ne 0 ]]; then
        echo "Broad mv failed for ${DATE_TO_ARCHIVE}, attempting backup solution..."

        # Create backup directories if not already present
        sudo mkdir -p "${ARCHIVE_DIR}/demistoidx/"
        sudo mkdir -p "${ARCHIVE_DIR}/partitionsData/"

        # Attempt the index files one by one
        # Adjust these paths as needed if they differ in your environment
        for IDX_NAME in entries evidences incidents invTaskIdx investigations newInsights todosTask; do
            SRC="${DEMISTO_DATA_DIR}/demistoidx/${IDX_NAME}_${DATE_TO_ARCHIVE}"
            if [[ -e "$SRC" ]]; then
                sudo mv "$SRC" "${ARCHIVE_DIR}/demistoidx/" || echo "Warning: Could not move $SRC"
            fi
        done

        # Attempt the partition file
        PARTITION_FILE="${DEMISTO_DATA_DIR}/partitionsData/demisto_${DATE_TO_ARCHIVE}.db"
        if [[ -e "$PARTITION_FILE" ]]; then
            sudo mv "$PARTITION_FILE" "${ARCHIVE_DIR}/partitionsData/" || echo "Warning: Could not move $PARTITION_FILE"
        fi
    else
        echo "Archived data for ${DATE_TO_ARCHIVE} successfully."
    fi
done

# 5. Create the compressed archive of the archived files/folders
TAR_FILE="${OUTPUT_PATH}/demisto-${YEAR}-archive.tar.gz"
echo "Creating tar archive ${TAR_FILE}..."
sudo tar -cvzf "${TAR_FILE}" "${ARCHIVE_DIR}"

# 6. Start the Cortex XSOAR service
echo "Starting Demisto service..."
sudo service demisto start

echo "Archive process completed successfully."