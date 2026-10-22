import socket
import time

deadline = time.monotonic() + 120
while time.monotonic() < deadline:
    try:
        with socket.create_connection(('127.0.0.1', 55917), timeout=2):
            time.sleep(8)
            break
    except OSError:
        time.sleep(1)
else:
    raise SystemExit('Official Mondcraft survival server did not open port 55917 within 120 seconds')