from client.common import ids


def test_versions_increase_when_wall_clock_moves_backwards(monkeypatch):
    clock = iter([300, 200, 200])
    monkeypatch.setattr(ids.time, "time_ns", lambda: next(clock))
    versions = [int(ids.new_file_id().split(":", 1)[0]) for _ in range(3)]
    assert versions[0] < versions[1] < versions[2]
