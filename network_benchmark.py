"""
Pi-to-Pi Network Benchmarking System
For testing over WiFi/Ethernet without physical radios

This simplified version is perfect for:
- Testing your benchmarking logic before deploying to radios
- Measuring WiFi/Ethernet network performance
- Developing on Raspberry Pis in a lab environment
"""

import socket
import struct
import time
import threading
import json
from dataclasses import dataclass, asdict
from typing import Optional, Tuple, List, Dict
from enum import Enum
import argparse

###############################################################################
# Configuration
###############################################################################

class TransportMode(Enum):
    TCP = "tcp"
    UDP = "udp"

@dataclass
class BenchmarkConfig:
    """Configuration for Pi-to-Pi benchmarking"""
    # Network settings
    mode: TransportMode = TransportMode.TCP
    host: str = "192.168.1.100"  # Remote Pi IP address
    port: int = 5000
    
    # Test parameters
    payload_size: int = 100
    max_packets: int = 1000
    send_delay: float = 0.01  # seconds between packets
    timeout: float = 5.0
    
    # Role
    is_sender: bool = True  # True = send packets, False = receive only
    is_receiver: bool = True  # Can be both sender and receiver
    
    # Logging
    print_logs: bool = True
    log_frequency: int = 10  # Print every N packets
    save_results: bool = True
    results_file: str = "benchmark_results.json"

@dataclass
class PacketMetrics:
    """Metrics for a single packet"""
    msg_id: int
    send_time: float
    recv_time: float
    payload_size: int
    latency_ms: float
    
    def to_dict(self):
        return asdict(self)

###############################################################################
# Network Benchmark Class
###############################################################################

