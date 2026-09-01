class RoundRobin:
    def __init__(self, number_of_senders: int):
        self.number_of_senders = number_of_senders
        self.current_sender = 0

    def next_sender(self) -> int:
        sender = self.current_sender
        self.current_sender = (
            self.current_sender + 1
        ) % self.number_of_senders

        return sender