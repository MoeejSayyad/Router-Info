import socket
import requests
import speedtest
import psutil
import threading
import time
import sys
import subprocess
from pathlib import Path
from datetime import datetime


def get_public_ip():
    try:
        return requests.get("https://api.ipify.org?format=json", timeout=5).json()["ip"]
    except Exception as e:
        return f"Error: {e}"


def get_private_ips():
    private_ips = []

    try:
        interfaces = psutil.net_if_addrs()

        for interface, addresses in interfaces.items():
            for addr in addresses:
                if addr.family == socket.AF_INET:
                    private_ips.append({
                        "Interface": interface,
                        "IP Address": addr.address
                    })

    except Exception as e:
        return [{"Error": str(e)}]

    return private_ips


def get_location():
    try:
        response = requests.get("http://ip-api.com/json/", timeout=5)
        data = response.json()

        if data["status"] == "success":
            return {
                "Country": data.get("country"),
                "Region": data.get("regionName"),
                "City": data.get("city"),
                "ISP": data.get("isp"),
                "Latitude": data.get("lat"),
                "Longitude": data.get("lon"),
                "Timezone": data.get("timezone")
            }
        else:
            return {"Error": "Location lookup failed"}

    except Exception as e:
        return {"Error": str(e)}


def run_binary(executable_path, args=None):
    executable = Path(executable_path)
    if not executable.is_file():
        raise FileNotFoundError(f"Binary not found: {executable}")

    result = subprocess.run(
        [str(executable)] + (args or []),
        capture_output=True,
        text=True,
        check=False,
    )
    return result


def write_binary_and_run(binary_data, file_path, args=None):
    output_path = Path(file_path)
    output_path.write_bytes(binary_data)
    return run_binary(output_path, args=args)


def render_progress(label, completed, total, width=40):
    if total <= 0:
        total = 1
    percent = min(completed / total, 1.0)
    filled = int(percent * width)
    empty = width - filled
    bar = '[' + '#' * filled + ' ' * empty + ']'
    percent_text = f"{int(percent * 100):3d}%"
    sys.stdout.write(f"\r{label} {bar} {percent_text} ({completed}/{total})")
    sys.stdout.flush()


def internet_speed():
    try:
        try:
            st = speedtest.Speedtest()
        except speedtest.ConfigRetrievalError as e:
            print("Config retrieval returned 403; retrying with secure=True...")
            st = speedtest.Speedtest(secure=True)

        print("Finding best server...")
        st.get_best_server()

        print("Testing download speed...")
        download_total = len(st.config['sizes']['download']) * st.config['counts']['download']
        download_completed = 0

        def download_callback(i, request_count, start=False, end=False):
            nonlocal download_completed
            if end:
                download_completed += 1
            render_progress("Downloading:", download_completed, request_count)

        download = st.download(callback=download_callback) / 1_000_000
        sys.stdout.write("\n")
        print("Download complete.")

        print("Testing upload speed...")
        upload_total = st.config['upload_max']
        upload_completed = 0

        def upload_callback(i, request_count, start=False, end=False):
            nonlocal upload_completed
            if end:
                upload_completed += 1
            render_progress("Uploading:", upload_completed, request_count)

        upload = st.upload(callback=upload_callback) / 1_000_000
        sys.stdout.write("\n")
        print("Upload complete.")

        ping = st.results.ping

        return {
            "Download (Mbps)": round(download, 2),
            "Download (MB/s)": round(download / 8, 2),
            "Upload (Mbps)": round(upload, 2),
            "Upload (MB/s)": round(upload / 8, 2),
            "Ping (ms)": round(ping, 2),
        }

    except Exception as e:
        return {"Error": str(e)}


def main():

    print("=" * 60)
    print(" Network Information Report")
    print("=" * 60)

    print("Date & Time :", datetime.now())
    print("Hostname    :", socket.gethostname())

    print("\nPublic IP")
    print("-" * 30)
    print(get_public_ip())

    print("\nPrivate IP Addresses")
    print("-" * 30)

    private_ips = get_private_ips()
    for item in private_ips:
        print(item)

    print("\nLocation Information (Public IP Based)")
    print("-" * 30)

    location = get_location()
    for key, value in location.items():
        print(f"{key:12}: {value}")

    print("\nInternet Speed Test")
    print("-" * 30)

    speed = internet_speed()
    for key, value in speed.items():
        print(f"{key:20}: {value}")

    print("\nDone!")


if __name__ == "__main__":
    main()