class NetworkBenchmark:
    """Simplified benchmarking for Pi-to-Pi over WiFi/Ethernet"""
    
    def __init__(self, config: BenchmarkConfig):
        self.config = config
        self.running = False
        
        # Sockets
        self.sock: Optional[socket.socket] = None
        self.server_sock: Optional[socket.socket] = None  # For TCP server
        self.client_addr: Optional[Tuple] = None  # For UDP
        
        # Tracking
        self.sent_packets: Dict[int, float] = {}  # msg_id -> send_time
        self.metrics: List[PacketMetrics] = []
        
        # Threads
        self.sender_thread: Optional[threading.Thread] = None
        self.receiver_thread: Optional[threading.Thread] = None
        
        # Thread safety
        self._lock = threading.Lock()
    
    ###########################################################################
    # Connection Management
    ###########################################################################
    
    def start(self):
        """Start the benchmark"""
        print(f"\n{'='*70}")
        print(f"Pi-to-Pi Network Benchmark")
        print(f"Mode: {self.config.mode.value.upper()}")
        print(f"{'='*70}\n")
        
        self.running = True
        
        # Setup network connection
        if self.config.mode == TransportMode.TCP:
            self._setup_tcp()
        else:
            self._setup_udp()
        
        # Start threads based on role
        if self.config.is_receiver:
            self.receiver_thread = threading.Thread(target=self._receiver_loop, daemon=True)
            self.receiver_thread.start()
            print(f"[Receiver] Started listening on port {self.config.port}")
        
        if self.config.is_sender:
            time.sleep(0.5)  # Let receiver start first
            self.sender_thread = threading.Thread(target=self._sender_loop, daemon=True)
            self.sender_thread.start()
            print(f"[Sender] Started sending to {self.config.host}:{self.config.port}")
    
    def stop(self):
        """Stop the benchmark"""
        print(f"\n{'='*70}")
        print(f"Stopping benchmark...")
        print(f"{'='*70}\n")
        
        self.running = False
        
        # Wait for threads
        if self.sender_thread:
            self.sender_thread.join(timeout=5)
        if self.receiver_thread:
            self.receiver_thread.join(timeout=5)
        
        # Close sockets
        if self.sock:
            try:
                if self.config.mode == TransportMode.TCP:
                    self.sock.shutdown(socket.SHUT_RDWR)
            except:
                pass
            self.sock.close()
        
        if self.server_sock:
            self.server_sock.close()
        
        # Process and display results
        self._display_results()
        
        # Save results if configured
        if self.config.save_results:
            self._save_results()
    
    def _setup_tcp(self):
        """Setup TCP connection"""
        if self.config.is_receiver:
            # Create server socket
            self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_sock.bind(('0.0.0.0', self.config.port))
            self.server_sock.listen(1)
            self.server_sock.settimeout(1.0)  # Non-blocking accept
            print(f"[TCP] Listening on port {self.config.port}")
        
        if self.config.is_sender:
            # Create client socket
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            
            # Try to connect (with retries for when other Pi isn't ready yet)
            max_retries = 10
            for attempt in range(max_retries):
                try:
                    self.sock.connect((self.config.host, self.config.port))
                    print(f"[TCP] Connected to {self.config.host}:{self.config.port}")
                    break
                except ConnectionRefusedError:
                    if attempt < max_retries - 1:
                        print(f"[TCP] Connection refused, retrying ({attempt+1}/{max_retries})...")
                        time.sleep(1)
                    else:
                        raise
    
    def _setup_udp(self):
        """Setup UDP socket"""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        if self.config.is_receiver:
            self.sock.bind(('0.0.0.0', self.config.port))
            print(f"[UDP] Listening on port {self.config.port}")
        else:
            # Sender doesn't need to bind for UDP
            print(f"[UDP] Ready to send to {self.config.host}:{self.config.port}")
        
        self.sock.settimeout(1.0)
    
    ###########################################################################
    # Packet Operations
    ###########################################################################
    
    def _create_packet(self, msg_id: int) -> bytes:
        """Create a packet with header + payload"""
        send_time = time.time()
        
        # Create payload
        payload = b'a' * self.config.payload_size
        
        # Header: MSG_ID (4) + TIMESTAMP (8) + PAYLOAD_LENGTH (4)
        header = struct.pack('<Idi', msg_id, send_time, len(payload))
        
        return header + payload, send_time
    
    def _parse_packet(self, data: bytes) -> Tuple[int, float, bytes]:
        """Parse received packet"""
        if len(data) < 16:
            raise ValueError("Packet too short")
        
        # Parse header
        msg_id, send_time, payload_len = struct.unpack('<Idi', data[:16])
        payload = data[16:16+payload_len]
        
        return msg_id, send_time, payload
    
    ###########################################################################
    # Sender Loop
    ###########################################################################
    
    def _sender_loop(self):
        """Send packets at configured rate"""
        msg_id = 1
        packets_sent = 0
        
        print(f"[Sender] Sending {self.config.max_packets} packets...")
        print(f"[Sender] Payload size: {self.config.payload_size} bytes")
        print(f"[Sender] Send delay: {self.config.send_delay} seconds\n")
        
        start_time = time.time()
        
        while self.running and msg_id <= self.config.max_packets:
            try:
                # Create packet
                packet, send_time = self._create_packet(msg_id)
                
                # Send packet
                if self.config.mode == TransportMode.TCP:
                    self.sock.sendall(packet)
                else:  # UDP
                    self.sock.sendto(packet, (self.config.host, self.config.port))
                
                # Track sent packet
                with self._lock:
                    self.sent_packets[msg_id] = send_time
                
                packets_sent += 1
                
                # Print progress
                if self.config.print_logs and msg_id % self.config.log_frequency == 0:
                    elapsed = time.time() - start_time
                    rate = packets_sent / elapsed if elapsed > 0 else 0
                    print(f"[Sender] Sent {msg_id}/{self.config.max_packets} packets "
                          f"({rate:.1f} pkt/sec)")
                
                msg_id += 1
                time.sleep(self.config.send_delay)
                
            except Exception as e:
                print(f"[Sender] Error sending packet {msg_id}: {e}")
                break
        
        print(f"\n[Sender] Finished! Sent {packets_sent} packets\n")
    
    ###########################################################################
    # Receiver Loop
    ###########################################################################
    
    def _receiver_loop(self):
        """Receive and process packets"""
        print(f"[Receiver] Listening for packets...\n")
        
        # For TCP server, accept connection first
        if self.config.mode == TransportMode.TCP and self.config.is_receiver:
            print(f"[Receiver] Waiting for connection...")
            while self.running:
                try:
                    self.sock, client_addr = self.server_sock.accept()
                    self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    print(f"[Receiver] Accepted connection from {client_addr}\n")
                    break
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"[Receiver] Accept error: {e}")
                    return
        
        packets_received = 0
        consecutive_timeouts = 0
        max_timeouts = 20
        
        while self.running:
            try:
                # Receive data
                if self.config.mode == TransportMode.TCP:
                    data = self._recv_tcp_packet()
                else:  # UDP
                    data, self.client_addr = self.sock.recvfrom(65535)
                
                if not data:
                    consecutive_timeouts += 1
                    if consecutive_timeouts >= max_timeouts:
                        print(f"[Receiver] No data for {max_timeouts} attempts, stopping...")
                        break
                    continue
                
                consecutive_timeouts = 0
                recv_time = time.time()
                
                # Parse packet
                msg_id, send_time, payload = self._parse_packet(data)
                
                # Calculate latency
                latency_ms = (recv_time - send_time) * 1000
                
                # Store metrics
                metric = PacketMetrics(
                    msg_id=msg_id,
                    send_time=send_time,
                    recv_time=recv_time,
                    payload_size=len(payload),
                    latency_ms=latency_ms
                )
                
                with self._lock:
                    self.metrics.append(metric)
                
                packets_received += 1
                
                # Print progress
                if self.config.print_logs and msg_id % self.config.log_frequency == 0:
                    print(f"[Receiver] Received packet {msg_id}, "
                          f"Latency: {latency_ms:.2f} ms")
                
            except socket.timeout:
                consecutive_timeouts += 1
                if consecutive_timeouts >= max_timeouts:
                    print(f"[Receiver] Timeout limit reached, stopping...")
                    break
            except Exception as e:
                if self.running:  # Only print error if we're still supposed to be running
                    print(f"[Receiver] Error: {e}")
                break
        
        print(f"\n[Receiver] Finished! Received {packets_received} packets\n")
    
    def _recv_tcp_packet(self) -> bytes:
        """Receive a complete TCP packet (header + payload)"""
        # First, read the header (16 bytes)
        header = self._recv_exactly(16)
        if not header:
            return b''
        
        # Parse payload length from header
        _, _, payload_len = struct.unpack('<Idi', header)
        
        # Read the payload
        payload = self._recv_exactly(payload_len)
        
        return header + payload
    
    def _recv_exactly(self, n: int) -> bytes:
        """Receive exactly n bytes from TCP socket"""
        data = b''
        while len(data) < n:
            try:
                chunk = self.sock.recv(n - len(data))
                if not chunk:
                    return b''  # Connection closed
                data += chunk
            except socket.timeout:
                return b''
        return data
    
    ###########################################################################
    # Results Processing
    ###########################################################################
    
    def _display_results(self):
        """Display benchmark results"""
        if not self.metrics and not self.sent_packets:
            print("No metrics collected!")
            return
        
        packets_sent = len(self.sent_packets)
        packets_received = len(self.metrics)
        
        print(f"\n{'='*70}")
        print(f"BENCHMARK RESULTS")
        print(f"{'='*70}")
        print(f"Mode:             {self.config.mode.value.upper()}")
        print(f"Payload Size:     {self.config.payload_size} bytes")
        print(f"Send Delay:       {self.config.send_delay} seconds")
        print(f"\nPackets Sent:     {packets_sent}")
        print(f"Packets Received: {packets_received}")
        
        if packets_sent > 0:
            packet_loss = ((packets_sent - packets_received) / packets_sent * 100)
            print(f"Packet Loss:      {packet_loss:.2f}%")
        
        if self.metrics:
            # Calculate latency statistics
            latencies = [m.latency_ms for m in self.metrics]
            latencies.sort()
            
            print(f"\n--- Latency Statistics ---")
            print(f"Min:              {min(latencies):.2f} ms")
            print(f"Max:              {max(latencies):.2f} ms")
            print(f"Average:          {sum(latencies)/len(latencies):.2f} ms")
            print(f"Median:           {latencies[len(latencies)//2]:.2f} ms")
            print(f"95th percentile:  {latencies[int(len(latencies)*0.95)]:.2f} ms")
            print(f"99th percentile:  {latencies[int(len(latencies)*0.99)]:.2f} ms")
            
            # Calculate throughput
            if len(self.metrics) > 1:
                time_span = max(m.recv_time for m in self.metrics) - min(m.recv_time for m in self.metrics)
                total_bytes = sum(m.payload_size for m in self.metrics)
                
                if time_span > 0:
                    throughput_bps = (total_bytes * 8) / time_span
                    print(f"\n--- Throughput Statistics ---")
                    print(f"Total Bytes:      {total_bytes}")
                    print(f"Time Span:        {time_span:.2f} seconds")
                    print(f"Throughput:       {throughput_bps/1000:.2f} kbps")
                    print(f"Throughput:       {throughput_bps/1_000_000:.2f} Mbps")
        
        print(f"{'='*70}\n")
    
    def _save_results(self):
        """Save results to JSON file"""
        results = {
            'config': {
                'mode': self.config.mode.value,
                'host': self.config.host,
                'port': self.config.port,
                'payload_size': self.config.payload_size,
                'max_packets': self.config.max_packets,
                'send_delay': self.config.send_delay
            },
            'summary': {
                'packets_sent': len(self.sent_packets),
                'packets_received': len(self.metrics),
                'packet_loss_pct': ((len(self.sent_packets) - len(self.metrics)) / 
                                   max(len(self.sent_packets), 1) * 100) if self.sent_packets else 0
            },
            'metrics': [m.to_dict() for m in self.metrics]
        }
        
        # Calculate stats if we have metrics
        if self.metrics:
            latencies = [m.latency_ms for m in self.metrics]
            latencies.sort()
            
            results['summary']['latency'] = {
                'min_ms': min(latencies),
                'max_ms': max(latencies),
                'avg_ms': sum(latencies) / len(latencies),
                'median_ms': latencies[len(latencies)//2],
                'p95_ms': latencies[int(len(latencies)*0.95)],
                'p99_ms': latencies[int(len(latencies)*0.99)]
            }
            
            if len(self.metrics) > 1:
                time_span = max(m.recv_time for m in self.metrics) - min(m.recv_time for m in self.metrics)
                total_bytes = sum(m.payload_size for m in self.metrics)
                if time_span > 0:
                    results['summary']['throughput_bps'] = (total_bytes * 8) / time_span
        
        with open(self.config.results_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"Results saved to: {self.config.results_file}")

###############################################################################
# Command Line Interface
###############################################################################

def main():
    parser = argparse.ArgumentParser(description='Pi-to-Pi Network Benchmark')
    
    # Network settings
    parser.add_argument('--mode', choices=['tcp', 'udp'], default='tcp',
                       help='Transport protocol (default: tcp)')
    parser.add_argument('--host', default='192.168.1.100',
                       help='Remote Pi IP address (default: 192.168.1.100)')
    parser.add_argument('--port', type=int, default=5000,
                       help='Port number (default: 5000)')
    
    # Role
    parser.add_argument('--sender', action='store_true',
                       help='Act as sender (sends packets)')
    parser.add_argument('--receiver', action='store_true',
                       help='Act as receiver (receives packets)')
    parser.add_argument('--both', action='store_true',
                       help='Act as both sender and receiver')
    
    # Test parameters
    parser.add_argument('--payload-size', type=int, default=100,
                       help='Payload size in bytes (default: 100)')
    parser.add_argument('--max-packets', type=int, default=1000,
                       help='Maximum packets to send (default: 1000)')
    parser.add_argument('--send-delay', type=float, default=0.01,
                       help='Delay between packets in seconds (default: 0.01)')
    parser.add_argument('--duration', type=int, default=None,
                       help='Run for specified seconds (overrides max-packets)')
    
    # Logging
    parser.add_argument('--quiet', action='store_true',
                       help='Disable console logging')
    parser.add_argument('--log-frequency', type=int, default=10,
                       help='Print log every N packets (default: 10)')
    parser.add_argument('--output', default='benchmark_results.json',
                       help='Output file for results (default: benchmark_results.json)')
    
    args = parser.parse_args()
    
    # Determine role
    if args.both:
        is_sender = True
        is_receiver = True
    else:
        is_sender = args.sender
        is_receiver = args.receiver
        
        # Default to both if neither specified
        if not is_sender and not is_receiver:
            is_sender = True
            is_receiver = True
            print("No role specified, defaulting to both sender and receiver")
    
    # Create configuration
    config = BenchmarkConfig(
        mode=TransportMode.TCP if args.mode == 'tcp' else TransportMode.UDP,
        host=args.host,
        port=args.port,
        payload_size=args.payload_size,
        max_packets=args.max_packets,
        send_delay=args.send_delay,
        is_sender=is_sender,
        is_receiver=is_receiver,
        print_logs=not args.quiet,
        log_frequency=args.log_frequency,
        results_file=args.output
    )
    
    # Create and start benchmark
    benchmark = NetworkBenchmark(config)
    
    try:
        benchmark.start()
        
        # Run for specified duration or until max packets
        if args.duration:
            print(f"\nRunning for {args.duration} seconds...")
            time.sleep(args.duration)
        else:
            # Wait for sender to finish
            if benchmark.sender_thread:
                benchmark.sender_thread.join()
            # Give receiver a bit more time to catch up
            time.sleep(2)
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user (Ctrl+C)")
    finally:
        benchmark.stop()

if __name__ == "__main__":
    main()