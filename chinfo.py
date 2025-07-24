#!/usr/bin/env python3
"""
    chinfo = collect host info
    (cross-platform)

    this script gathers information about a host and outputs it as
    JSON. the script should run on any platform you may come accross.  
    The script collects:
    
        *   basic config: hostname, domain, current user and a list of
            local accounts + grabs operating system and architecture.
        *   network details: for each interface it records the interface 
            name, MAC address and associated IPv4/IPv6 addresses.
        *   hardware information: vendor/manufacturer, model, CPU, 
            memory totals and free memory, and a summary of mounted 
            storage devices with sizes and free/used space.
        *   edr/security tools: the script inspects running processes 
        and reports
            known antivirus/EDR agents based on a curated list of 
            process names. process list includes many common endpoint 
            security products such as CrowdStrike Falcon, Carbon 
            Black, SentinelOne, Windows Defender and others, 
            derived from industry sources【764838684698230†L49-L167】.

    goal is to provide a consistent JSON report regardless of the host.

    usage: (output to console)
        python3 chinfo.py
    
    usage: (output to file)
        python3 chinfo.py > host_details.json

    NOTE:   many commands used here require administrative/root privileges to
            retrieve comprehensive information.  The script attempts to handle failures
            gracefully but some fields may be missing on systems where particular
            commands are unavailable.
"""

import json
import os
import platform
import re
import socket
import subprocess
import sys
import time
from typing import Dict, List, Optional


def run_command(command: str) -> str:
    """
        command is executed with ``shell=True`` so that it may include
        pipelines or shell builtins.  
    """
    try:
        # ``/bin/sh``.  we request universal_newlines=True so that output
        # is decoded to str using the system encoding.
        return subprocess.check_output(
            command,
            shell=True,
            stderr=subprocess.DEVNULL,
            universal_newlines=True,
        ).strip()
    except Exception:
        return ""


def get_hostname() -> str:
    """ return the system hostname using the socket module. """
    try:
        return socket.gethostname()
    except Exception:
        return ""


def get_os_info() -> Dict[str, str]:
    """ return basic OS information including name, release and architecture. """
    return {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "architecture": platform.machine(),
    }


def get_current_user() -> str:
    """ return the username of the current effective user. """
    try:
        import getpass

        return getpass.getuser()
    except Exception:
        return os.environ.get("USER", "")


def get_domain_name() -> Optional[str]:
    """
        attempt to determine the domain (or workgroup) the host is joined to.

        1 - ``wmic`` command
        2 - ``computersystem get domain``
        3 - ``USERDOMAIN``   
        domain is less common on linux/macos; we attempt to read the DNS domain
        using ``hostname -d`` or ``domainname``.  If no domain is found a
        ``None`` is returned.
    """
    system = platform.system().lower()
    domain: Optional[str] = None

    if system == "windows":
        # try WMIC for the computer domain
        output = run_command("wmic computersystem get domain")
        # first line will be "Domain"; subsequent lines contain the value
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        if len(lines) >= 2:
            # choose the last non‑blank line as the domain
            domain = lines[-1]
        if not domain:
            # fallback to USERDOMAIN environment variable
            domain = os.environ.get("USERDOMAIN")
        return domain

    # POSIX hosts: try hostname -d (Linux) or dnsdomainname
    for cmd in ["hostname -d", "dnsdomainname", "domainname"]:
        output = run_command(cmd)
        if output and output.lower() not in ("(none)", "unknown"):
            domain = output.strip()
            break
    return domain


