import argparse
import socket
import requests
import speedtest
import psutil
import threading
import time
import sys
import math
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


def get_ssid():
    system = platform.system().lower()
    try:
        if system == 'windows':
            cmd = ['netsh', 'wlan', 'show', 'interfaces']
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            output = result.stdout.strip() or result.stderr.strip()
            for line in output.splitlines():
                if ':' in line:
                    key, value = line.split(':', 1)
                    if key.strip().lower() == 'ssid':
                        return value.strip() or None
            return None

        if system == 'linux':
            candidates = [
                ['iwgetid', '-r'],
                ['nmcli', '-t', '-f', 'active,ssid', 'dev', 'wifi'],
            ]
            for cmd in candidates:
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                    output = (result.stdout or result.stderr).strip()
                    if not output:
                        continue
                    if cmd[0] == 'nmcli':
                        parts = output.split(':')
                        if len(parts) >= 2 and parts[0].strip().lower() == 'yes':
                            return parts[1].strip() or None
                    return output
                except FileNotFoundError:
                    continue
            return None

        if system == 'darwin':
            cmd = ['/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport', '-I']
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            output = result.stdout.strip() or result.stderr.strip()
            for line in output.splitlines():
                if line.startswith('SSID:'):
                    return line.split(':', 1)[1].strip() or None
            return None

        return None
    except Exception:
        return None


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

    try:
        process = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=30)
        output = process.stdout.strip() or process.stderr.strip()
        success = process.returncode == 0
    except subprocess.TimeoutExpired as e:
        output = f"Traceroute timed out: {e}"
        success = False
    return {
        'target': target,
        'success': success,
        'hops': output.splitlines() if isinstance(output, str) else []
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


def format_report(public_ip, private_ips, location, speed_results, routing_table, timestamp, hostname, ssid=None):
    lines = []
    lines.append("=" * 60)
    lines.append(" Network Information Report")
    lines.append("=" * 60)
    lines.append(f"Date & Time : {timestamp}")
    lines.append(f"Hostname    : {hostname}")
    lines.append("")
    lines.append("Wi-Fi SSID")
    lines.append("-" * 30)
    lines.append(str(ssid) if ssid else "Not detected")
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
        display_value = "N/A" if value is None else value
        lines.append(f"{key:20}: {display_value}")
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
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_text, encoding="utf-8")
    return output_path


def timestamped_output_path(path, timestamp):
    output_path = Path(path)
    time_suffix = timestamp.strftime("%Y%m%d_%H%M%S")
    if output_path.suffix:
        return output_path.with_name(f"{output_path.stem}_{time_suffix}{output_path.suffix}")
    return output_path.with_name(f"{output_path.name}_{time_suffix}")


def init_db(db_path):
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_file)
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
        'speedtest': {'run': True, 'method': 'speedtest'},
        'routing_table': {'run': True},
        'ssid': {'run': True},
        'ping_targets': ['8.8.8.8', '1.1.1.1'],
        'dns_hosts': ['google.com', 'cloudflare.com'],
        'thresholds': {'download_min_mbps': 10, 'upload_min_mbps': 1, 'ping_max_ms': 200},
        'webhook': None,
        'db': 'reports/network_reports.db',
        'outputs': {'text': 'reports/network_report.txt'}
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


def setup_logging(level=logging.WARNING, path=None):
    logger = logging.getLogger('netinfo')
    logger.setLevel(level)
    if not logger.handlers:
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
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output and progress indicators.",
    )
    parser.add_argument(
        "--save",
        nargs="?",
        const="reports/network_report.txt",
        help="Save the text report to a file. Optionally provide a filename.",
    )
    parser.add_argument(
        "--no-save",
        dest="save_report",
        action="store_false",
        help="Do not save the report to disk or the SQLite database.",
    )
    parser.set_defaults(save_report=True)
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
        "--no-ssid",
        dest="run_ssid",
        action="store_false",
        help="Disable SSID detection.",
    )
    parser.set_defaults(run_ssid=True)
    parser.add_argument(
        "--speedtest-method",
        choices=['speedtest', 'http-download'],
        default=None,
        help="Choose the speed test method: 'speedtest' or 'http-download'.",
    )
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


