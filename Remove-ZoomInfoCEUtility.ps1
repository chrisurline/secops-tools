# PowerShell script to remove ZoomInfoCEUtility

# Define the application name
$applicationName = "ZoomInfoCEUtility"

# Function to uninstall application
Function Uninstall-Application {
    param(
        [string]$appName
    )

    # Get the list of installed applications from the registry (64-bit and 32-bit)
    $installedApps = @()
    $registryPaths = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )

    foreach ($path in $registryPaths) {
        $installedApps += Get-ItemProperty -Path $path -ErrorAction SilentlyContinue | Where-Object {
            $_.DisplayName -like "*$appName*"
        }
    }

    if ($installedApps) {
        foreach ($app in $installedApps) {
            Write-Host "Found application: $($app.DisplayName)"
            if ($app.UninstallString) {
                $uninstallCommand = $app.UninstallString
                # Some uninstall strings are enclosed in quotes
                if ($uninstallCommand.StartsWith('"')) {
                    $uninstallCommand = $uninstallCommand.Trim('"')
                }
                # If the uninstall string contains 'msiexec', adjust the command
                if ($uninstallCommand -like "*msiexec*") {
                    $uninstallCommand += " /qn /norestart"
                } else {
                    $uninstallCommand += " /quiet /norestart"
                }
                Write-Host "Uninstalling $($app.DisplayName)..."
                Start-Process -FilePath "cmd.exe" -ArgumentList "/c", $uninstallCommand -Wait -NoNewWindow
                Write-Host "$($app.DisplayName) has been uninstalled."
            } else {
                Write-Host "No uninstall string found for $($app.DisplayName)."
            }
        }
    } else {
        Write-Host "No applications matching '$appName' were found."
    }
}

# Execute the uninstall function
Uninstall-Application -appName $applicationName