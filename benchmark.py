import socket
import time
import struct

class TCPRadioBenchmark:
    def __init__(self, host, port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)  # Disable Nagle
        self.sock.connect((host, port))
    
    def send_packet(self, msg_id, payload):
        # Simpler framing - TCP handles reliability
        timestamp = time.time()
        header = struct.pack('<Id', msg_id, timestamp)
        frame = header + payload
        
        # TCP handles the sending
        self.sock.sendall(frame)  # Blocks until all data buffered
        return timestamp
    
    def recv_packet(self):
        # Read fixed header first
        header = self._recv_exactly(12)  # 4 bytes ID + 8 bytes timestamp
        msg_id, send_time = struct.unpack('<Id', header)
        
        # Then read payload (you'd need to include payload length in header)
        payload = self._recv_exactly(payload_length)
        recv_time = time.time()
        
        return msg_id, payload, send_time, recv_time
    
    def _recv_exactly(self, n):
        """TCP stream handling - recv until we have exactly n bytes"""
        data = b''
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                raise ConnectionError("Socket closed")
            data += chunk
        return data