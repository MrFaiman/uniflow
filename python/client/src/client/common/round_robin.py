from collections.abc import Iterator


def round_robin(number_of_senders: int) -> Iterator[int]:
    current_sender = 0

    while True:
        yield current_sender
        current_sender = (current_sender + 1) % number_of_senders
