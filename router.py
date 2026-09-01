import socket
import random
from config import ROUTER_IP, ROUTER_PORT, RX_HOST, RX_PORT_LIST,MAX_UDP_PACKET_SIZE, DisruptionProbabilities

def apply_bit_flip(data):
    if not data:
        return data
    data_bytearray = bytearray(data)
    random_byte_index = random.randint(0, len(data_bytearray) - 1)
    bit_to_flip = random.randint(0, 7)
    data_bytearray[random_byte_index] ^= (1 << bit_to_flip)
    return bytes(data_bytearray)

def start_router():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((ROUTER_IP, ROUTER_PORT))
    
    print(f"[Router] Listening on {ROUTER_IP}:{ROUTER_PORT}...")
    
    while True:
        data, addr = sock.recvfrom(MAX_UDP_PACKET_SIZE)
        
        if random.random() < DisruptionProbabilities.PACKET_LOSS:
            continue
            
        if random.random() < DisruptionProbabilities.BIT_FLIP:
            data = apply_bit_flip(data)
            
        target_port = random.choice(RX_PORT_LIST)
        
        if random.random() < DisruptionProbabilities.MISROUTING:
            wrong_ports = [p for p in RX_PORT_LIST if p != target_port]
            target_port = random.choice(wrong_ports)
                
        sock.sendto(data, (socket.gethostbyname(RX_HOST), target_port))

if __name__ == "__main__":
    start_router()