def http_download_speed(url="http://speedtest.tele2.net/10MB.zip", max_duration=20, quiet=True):
    try:
        if not quiet:
            print(f"Starting HTTP download speed test from {url}...")

        start = time.perf_counter()
        total_bytes = 0
        with requests.get(url, stream=True, timeout=10) as response:
            response.raise_for_status()
            for chunk in response.iter_content(chunk_size=4096):
                if not chunk:
                    continue
                total_bytes += len(chunk)
                elapsed = time.perf_counter() - start
                if elapsed >= max_duration:
                    break

        elapsed = max(time.perf_counter() - start, 1e-6)
        mbps = (total_bytes * 8) / 1_000_000 / elapsed
        return {
            "download_mbps": round(mbps, 2),
            "download_mBps": round(mbps / 8, 2),
            "upload_mbps": None,
            "upload_mBps": None,
            "ping_ms": None,
            "method": "http-download",
            "source_url": url,
        }

    except Exception as e:
        return {"Error": str(e)}


def sanitize_speedtest_result(result):
    if not isinstance(result, dict):
        return result

    cleaned = dict(result)

    for key in ("download_mbps", "upload_mbps", "download_mBps", "upload_mBps"):
        value = cleaned.get(key)
        if value is None:
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            cleaned[key] = None
            continue
        if not math.isfinite(numeric) or numeric < 0 or numeric > 10000:
            cleaned[key] = None

    ping = cleaned.get("ping_ms")
    if ping is not None:
        try:
            ping_value = float(ping)
        except (TypeError, ValueError):
            cleaned["ping_ms"] = None
        else:
            if not math.isfinite(ping_value) or ping_value < 0 or ping_value > 60000:
                cleaned["ping_ms"] = None
            else:
                cleaned["ping_ms"] = round(ping_value, 2)

    return cleaned


def speedtest_speed(quiet=True):
    try:
        try:
            st = speedtest.Speedtest(secure=True)
        except Exception:
            st = speedtest.Speedtest()

        if not quiet:
            print("Finding best server...")
        st.get_best_server()

        if not quiet:
            print("Testing download speed...")
        download_total = len(st.config['sizes']['download']) * st.config['counts']['download']
        download_completed = 0

        def download_callback(i, request_count, start=False, end=False):
            nonlocal download_completed
            if end:
                download_completed += 1
            if not quiet:
                render_progress("Downloading:", download_completed, request_count)

        download = st.download(callback=download_callback) / 1_000_000
        if not quiet:
            sys.stdout.write("\n")
            print("Download complete.")

        if not quiet:
            print("Testing upload speed...")
        upload_total = st.config['upload_max']
        upload_completed = 0

        def upload_callback(i, request_count, start=False, end=False):
            nonlocal upload_completed
            if end:
                upload_completed += 1
            if not quiet:
                render_progress("Uploading:", upload_completed, request_count)

        upload = st.upload(callback=upload_callback) / 1_000_000
        if not quiet:
            sys.stdout.write("\n")
            print("Upload complete.")

        ping = st.results.ping
        if ping is not None and (not math.isfinite(float(ping)) or float(ping) < 0 or float(ping) > 60000):
            ping = None

        result = {
            "download_mbps": round(download, 2),
            "download_mBps": round(download / 8, 2),
            "upload_mbps": round(upload, 2),
            "upload_mBps": round(upload / 8, 2),
            "ping_ms": round(float(ping), 2) if ping is not None else None,
            "method": "speedtest",
        }
        return sanitize_speedtest_result(result)

    except Exception as e:
        return {"Error": str(e)}


def internet_speed(method='speedtest', quiet=True):
    if method == 'http-download':
        return http_download_speed(quiet=quiet)
    if method == 'speedtest':
        return speedtest_speed(quiet=quiet)
    return {"Error": f"Unknown speed test method: {method}"}


class Spinner:
    def __init__(self, message="[+] Running network diagnostics..."):
        self.message = message
        self.stop_running = False
        self.thread = None
        self.frames = ["|", "/", "-", "\\"]

    def _spin(self):
        idx = 0
        if sys.platform == 'win32':
            import os
            os.system('')
            try:
                if hasattr(sys.stdout, 'reconfigure'):
                    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            except Exception:
                pass

        while not self.stop_running:
            try:
                frame = self.frames[idx % len(self.frames)]
                sys.stdout.write(f"\r \033[96m[{frame}]\033[0m \033[1m{self.message}\033[0m   ")
                sys.stdout.flush()
            except Exception:
                frame = self.frames[idx % len(self.frames)]
                sys.stdout.write(f"\r[{frame}] {self.message}   ")
                sys.stdout.flush()
            time.sleep(0.08)
            idx += 1

        sys.stdout.write("\r" + " " * 90 + "\r")
        sys.stdout.flush()

    def start(self):
        self.stop_running = False
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.thread.start()

    def update(self, message):
        self.message = message

    def stop(self):
        self.stop_running = True
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=0.5)


