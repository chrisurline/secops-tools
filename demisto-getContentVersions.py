import subprocess
import json
import re

def get_installed_content_pack_versions():
    
    # Retrieves the currently installed content pack versions using the demisto-sdk.
    
    try:
        # Execute demisto-sdk marketplace -lp to list installed packs
        result = subprocess.run(
            ["demisto-sdk", "marketplace", "-lp"],
            capture_output=True,
            text=True,
            check=True
        )
        output = result.stdout

        # Parse the output to extract pack ID and version
        packs = {}
        for line in output.splitlines():
            match = re.match(r"(\S+)\s+v(\d+\.\d+\.\d+)", line)
            if match:
                pack_id = match.group(1)
                version = match.group(2)
                packs[pack_id] = version

        return packs

    except subprocess.CalledProcessError as e:
        print(f"Error executing demisto-sdk: {e}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        return {}
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return {}

if __name__ == "__main__":
    installed_packs = get_installed_content_pack_versions()

    if installed_packs:
        print("Installed Content Pack Versions:")
        for pack_id, version in installed_packs.items():
            print(f"  {pack_id}: v{version}")
    else:
        print("No content packs found or an error occurred.")