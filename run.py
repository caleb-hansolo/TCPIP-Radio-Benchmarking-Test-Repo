import scanner

if __name__ == "__main__":
    devices = scanner.scan_network_socket("172.20.10.0/28", 5000) # test for phone hotspot
    print(devices)