def get_local_users() -> List[str]:
    """
        return a list of local user names.
        system accounts (e.g., users with non‑interactive shells) are 
        included because they may be relevant to investigations.
    """
    system = platform.system().lower()
    users: List[str] = []
    if system == "windows":
        output = run_command("net user")
        # net user output has a header and footer; account names are
        # arranged in columns.  We'll split on whitespace and ignore headers.
        if output:
            lines = output.splitlines()
            # skip lines until we hit a line containing ----- which delineates
            # column headings
            collecting = False
            for line in lines:
                if not collecting:
                    if line.strip().startswith("---"):
                        collecting = True
                    continue
                # when we reach the next empty line the listing ends
                if not line.strip():
                    break
                users += [name for name in line.split() if name]
    else:
        # POSIX: parse /etc/passwd
        try:
            with open("/etc/passwd", "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if not line.strip() or line.startswith("#"):
                        continue
                    parts = line.split(":")
                    if parts:
                        users.append(parts[0])
        except Exception:
            pass
    return users


def parse_ip_config_windows() -> List[Dict[str, any]]:
    """
        parse the output of ``ipconfig /all`` into interface dictionaries.
    """
    output = run_command("ipconfig /all")
    interfaces: List[Dict[str, any]] = []
    if not output:
        return interfaces
    adapter = {}
    for line in output.splitlines():
        if not line.strip():
            # blank line indicates separation between adapters
            if adapter:
                interfaces.append(adapter)
                adapter = {}
            continue
        # identify adapter names (they end with a colon)
        if line.lstrip() == line and line.strip().endswith(":"):
            # start of a new adapter section
            if adapter:
                interfaces.append(adapter)
                adapter = {}
            adapter["name"] = line.strip().rstrip(":")
        else:
            parts = line.split(":", 1)
            if len(parts) != 2:
                continue
            key, value = parts[0].strip(), parts[1].strip()
            key_lower = key.lower()
            # map relevant fields
            if "physical address" in key_lower:
                adapter.setdefault("mac", value)
            elif key_lower in ("ipv4 address", "ip address", "autoconfiguration ipv4 address"):
                # remove suffix
                ip = value.split("(")[0].strip()
                adapter.setdefault("ipv4", []).append(ip)
            elif "ipv6 address" in key_lower:
                ip = value.split("(")[0].strip()
                adapter.setdefault("ipv6", []).append(ip)
    # append last adapter if present
    if adapter:
        interfaces.append(adapter)
    return interfaces


def parse_ip_config_posix() -> List[Dict[str, any]]:
    """
        parse network interface information on Linux and macOS.

        this function executes the appropriate command and returns a list of
        dictionaries describing each interface.
    """
    system = platform.system().lower()
    interfaces: List[Dict[str, any]] = []
    if system == "linux":
        cmd = "ip -o addr show"
    else:
        # macOS or other BSD: fallback to ifconfig
        cmd = "ifconfig -a"
    output = run_command(cmd)
    if not output:
        return interfaces
    if system == "linux":
        # ip -o addr show outputs one line per address: <idx>: <ifname>    <fam> <addr>/<mask> ...
        iface_map: Dict[str, Dict[str, any]] = {}
        for line in output.splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            # format: index: ifname    family  address/mask  brd ...
            ifname = parts[1]
            family = parts[2]
            addr_mask = parts[3]
            ip, *_ = addr_mask.split("/")
            iface = iface_map.setdefault(ifname, {"name": ifname})
            if family == "link":
                # MAC address appears after second field (addresses are often in format <ifname> link/ether <mac>)
                # use a regex to capture MAC
                mac_match = re.search(r"link/\w+ ([0-9a-f:]{17}|[0-9a-f]{2}(?:-[0-9a-f]{2}){5})", line, re.IGNORECASE)
                if mac_match:
                    iface["mac"] = mac_match.group(1)
            elif family == "inet":
                iface.setdefault("ipv4", []).append(ip)
            elif family == "inet6":
                iface.setdefault("ipv6", []).append(ip)
        interfaces = list(iface_map.values())
    else:
        # basic parser for BSD ifconfig output
        adapter = {}
        for line in output.splitlines():
            if not line.startswith("\t"):
                # new interface header: e.g., en0: flags=8863<UP,...>
                if adapter:
                    interfaces.append(adapter)
                    adapter = {}
                # interface name before colon
                m = re.match(r"^(\S+):", line)
                if m:
                    adapter["name"] = m.group(1)
                # look for ether (MAC) on same line
                m2 = re.search(r"ether ([0-9a-f:]{17})", line)
                if m2:
                    adapter["mac"] = m2.group(1)
            else:
                # subsequent lines, check for inet/inet6
                m4 = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", line)
                if m4:
                    adapter.setdefault("ipv4", []).append(m4.group(1))
                m6 = re.search(r"inet6 ([0-9a-f:]+)", line)
                if m6:
                    adapter.setdefault("ipv6", []).append(m6.group(1))
                mmac = re.search(r"ether ([0-9a-f:]{17})", line)
                if mmac:
                    adapter["mac"] = mmac.group(1)
        if adapter:
            interfaces.append(adapter)
    return interfaces


def get_network_info() -> List[Dict[str, any]]:
    """ return a list of network interface dictionaries for the current host. """
    system = platform.system().lower()
    if system == "windows":
        return parse_ip_config_windows()
    return parse_ip_config_posix()


def get_memory_info() -> Dict[str, Optional[int]]:
    """ 
        return total and free memory in bytes.
        if a method fails the values are set to ``None``.
    """
    system = platform.system().lower()
    total = free = None
    if system == "windows":
        output = run_command(
            "wmic OS get FreePhysicalMemory,TotalVisibleMemorySize /Value"
        )
        if output:
            for line in output.splitlines():
                if "=" in line:
                    key, value = line.strip().split("=", 1)
                    if key == "FreePhysicalMemory":
                        try:
                            free = int(value) * 1024  # kilobytes to bytes
                        except ValueError:
                            pass
                    elif key == "TotalVisibleMemorySize":
                        try:
                            total = int(value) * 1024
                        except ValueError:
                            pass
    elif system == "linux":
        # use free -b for bytes; fallback to /proc/meminfo
        output = run_command("free -b")
        if output:
            # skip header line; parse line starting with "Mem:"
            for line in output.splitlines():
                if line.startswith("Mem:"):
                    parts = line.split()
                    # format: Mem: total used free shared buff/cache available
                    if len(parts) >= 4:
                        total = int(parts[1])
                        free = int(parts[3])
                    break
        else:
            # parse /proc/meminfo
            try:
                with open("/proc/meminfo", "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if line.startswith("MemTotal:"):
                            total = int(line.split()[1]) * 1024
                        elif line.startswith("MemFree:"):
                            free = int(line.split()[1]) * 1024
                        if total is not None and free is not None:
                            break
            except Exception:
                pass
    elif system == "darwin":
        # macOS: sysctl hw.memsize gives total memory in bytes
        total_str = run_command("sysctl -n hw.memsize")
        if total_str.isdigit():
            total = int(total_str)
        # free memory: use vm_stat; page size from vm_stat header
        vm_output = run_command("vm_stat")
        if vm_output:
            page_size = 4096  # default
            m_ps = re.search(r"page size of (\d+) bytes", vm_output)
            if m_ps:
                page_size = int(m_ps.group(1))
            pages_free = 0
            for line in vm_output.splitlines():
                m = re.match(r"^Pages free:\s+(\d+)", line)
                if m:
                    pages_free = int(m.group(1))
                    break
            if pages_free:
                free = pages_free * page_size
    return {"total": total, "free": free}


def get_cpu_info() -> Optional[str]:
    """ return a human‑readable CPU description if available. """
    system = platform.system().lower()
    cpu = None
    if system == "windows":
        output = run_command("wmic cpu get Name /Value")
        for line in output.splitlines():
            if line.startswith("Name="):
                cpu = line.split("=", 1)[1].strip()
                break
    elif system == "linux":
        # parse /proc/cpuinfo for model name
        try:
            with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.lower().startswith("model name"):
                        cpu = line.split(":", 1)[1].strip()
                        break
        except Exception:
            pass
        if not cpu:
            # fallback to lscpu
            output = run_command("lscpu")
            for line in output.splitlines():
                if "model name" in line.lower():
                    cpu = line.split(":", 1)[1].strip()
                    break
    elif system == "darwin":
        output = run_command("sysctl -n machdep.cpu.brand_string")
        if output:
            cpu = output.strip()
    return cpu


def get_vendor_model() -> Dict[str, Optional[str]]:
    """ retrieve the system manufacturer and product/model information. """
    system = platform.system().lower()
    manufacturer = model = None
    if system == "windows":
        output = run_command("wmic computersystem get manufacturer,model /Value")
        for line in output.splitlines():
            if line.lower().startswith("manufacturer="):
                manufacturer = line.split("=", 1)[1].strip()
            elif line.lower().startswith("model="):
                model = line.split("=", 1)[1].strip()
    elif system == "linux":
        # try reading sysfs files which expose vendor and product name
        try:
            with open("/sys/class/dmi/id/sys_vendor", "r", encoding="utf-8", errors="ignore") as f:
                manufacturer = f.read().strip()
        except Exception:
            pass
        try:
            with open("/sys/class/dmi/id/product_name", "r", encoding="utf-8", errors="ignore") as f:
                model = f.read().strip()
        except Exception:
            pass
    elif system == "darwin":
        # macOS: use system_profiler
        output = run_command("system_profiler SPHardwareDataType")
        if output:
            for line in output.splitlines():
                if "Model Name:" in line:
                    # Example: Model Name: MacBookPro16,1
                    model = line.split(":", 1)[1].strip()
                elif "Model Identifier:" in line and not model:
                    model = line.split(":", 1)[1].strip()
                elif "Manufacturer:" in line:
                    manufacturer = line.split(":", 1)[1].strip()
    return {"manufacturer": manufacturer, "model": model}


def get_disk_info() -> List[Dict[str, any]]:
    """return a list of logical drives or mount points with size and free space.

    On Windows, ``wmic logicaldisk get size,freespace,caption`` lists the
    drive letter (caption), free space and total size in bytes【358342111371978†L163-L170】.
    On POSIX systems we use the ``df`` command with a portable output format.
    """
    system = platform.system().lower()
    disks: List[Dict[str, any]] = []
    if system == "windows":
        output = run_command("wmic logicaldisk get Caption,FileSystem,FreeSpace,Size /Format:csv")
        # csv output has header lines: Node,Caption,FileSystem,FreeSpace,Size
        if output:
            for line in output.splitlines():
                if not line or line.startswith("Node"):
                    continue
                parts = line.split(",")
                # parts[1]: Caption (e.g., C:)
                # parts[2]: FileSystem (e.g., NTFS)
                # parts[3]: FreeSpace
                # parts[4]: Size
                if len(parts) >= 5:
                    caption = parts[1]
                    filesystem = parts[2] or None
                    try:
                        free = int(parts[3]) if parts[3] else None
                    except ValueError:
                        free = None
                    try:
                        size = int(parts[4]) if parts[4] else None
                    except ValueError:
                        size = None
                    used = size - free if size is not None and free is not None else None
                    disks.append(
                        {
                            "name": caption,
                            "filesystem": filesystem,
                            "total": size,
                            "free": free,
                            "used": used,
                        }
                    )
    else:
        # Use df with -P (POSIX) to ensure fixed column widths; use -B1 to output sizes in bytes
        output = run_command("df -P -B1")
        if output:
            lines = output.splitlines()
            # skip header
            for line in lines[1:]:
                parts = line.split()
                if len(parts) < 6:
                    continue
                filesystem = parts[0]
                try:
                    size = int(parts[1])
                except ValueError:
                    size = None
                try:
                    used = int(parts[2])
                except ValueError:
                    used = None
                try:
                    free = int(parts[3])
                except ValueError:
                    free = None
                mount = parts[5]
                disks.append(
                    {
                        "name": mount,
                        "filesystem": filesystem,
                        "total": size,
                        "free": free,
                        "used": used,
                    }
                )
    return disks


# predefined mapping of security software process names to vendor names
SECURITY_PROCESSES: Dict[str, str] = {
    # CrowdStrike and Falcon Insight
    "csfalconservice": "CrowdStrike Falcon",
    "cbcomms": "CrowdStrike Falcon Insight XDR",
    "crowdstrike": "CrowdStrike Falcon",
    # Carbon Black / VMware
    "carbonsensor": "VMware Carbon Black EDR",
    "cb.exe": "Carbon Black EDR",
    # SentinelOne
    "cpx": "SentinelOne Singularity XDR",
    # Cybereason
    "cybereason": "Cybereason EDR",
    # Tanium
    "tanclient": "Tanium EDR",
    # FireEye / Trellix
    "xagt": "FireEye HX",
    "trapsagent": "Palo Alto Networks Cortex XDR",
    "trapsd": "Palo Alto Networks Cortex XDR",
    # Windows Defender / Microsoft
    "msmpeng": "Microsoft Defender",
    "msascuil": "Microsoft Defender",
    "windefend": "Microsoft Defender",
    "sysmon": "Microsoft Sysmon",
    # Symantec
    "ccsvchst": "Symantec Endpoint Protection",
    "rtvscan": "Symantec Endpoint Protection",
    # McAfee
    "edpa": "McAfee Endpoint Security",
    "shstat": "McAfee VirusScan",
    "mcshield": "McAfee VirusScan",
    "mfefire": "McAfee Host Intrusion Prevention",
    "dlpsensor": "McAfee DLP Sensor",
    # Bitdefender
    "bdagent": "Bitdefender",
    "vsserv": "Bitdefender",
    # Sophos
    "savservice": "Sophos Endpoint Security",
    "sophosav": "Sophos Endpoint Security",
    "sophossps": "Sophos Endpoint Security",
    "sophosui": "Sophos Endpoint Security",
    # Panda Security
    "pavfnsvr": "Panda Security",
    "pavsrv": "Panda Security",
    "psanhost": "Panda Security",
    "panda_url_filtering": "Panda Security",
    # Check Point
    "cpd": "Check Point Daemon",
    "fw": "Check Point Firewall",
    # Fortinet
    "fortiedr": "Fortinet FortiEDR",
    # ESET
    "egui": "ESET NOD32",
    "ekrn": "ESET NOD32",
    # Kaspersky
    "avp": "Kaspersky Anti‑Virus",
    # Avast/AVG
    "avastsvc": "Avast",
    "avastui": "Avast",
    "avgnt": "Avira",
    "avguard": "Avira",
    # Malwarebytes
    "mbamservice": "Malwarebytes",
    "mbamtray": "Malwarebytes",
    # FireEye
    "firesvc": "FireEye Endpoint Agent",
    "firetray": "FireEye Endpoint Agent",
    # Tanium repeated above
    # Others
    "dlpagent": "Symantec DLP Agent",
    "mbamservice": "Malwarebytes",
    "mbamtray": "Malwarebytes",
    "savservice": "Sophos Endpoint Security",
    "wrsa": "Webroot SecureAnywhere",
    "truecrypt": "TrueCrypt (encryption tool)",
}


def get_running_process_names() -> List[str]:
    """ return a list of process names (lower‑case) currently running. """
    system = platform.system().lower()
    processes: List[str] = []
    if system == "windows":
        output = run_command("tasklist /fo csv /nh")
        # CSV format: "Image Name","PID","Session Name","Session#","Mem Usage"
        for line in output.splitlines():
            if not line:
                continue
            # Remove surrounding quotes and split by ","
            fields = [field.strip("\"") for field in line.split(",")]
            if fields:
                exe = fields[0].lower()
                # strip .exe extension for comparison
                if exe.endswith(".exe"):
                    exe = exe[:-4]
                processes.append(exe)
    else:
        # Use ps -eo comm to list the executable names only
        output = run_command("ps -eo comm")
        for line in output.splitlines()[1:]:  # skip header
            exe = os.path.basename(line.strip()).lower()
            processes.append(exe)
    return processes


def detect_security_tools() -> List[str]:
    """
        detect known security/EDR tools by matching running process names.

        returns a sorted list of unique vendor/product names found.  If no
        security tools are detected, the list will be empty.  The mapping is
        maintained in ``SECURITY_PROCESSES``.
    """
    running = get_running_process_names()
    detected = set()
    for proc in running:
        if proc in SECURITY_PROCESSES:
            detected.add(SECURITY_PROCESSES[proc])
    return sorted(detected)


def gather_host_info() -> Dict[str, any]:
    """ collect all host information and return as a dict. """
    host_info: Dict[str, any] = {}
    host_info["collected_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    host_info["basic_config"] = {
        "hostname": get_hostname(),
        "domain": get_domain_name(),
        "current_user": get_current_user(),
        "os": get_os_info(),
        "users": get_local_users(),
    }
    host_info["network"] = get_network_info()
    # Hardware information
    mem_info = get_memory_info()
    host_info["hardware"] = {
        **get_vendor_model(),
        "cpu": get_cpu_info(),
        "memory_total_bytes": mem_info.get("total"),
        "memory_free_bytes": mem_info.get("free"),
        "disks": get_disk_info(),
    }
    host_info["security_tools"] = {
        "detected": detect_security_tools(),
        "detection_method": "process_scan",
    }
    return host_info


def main() -> None:
    info = gather_host_info()
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()