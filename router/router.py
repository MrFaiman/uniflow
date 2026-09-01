import socket
import select
import random
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import ROUTER_IP, RX_HOST, RX_PORT_LIST, DisruptionProbabilities

def apply_bit_flip(data):
    if not data:
        return data
    data_bytearray = bytearray(data)
    random_byte_index = random.randint(0, len(data_bytearray) - 1)
    bit_to_flip = random.randint(0, 7)
    data_bytearray[random_byte_index] ^= (1 << bit_to_flip)
    return bytes(data_bytearray)

def start_router():
    listening_sockets = {}
    
    for port in RX_PORT_LIST:
        recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        recv_sock.bind((ROUTER_IP, port))
        listening_sockets[recv_sock] = port
        print(f"[Router] Listening for TX on {ROUTER_IP}:{port}...")
        
    send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    while True:
        readable, _, _ = select.select(list(listening_sockets.keys()), [], [])
        
        for sock in readable:
            data, addr = sock.recvfrom(65535)
            intended_port = listening_sockets[sock]
            
            if random.random() < DisruptionProbabilities.PACKET_LOSS:
                print(f"[X] Packet Loss: Dropped packet from {addr} to {intended_port}")
                continue
                
            if random.random() < DisruptionProbabilities.BIT_FLIP:
                data = apply_bit_flip(data)
                
            target_port = intended_port
            
            if random.random() < DisruptionProbabilities.MISROUTING:
                wrong_ports = [p for p in RX_PORT_LIST if p != intended_port]
                target_port = random.choice(wrong_ports)
                print(f"[?] Misrouting: Redirecting from {intended_port} to {target_port}")
                    
            send_sock.sendto(data, (socket.gethostbyname(RX_HOST), target_port))

if __name__ == "__main__":
    start_router()