def main():
    args = parse_args()

    cfg = load_config(args.config)
    logger = setup_logging(level=logging.INFO if args.verbose else logging.WARNING)

    timestamp = datetime.now()
    hostname = socket.gethostname()

    show_spinner = not args.verbose and not getattr(args, 'quiet', False)
    spinner = Spinner("[+] Collecting network diagnostics & speed test...")
    if show_spinner:
        spinner.start()

    try:
        public_ip = get_public_ip()
        private_ips = get_private_ips()
        location = get_location()

        # Run diagnostics in parallel
        results = {}
        is_quiet = not args.verbose
        with ThreadPoolExecutor(max_workers=6) as ex:
            futures = {}
            if cfg.get('speedtest', {}).get('run', True) and args.run_speedtest:
                method = args.speedtest_method or cfg.get('speedtest', {}).get('method', 'speedtest')
                futures[ex.submit(lambda m=method: internet_speed(method=m, quiet=is_quiet))] = 'speedtest'
            futures[ex.submit(lambda: get_public_ip())] = 'public_ip_refresh'
            futures[ex.submit(lambda: get_private_ips())] = 'private_ips_refresh'
            if cfg.get('routing_table', {}).get('run', True) and args.run_routing_table:
                futures[ex.submit(get_routing_table)] = 'routing_table'
            if cfg.get('ssid', {}).get('run', True) and args.run_ssid:
                futures[ex.submit(get_ssid)] = 'ssid'

            # Ping targets
            def ping_task():
                return ping_targets(cfg.get('ping_targets', []))

            futures[ex.submit(ping_task)] = 'pings'

            # Traceroute first ping target
            first_target = cfg.get('ping_targets', [None])[0]
            if first_target:
                futures[ex.submit(lambda t=first_target: run_traceroute(t))] = 'traceroute'

            total_tasks = len(futures)
            completed_tasks = 0

            for fut in as_completed(futures):
                completed_tasks += 1
                if show_spinner:
                    spinner.update(f"[+] Running network diagnostics & speed test... ({completed_tasks}/{total_tasks})")
                k = futures[fut]
                try:
                    results[k] = fut.result()
                except Exception as e:
                    results[k] = {'error': str(e)}

    finally:
        if show_spinner:
            spinner.stop()

    speed_results = results.get('speedtest', {})

    report_text = format_report(
        public_ip=public_ip,
        private_ips=private_ips,
        location=location,
        speed_results=speed_results,
        routing_table=results.get('routing_table', []),
        timestamp=timestamp,
        hostname=hostname,
        ssid=results.get('ssid'),
    )

    print(report_text)

    # Structured outputs
    out_json = {
        'timestamp': timestamp.isoformat(),
        'hostname': hostname,
        'public_ip': public_ip,
        'private_ips': private_ips,
        'ssid': results.get('ssid'),
        'location': location,
        'speed_test': speed_results,
        'routing_table': results.get('routing_table'),
        'pings': results.get('pings'),
        'traceroute': results.get('traceroute')
    }

    # Save outputs
    if getattr(args, 'save_report', True):
        try:
            text_path = args.save or cfg.get('outputs', {}).get('text', 'reports/network_report.txt')
            if args.save is None:
                text_path = timestamped_output_path(text_path, timestamp)
            save_report(report_text, text_path)

            # store in sqlite
            db_conn = init_db(cfg.get('db'))
            store_report_db(db_conn, timestamp, hostname, out_json)
            db_conn.close()

        except Exception as e:
            logger.exception('Error saving outputs: %s', e)
    else:
        logger.info('Report saving disabled via --no-save.')

    # Threshold check and alert
    thresholds = cfg.get('thresholds', {})
    alerts = []
    def _to_float(value, default):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    if speed_results:
        if speed_results.get('download_mbps') is not None and _to_float(speed_results.get('download_mbps', 0), 0) < thresholds.get('download_min_mbps', 0):
            alerts.append('Download below threshold')
        if speed_results.get('upload_mbps') is not None and _to_float(speed_results.get('upload_mbps', 0), 0) < thresholds.get('upload_min_mbps', 0):
            alerts.append('Upload below threshold')
        if speed_results.get('ping_ms') is not None and _to_float(speed_results.get('ping_ms', None), 9999) > thresholds.get('ping_max_ms', 9999):
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