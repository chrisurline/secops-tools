import requests
import csv
import os
import argparse

# this script is step 2 of the process (we will put together an all-in-one tool here shortly)
# in this step we will take our CSV from step 1 and provide it as an arg
# the script will then fetch the current versions from the xsoar instance and add it to our csv
# the format will be "Pack Name", "Version Before", "Version After", "Last Install Date" 

# xsoar api config
XSOAR_BASE_URL = os.environ.get("DEMISTO_BASE_URL") # Example: "https://your-xsoar-instance.com"
XSOAR_API_KEY = os.environ.get("DEMISTO_API_KEY") # Your XSOAR API Key
XSOAR_HEADERS = {
    "Authorization": XSOAR_API_KEY,
    "Content-Type": "application/json",
    "Accept": "application/json"
}

def get_installed_content_packs_metadata():
    
    # retrieve metadata for all installed content packs

    url = f"{XSOAR_BASE_URL}/contentpacks/metadata/installed"
    try:
        response = requests.get(url, headers=XSOAR_HEADERS, verify=False)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching content pack metadata: {e}")
        return None

def update_pack_versions_in_csv(csv_path, content_packs):

    # update the csv with the new version and installation date for updated packs

    updated_rows = []
    try:
        with open(csv_path, "r", newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                pack_name = row["Content Pack Name"]
                version_before = row["Current Version"]
                version_after = ""
                last_install_date = ""

                for pack in content_packs:
                    if pack["name"] == pack_name:
                        version_after = pack["currentVersion"]
                        last_install_date = pack["lastInstalledDate"]
                        break

                updated_rows.append({
                    "Pack Name": pack_name,
                    "Version Before": version_before,
                    "Version After": version_after,
                    "Last Install Date": last_install_date
                })
    except FileNotFoundError:
        print(f"Error: CSV file not found at {csv_path}")
        return
    
    except Exception as e:
        print(f"An error occurred: {e}")
        return

    with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
        fieldnames = ["Pack Name", "Version Before", "Version After", "Last Install Date"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(updated_rows)

def main():
    parser = argparse.ArgumentParser(description="Update content pack version information in a CSV.")
    parser.add_argument("pack_version_csv", help="Path to the CSV file containing content pack update information.")
    args = parser.parse_args()

    content_packs = get_installed_content_packs_metadata()
    if content_packs:
        update_pack_versions_in_csv(args.pack_version_csv, content_packs)
        print(f"Content pack information updated in {args.pack_version_csv}")

if __name__ == "__main__":
    main()