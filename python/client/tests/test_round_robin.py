from client.common.round_robin import round_robin


def test_round_robin():
    senders = round_robin(3)

    assert next(senders) == 0
    assert next(senders) == 1
    assert next(senders) == 2
    assert next(senders) == 0
    assert next(senders) == 1