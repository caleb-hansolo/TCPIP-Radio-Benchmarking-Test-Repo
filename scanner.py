import socket
import ipaddress
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

def check_host(ip, port=5000, timeout=0.5):
    """Check if a host has the specified port open."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((str(ip), port))
        sock.close()
        
        if result == 0:
            return str(ip)
    except:
        pass
    return None

def scan_network_socket(network="172.20.10.0/28", port=5000, max_workers=100):
    """
    Fast network scanner using pure Python.
    Scans entire subnet in parallel.
    """
    print(f"Scanning {network} for devices with port {port} open...")
    
    network_obj = ipaddress.ip_network(network, strict=False)
    hosts = list(network_obj.hosts())
    
    found_devices = []
    completed = 0
    total = len(hosts)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all scan jobs
        future_to_ip = {
            executor.submit(check_host, ip, port): ip 
            for ip in hosts
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_ip):
            completed += 1
            if completed % 50 == 0:
                print(f"Progress: {completed}/{total} hosts scanned...")
            
            result = future.result()
            if result:
                found_devices.append(result)
                print(f"  ✓ Found device at {result}")
    
    return found_devices