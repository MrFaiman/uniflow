import socket
import select
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from devops.config import RX_PORT_LIST

listening_sockets = {}

for port in RX_PORT_LIST:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('0.0.0.0', port))
    listening_sockets[sock] = port
    print(f"[RX] Receiver Mock listening on port {port}...")

while True:
    readable, _, _ = select.select(list(listening_sockets.keys()), [], [])
    
    for sock in readable:
        data, addr = sock.recvfrom(65535)
        receiving_port = listening_sockets[sock]
        
        print(f"[RX - Port {receiving_port}] Received data: {data} (from Router at {addr})")