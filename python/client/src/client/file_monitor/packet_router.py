SMALL_FILE_LIMIT = 10 * 1024 * 1024


def route_packets(
    packets,
    file_size: int,
    small_file_sender: int = 0,
    number_of_senders: int = 3,
):
    if file_size < SMALL_FILE_LIMIT:
        for packet in packets:
            yield small_file_sender, packet

        return

    for index, packet in enumerate(packets):
        sender = index % number_of_senders
        yield sender, packet