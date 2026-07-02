import argparse
import socket
import requests
import speedtest
import psutil
import threading
import time
import sys
import subprocess
import json
import sqlite3
import logging
import platform
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
try:
    import yaml
except Exception:
    yaml = None


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


def get_routing_table():
    system = platform.system().lower()
    if system == 'windows':
        cmd = ['route', 'print']
    elif system == 'linux':
        cmd = ['ip', 'route', 'show']
    elif system == 'darwin':
        cmd = ['netstat', '-rn']
    else:
        cmd = ['netstat', '-rn']

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        output = result.stdout.strip() or result.stderr.strip()
        if not output:
            return [f"No routing table output from: {' '.join(cmd)}"]
        return output.splitlines()
    except Exception as e:
        return [{"Error": str(e)}]


def ping_targets(targets):
    results = []
    if not targets:
        return results

    for target in targets:
        if not target:
            continue

        system = platform.system().lower()
        if system == 'windows':
            cmd = ['ping', '-n', '1', '-w', '1000', target]
        else:
            cmd = ['ping', '-c', '1', '-W', '1', target]

        process = subprocess.run(cmd, capture_output=True, text=True, check=False)
        output = process.stdout.strip() or process.stderr.strip()
        success = process.returncode == 0
        rtt = None

        for line in output.splitlines():
            if 'time=' in line.lower():
                import re
                match = re.search(r'time[=<]\s*([\d\.]+)\s*ms', line, re.IGNORECASE)
                if match:
                    rtt = float(match.group(1))
                    break

        results.append({
            'target': target,
            'success': success,
            'rtt_ms': rtt,
            'output': output.splitlines()
        })

    return results


def run_traceroute(target, max_hops=30):
    system = platform.system().lower()
    if system == 'windows':
        cmd = ['tracert', '-d', '-h', str(max_hops), target]
    else:
        cmd = ['traceroute', '-n', '-m', str(max_hops), target]

    process = subprocess.run(cmd, capture_output=True, text=True, check=False)
    output = process.stdout.strip() or process.stderr.strip()
    return {
        'target': target,
        'success': process.returncode == 0,
        'hops': output.splitlines()
    }


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


def format_report(public_ip, private_ips, location, speed_results, routing_table, timestamp, hostname):
    lines = []
    lines.append("=" * 60)
    lines.append(" Network Information Report")
    lines.append("=" * 60)
    lines.append(f"Date & Time : {timestamp}")
    lines.append(f"Hostname    : {hostname}")
    lines.append("")
    lines.append("Public IP")
    lines.append("-" * 30)
    lines.append(str(public_ip))
    lines.append("")
    lines.append("Private IP Addresses")
    lines.append("-" * 30)
    for item in private_ips:
        if isinstance(item, dict):
            lines.append(f"{item.get('Interface', '')}: {item.get('IP Address', '')}")
        else:
            lines.append(str(item))
    lines.append("")
    lines.append("Location Information (Public IP Based)")
    lines.append("-" * 30)
    for key, value in location.items():
        lines.append(f"{key:12}: {value}")
    lines.append("")
    lines.append("Internet Speed Test")
    lines.append("-" * 30)
    for key, value in speed_results.items():
        lines.append(f"{key:20}: {value}")
    lines.append("")
    lines.append("Routing Table")
    lines.append("-" * 30)
    if isinstance(routing_table, list):
        if routing_table:
            lines.extend(routing_table)
        else:
            lines.append("No routing table entries found.")
    else:
        lines.append(str(routing_table))
    lines.append("")
    lines.append("Done!")
    return "\n".join(lines)


def save_report(report_text, file_path):
    output_path = Path(file_path)
    output_path.write_text(report_text, encoding="utf-8")
    return output_path


def timestamped_output_path(path, timestamp):
    output_path = Path(path)
    time_suffix = timestamp.strftime("%Y%m%d_%H%M%S")
    if output_path.suffix:
        return output_path.with_name(f"{output_path.stem}_{time_suffix}{output_path.suffix}")
    return output_path.with_name(f"{output_path.name}_{time_suffix}")


