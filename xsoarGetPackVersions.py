import requests
import csv
import os

# this script is intended to be step 1 of a 2 step process
# in this step we will log the before versions of our content pack
# we perform updates to the content packs using the xsoar console, reviewing the change logs for potential breaking changes, etc.
# step 2 takes the scripts we identified here and adds the new version to csv tracking sheet

# xsoar api config
# the variables below will work but you should replace them with a more secure alternative - env variables at minimum :)
XSOAR_BASE_URL = os.environ.get("DEMISTO_BASE_URL") # example: "https://xsoar-instance.xyz"
XSOAR_API_KEY = os.environ.get("DEMISTO_API_KEY") # your xsoar api key  
XSOAR_HEADERS = {
    "Authorization": XSOAR_API_KEY,
    "Content-Type": "application/json",
    "Accept": "application/json"
}

# csv to output too
OUTPUT_CSV = "content_pack_updates.csv"

def get_installed_content_packs_metadata():
   
    # retrieve metadata for all installed content packs
    
    url = f"{XSOAR_BASE_URL}/contentpacks/metadata/installed"
    try:
        response = requests.get(url, headers=XSOAR_HEADERS, verify=False)
        response.raise_for_status()  # Raise an exception for bad status codes
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching content pack metadata: {e}")
        return None

def filter_and_output_updates(content_packs):
    
    # filter content packs with available updates and outputs them to the csv

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as csvfile:
        fieldnames = ["Content Pack Name", "Current Version"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for pack in content_packs:
            if pack.get("updateAvailable"):
                writer.writerow({
                    "Content Pack Name": pack["name"],
                    "Current Version": pack["currentVersion"]
                })

def main():
    content_packs = get_installed_content_packs_metadata()
    if content_packs:
        filter_and_output_updates(content_packs)
        print(f"Content pack update information written to {OUTPUT_CSV}")

if __name__ == "__main__":
    main()