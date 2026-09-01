from client.file_monitor.packet_router import route_packets


def test_small_file_uses_one_sender():
    packets = ["p0", "p1", "p2", "p3"]

    routed = list(
        route_packets(
            packets,
            file_size=1000,
            small_file_sender=1,
        )
    )

    assert routed == [
        (1, "p0"),
        (1, "p1"),
        (1, "p2"),
        (1, "p3"),
    ]


def test_large_file_uses_all_senders():
    packets = ["p0", "p1", "p2", "p3", "p4", "p5"]

    routed = list(
        route_packets(
            packets,
            file_size=10 * 1024 * 1024,
        )
    )

    assert routed == [
        (0, "p0"),
        (1, "p1"),
        (2, "p2"),
        (0, "p3"),
        (1, "p4"),
        (2, "p5"),
    ]