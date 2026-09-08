from collections.abc import Iterable, Iterator

from client.common.transfer_limits import SMALL_FILE_LIMIT


def route_packets[T](
    packets: Iterable[T],
    file_size: int,
    small_file_sender: int = 0,
    number_of_senders: int = 3,
) -> Iterator[tuple[int, T]]:
    if file_size < SMALL_FILE_LIMIT:
        for packet in packets:
            yield small_file_sender, packet
        return

    for index, packet in enumerate(packets):
        yield index % number_of_senders, packet
