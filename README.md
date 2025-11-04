# Setup on Two Raspberry Pis
## Pi #1 (Receiver - example IP: 192.168.1.100):
```bash
python3 network_benchmark.py --receiver --port 5000
```
## Pi #2 (Sender):
```bash
python3 network_benchmark.py --sender --host 192.168.1.100 --port 5000
```
