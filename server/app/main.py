import os
from fastapi import FastAPI, Header, HTTPException, status, Response
from typing import List, Dict, Any

app = FastAPI(title="SysMonitor Telemetry Receiver")
EXPECTED_TOKEN = os.getenv("AGENT_TOKEN", "your_secure_pre_shared_key")

@app.post("/api/metrics")
async def receive_metrics(payload: List[Dict[Any, Any]], authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header")
    
    try:
        token_type, token_value = authorization.split(" ")
        if token_type.lower() != "bearer" or token_value != EXPECTED_TOKEN:
            raise ValueError()
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token")

    print(f"[*] Batch received: {len(payload)} events.")
    for metric in payload:
        hostname = metric.get("host", {}).get("hostname", "unknown")
        print(f"    -> Host: {hostname} | Time: {metric.get('timestamp')} | CPU Load (1m): {metric.get('cpu', {}).get('load_average_1m')}")

    return Response(status_code=status.HTTP_200_OK)