def init_db(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY,
        timestamp TEXT,
        hostname TEXT,
        data JSON
    )
    """)
    conn.commit()
    return conn


def store_report_db(conn, timestamp, hostname, data):
    cur = conn.cursor()
    cur.execute("INSERT INTO reports (timestamp, hostname, data) VALUES (?, ?, ?)",
                (timestamp.isoformat(), hostname, json.dumps(data)))
    conn.commit()
    return cur.lastrowid


def load_config(path=None):
    defaults = {
        'speedtest': {'run': True},
        'routing_table': {'run': True},
        'ping_targets': ['8.8.8.8', '1.1.1.1'],
        'dns_hosts': ['google.com', 'cloudflare.com'],
        'thresholds': {'download_min_mbps': 10, 'upload_min_mbps': 1, 'ping_max_ms': 200},
        'webhook': None,
        'db': 'network_reports.db',
        'outputs': {'text': 'network_report.txt'}
    }
    if path and Path(path).is_file() and yaml:
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                cfg = yaml.safe_load(fh)
                if isinstance(cfg, dict):
                    defaults.update(cfg)
        except Exception:
            pass
    return defaults


def setup_logging(level=logging.INFO, path=None):
    logger = logging.getLogger('netinfo')
    logger.setLevel(level)
    fmt = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    if path:
        fh = logging.FileHandler(path)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    return logger


def parse_args():
    parser = argparse.ArgumentParser(description="Collect and optionally save network information report.")
    parser.add_argument(
        "--save",
        nargs="?",
        const="network_report.txt",
        help="Save the text report to a file. Optionally provide a filename.",
    )
    parser.add_argument(
        "--config",
        nargs="?",
        default=None,
        help="Path to a YAML config file to override defaults.",
    )
    parser.add_argument(
        "--run-speedtest",
        dest="run_speedtest",
        action="store_true",
        help="Enable running the speedtest (default on).",
    )
    parser.add_argument(
        "--no-speedtest",
        dest="run_speedtest",
        action="store_false",
        help="Disable running the speedtest.",
    )
    parser.set_defaults(run_speedtest=True)
    parser.add_argument(
        "--no-routing-table",
        dest="run_routing_table",
        action="store_false",
        help="Disable collecting the routing table.",
    )
    parser.set_defaults(run_routing_table=True)
    parser.add_argument(
        "--no-prompt",
        action="store_true",
        help="Do not prompt to save the report interactively.",
    )
    return parser.parse_args()


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
            "download_mbps": round(download, 2),
            "download_mBps": round(download / 8, 2),
            "upload_mbps": round(upload, 2),
            "upload_mBps": round(upload / 8, 2),
            "ping_ms": round(ping, 2),
        }

    except Exception as e:
        return {"Error": str(e)}


def main():
    args = parse_args()

    cfg = load_config(args.config)
    logger = setup_logging()

    timestamp = datetime.now()
    hostname = socket.gethostname()

    logger.info('Collecting network information')

    public_ip = get_public_ip()
    private_ips = get_private_ips()
    location = get_location()

    # Run diagnostics in parallel
    results = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {}
        if cfg.get('speedtest', {}).get('run', True) and args.run_speedtest:
            futures[ex.submit(internet_speed)] = 'speedtest'
        futures[ex.submit(lambda: get_public_ip())] = 'public_ip_refresh'
        futures[ex.submit(lambda: get_private_ips())] = 'private_ips_refresh'
        if cfg.get('routing_table', {}).get('run', True) and args.run_routing_table:
            futures[ex.submit(get_routing_table)] = 'routing_table'

        # Ping targets
        def ping_task():
            return ping_targets(cfg.get('ping_targets', []))

        futures[ex.submit(ping_task)] = 'pings'

        # Traceroute first ping target
        first_target = cfg.get('ping_targets', [None])[0]
        if first_target:
            futures[ex.submit(lambda t=first_target: run_traceroute(t))] = 'traceroute'

        for fut in as_completed(futures):
            k = futures[fut]
            try:
                results[k] = fut.result()
            except Exception as e:
                results[k] = {'error': str(e)}

    speed_results = results.get('speedtest', {})

    report_text = format_report(
        public_ip=public_ip,
        private_ips=private_ips,
        location=location,
        speed_results=speed_results,
        routing_table=results.get('routing_table', []),
        timestamp=timestamp,
        hostname=hostname,
    )

    print(report_text)

    # Structured outputs
    out_json = {
        'timestamp': timestamp.isoformat(),
        'hostname': hostname,
        'public_ip': public_ip,
        'private_ips': private_ips,
        'location': location,
        'speed_test': speed_results,
        'routing_table': results.get('routing_table'),
        'pings': results.get('pings'),
        'traceroute': results.get('traceroute')
    }

    # Save outputs
    try:
        text_path = args.save or cfg.get('outputs', {}).get('text', 'network_report.txt')
        if args.save is None:
            text_path = timestamped_output_path(text_path, timestamp)
        save_report(report_text, text_path)

        # store in sqlite
        db_conn = init_db(cfg.get('db'))
        store_report_db(db_conn, timestamp, hostname, out_json)
        db_conn.close()

    except Exception as e:
        logger.exception('Error saving outputs: %s', e)

    # Threshold check and alert
    thresholds = cfg.get('thresholds', {})
    alerts = []
    if speed_results:
        if speed_results.get('download_mbps', 0) < thresholds.get('download_min_mbps', 0):
            alerts.append('Download below threshold')
        if speed_results.get('upload_mbps', 0) < thresholds.get('upload_min_mbps', 0):
            alerts.append('Upload below threshold')
        if speed_results.get('ping_ms', 9999) > thresholds.get('ping_max_ms', 9999):
            alerts.append('Ping above threshold')

    if alerts and cfg.get('webhook'):
        try:
            requests.post(cfg['webhook'], json={'alerts': alerts, 'report': out_json}, timeout=5)
        except Exception:
            logger.exception('Failed to send webhook')

    if alerts:
        logger.warning('Alerts: %s', alerts)


if __name__ == "__main__":
    main()