#!/usr/bin/env python3
"""
Minimal rosbridge WebSocket client - pure Python stdlib, no external deps.
Runs inside the AGL QEMU VM (which only has python3) to prove the path:
  CARLA -> ROS2 /carla/odom -> rosbridge_websocket :9090 -> THIS client.

The server host is reachable from the QEMU slirp guest at 10.0.2.2.

Usage (inside AGL):
  python3 agl_ws_test.py                 # defaults: 10.0.2.2:9090, /carla/odom
  python3 agl_ws_test.py 10.0.2.2 9090 /carla/odom
"""
import socket, os, base64, struct, json, sys

def ws_connect(host, port):
    s = socket.create_connection((host, port), timeout=10)
    key = base64.b64encode(os.urandom(16)).decode()
    req = (
        "GET / HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    )
    s.sendall(req.encode())
    # read HTTP response headers
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = s.recv(1)
        if not chunk:
            raise RuntimeError("connection closed during handshake")
        buf += chunk
    if b"101" not in buf.split(b"\r\n", 1)[0]:
        raise RuntimeError("handshake failed:\n" + buf.decode(errors="replace"))
    return s

def ws_send_text(s, text):
    payload = text.encode()
    header = bytearray([0x81])  # FIN + text opcode
    n = len(payload)
    mask_bit = 0x80            # client frames MUST be masked
    if n < 126:
        header.append(mask_bit | n)
    elif n < 65536:
        header.append(mask_bit | 126); header += struct.pack(">H", n)
    else:
        header.append(mask_bit | 127); header += struct.pack(">Q", n)
    mask = os.urandom(4)
    header += mask
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    s.sendall(bytes(header) + masked)

def _recv_exactly(s, n):
    data = b""
    while len(data) < n:
        chunk = s.recv(n - len(data))
        if not chunk:
            raise RuntimeError("connection closed")
        data += chunk
    return data

def ws_recv_text(s):
    """Return one text-message payload (server->client frames are unmasked)."""
    while True:
        b0, b1 = _recv_exactly(s, 2)
        opcode = b0 & 0x0F
        masked = b1 & 0x80
        ln = b1 & 0x7F
        if ln == 126:
            ln = struct.unpack(">H", _recv_exactly(s, 2))[0]
        elif ln == 127:
            ln = struct.unpack(">Q", _recv_exactly(s, 8))[0]
        mask = _recv_exactly(s, 4) if masked else None
        payload = _recv_exactly(s, ln)
        if mask:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        if opcode == 0x8:      # close
            raise RuntimeError("server closed connection")
        if opcode in (0x1, 0x2):
            return payload.decode(errors="replace")
        # ignore ping/pong/continuation for this simple test

def main():
    host = sys.argv[1] if len(sys.argv) > 1 else "10.0.2.2"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 9090
    topic = sys.argv[3] if len(sys.argv) > 3 else "/carla/odom"
    print(f"[agl] connecting to ws://{host}:{port}  topic={topic}")
    s = ws_connect(host, port)
    print("[agl] websocket handshake OK, subscribing...")
    ws_send_text(s, json.dumps({"op": "subscribe", "topic": topic}))
    count = 0
    while True:
        msg = ws_recv_text(s)
        try:
            d = json.loads(msg)
        except ValueError:
            continue
        if d.get("op") != "publish":
            print("[agl] <-", msg[:200]); continue
        m = d.get("msg", {})
        pos = m.get("pose", {}).get("pose", {}).get("position", {})
        count += 1
        print(f"[agl] #{count} {topic}  x={pos.get('x'):.2f} "
              f"y={pos.get('y'):.2f} z={pos.get('z'):.2f}" if pos else f"[agl] #{count} {msg[:200]}")

if __name__ == "__main__":
    main()
