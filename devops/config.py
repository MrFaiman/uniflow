from enum import IntEnum

ROUTER_IP = '0.0.0.0'
ROUTER_PORT = 5000
ROUTER_HOST = 'router'


RX_HOST = 'rx_machine'

MAX_UDP_PACKET_SIZE = 65535

class RXPorts(IntEnum):
    PORT_1 = 6001
    PORT_2 = 6002
    PORT_3 = 6003

RX_PORT_LIST = [RXPorts.PORT_1.value, RXPorts.PORT_2.value, RXPorts.PORT_3.value]

class DisruptionProbabilities:
    PACKET_LOSS = 0.15
    BIT_FLIP = 0.15
    MISROUTING = 0.15