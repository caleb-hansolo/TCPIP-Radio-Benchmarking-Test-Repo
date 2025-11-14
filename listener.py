import socket

# if using ufw, must run: sudo ufw allow 5000/tcp
# afterwards, close port with: sudo ufw delete allow 5000/tcp

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.bind(("0.0.0.0", 5000))
s.listen(1)
print("Listening on port 5000...")
while True:
    conn, addr = s.accept()
    print("Connection from", addr)
    conn.close()
