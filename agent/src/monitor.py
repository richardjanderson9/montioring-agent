import os
import json
import time
import logging
from datetime import datetime, timezone
import urllib.request
import urllib.error

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# Set to match the Dockerfile COPY destination
CONFIG_PATH = "/opt/sysmonitor/conf/config.json"

def load_config():
    try:
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Config load failed: {e}")
        return {
            "server_url": "http://127.0.0.1:5000/api/metrics",
            "api_token": "your_secure_pre_shared_key",
            "collection_interval_seconds": 10,
            "local_buffer_path": "/var/log/sysmonitor/buffer.jsonl"
        }

def get_cpu_load():
    try:
        with open('/host/proc/loadavg', 'r') as f:
            load = f.read().split()
            return {"load_average_1m": float(load[0]), "load_average_5m": float(load[1]), "load_average_15m": float(load[2])}
    except Exception:
        return {"load_average_1m": 0.0, "load_average_5m": 0.0, "load_average_15m": 0.0}

def get_memory_usage():
    try:
        meminfo = {}
        with open('/host/proc/meminfo', 'r') as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    meminfo[parts[0].rstrip(':')] = int(parts[1]) * 1024
        
        total = meminfo.get('MemTotal', 0)
        available = meminfo.get('MemFree', 0) + meminfo.get('Buffers', 0) + meminfo.get('Cached', 0)
        used = total - available
        usage_percent = round((used / total) * 100, 2) if total > 0 else 0.0
        return {"total_bytes": total, "used_bytes": used, "free_bytes": available, "usage_percent": usage_percent}
    except Exception:
        return {}

def get_storage_usage():
    try:
        st = os.statvfs('/rootfs')
        free = st.f_bavail * st.f_frsize
        total = st.f_blocks * st.f_frsize
        used = total - free
        return {"mount_point": "/", "total_bytes": total, "used_bytes": used, "free_bytes": free, "usage_percent": round((used / total) * 100, 2) if total > 0 else 0.0}
    except Exception:
        return {}

def get_network_bytes():
    rx_bytes, tx_bytes = 0, 0
    try:
        with open('/host/proc/net/dev', 'r') as f:
            for line in f.readlines()[2:]:
                data = line.split()
                if len(data) > 9 and not data[0].startswith('lo'):
                    rx_bytes += int(data[1])
                    tx_bytes += int(data[9])
    except Exception:
        pass
    return rx_bytes, tx_bytes

def append_to_buffer(buffer_path, data):
    try:
        os.makedirs(os.path.dirname(buffer_path), exist_ok=True)
        with open(buffer_path, 'a') as f:
            f.write(json.dumps(data) + '\n')
    except Exception as e:
        logging.error(f"Buffer write error: {e}")

def send_buffer_to_server(buffer_path, server_url, token):
    if not os.path.exists(buffer_path) or os.path.getsize(buffer_path) == 0:
        return

    try:
        with open(buffer_path, 'r') as f:
            lines = f.readlines()
        
        payload_data = [json.loads(line.strip()) for line in lines if line.strip()]
        if not payload_data:
            return

        req = urllib.request.Request(server_url, data=json.dumps(payload_data).encode('utf-8'), method='POST')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Authorization', f'Bearer {token}')

        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status in [200, 201]:
                logging.info(f"Transmitted {len(payload_data)} records.")
                open(buffer_path, 'w').close()
    except Exception as e:
        logging.warning(f"Network transport delayed: {e}")

def main():
    logging.info("Starting Containerized Telemetry Agent...")
    config = load_config()
    last_rx, last_tx = get_network_bytes()
    last_time = time.time()

    while True:
        try:
            time.sleep(config.get("collection_interval_seconds", 10))
            current_rx, current_tx = get_network_bytes()
            current_time = time.time()
            td = current_time - last_time

            metrics = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "host": {"hostname": os.environ.get("HOSTNAME", "unknown-host")},
                "cpu": get_cpu_load(),
                "memory": get_memory_usage(),
                "storage": get_storage_usage(),
                "network": {
                    "bytes_sent_per_sec": int((current_tx - last_tx) / td) if td > 0 else 0,
                    "bytes_recv_per_sec": int((current_rx - last_rx) / td) if td > 0 else 0
                }
            }

            last_rx, last_tx, last_time = current_rx, current_tx, current_time
            append_to_buffer(config.get("local_buffer_path"), metrics)
            send_buffer_to_server(config.get("local_buffer_path"), config.get("server_url"), config.get("api_token"))
            
        except Exception as e:
            logging.error(f"Loop failure: {e}")

if __name__ == "__main__":
    main()