Network Information & Automation Script

This repository contains an enhanced `Script.py` for gathering network information, running diagnostics (speedtest, ping, traceroute), and exporting reports.

Quick start

1. Create a virtualenv and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Run the script:

```powershell
python Script.py --save
```

Features

- Public/private IP collection
- Geo IP lookup
- Speedtest
- Ping targets
- Traceroute
- JSON/CSV export
- SQLite storage
- Threshold checks and webhook alerts

Configuration

Add an optional `config.yaml` file to override defaults (speedtest, ping targets, thresholds, webhook URL, output paths).
