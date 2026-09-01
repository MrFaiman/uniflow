import socket
import time
import random
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from devops.config import ROUTER_HOST, RX_PORT_LIST

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
counter = 1

while True:
    target_port = random.choice(RX_PORT_LIST)
    message = f"Packet {counter} originally intended for port {target_port}".encode('utf-8')
    
    print(f"[TX] Sending to Router on port {target_port} | Data: {message.decode('utf-8')}")
    sock.sendto(message, (socket.gethostbyname(ROUTER_HOST), target_port))
    
    counter += 1
    time.sleep(1)