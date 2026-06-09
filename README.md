# Real Time Distributed Clock Sync System

A lightweight Python project that synchronizes system clocks across multiple machines in a distributed network. It ensures consistent timestamps for logging, data collection, and coordinated tasks.

## Features

- **Peer-to-peer synchronization** using UDP broadcasts.
- **Configurable sync interval** and tolerance.
- **Cross‑platform** support (Windows, Linux, macOS).
- Simple CLI for quick setup and monitoring.

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/distributed-clock-sync.git
cd distributed-clock-sync

# (Optional) Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows use `venv\Scripts\activate`

# Install dependencies
pip install -r requirements.txt
```

## Usage

```bash
# Start the sync service on a machine
python sync.py --host 0.0.0.0 --port 12345

# On other machines, point to the host
python sync.py --host <master_ip> --port 12345
```

- `--interval` – sync interval in seconds (default: 5).
- `--tolerance` – maximum allowed drift in milliseconds.

## Configuration

Edit `config.yaml` to adjust default settings:

```yaml
interval: 5
tolerance: 50
log_file: sync.log
```

## Contributing

Contributions are welcome! Please fork the repository and submit a pull request. Follow the standard GitHub workflow:

1. Create a feature branch.
2. Write tests for new functionality.
3. Ensure all existing tests pass (`pytest`).
4. Update the documentation as needed.

## License

Distributed under the MIT License. See `LICENSE` for more information.

---

* Created ❤️ with @imrannaseer123 *
