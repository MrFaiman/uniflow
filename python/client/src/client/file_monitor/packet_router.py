SMALL_FILE_LIMIT = 10 * 1024 * 1024
NUMBER_OF_SENDERS = 3


def route_packets(packets, file_size, small_file_sender=0):
    if file_size < SMALL_FILE_LIMIT:
        for packet in packets:
            yield small_file_sender, packet

        return

    for index, packet in enumerate(packets):
        sender = index % NUMBER_OF_SENDERS
        yield sender, packet