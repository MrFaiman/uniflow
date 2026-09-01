from client.common.round_robin import RoundRobin


def test_round_robin():
    round_robin = RoundRobin(3)

    assert round_robin.next_sender() == 0
    assert round_robin.next_sender() == 1
    assert round_robin.next_sender() == 2
    assert round_robin.next_sender() == 0
    assert round_robin.next_sender() == 1