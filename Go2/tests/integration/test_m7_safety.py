from core.control.remote_control import CommandQueue


def test_m7_safety_lifecycle():
    q = CommandQueue()

    # 1. Normal movement
    assert q.submit(0.1, 0.1) is not None
    assert q.take()[1:] == (0.1, 0.1)

    # 2. Communication fault
    q.set_fault()
    assert q.fault
    assert q.submit(0.1, 0.0) is None
    assert not q.clear_fault()

    # 3. STOP has priority
    assert q.submit(0.0, 0.0) is not None
    assert q.take()[1:] == (0.0, 0.0)
    assert q.stop_in_progress

    # 4. Recovery blocked during STOP
    assert not q.recovery_ready()
    assert not q.authorize_recovery()
    assert not q.clear_fault()
    assert q.submit(0.1, 0.0) is None

    # 5. STOP completed
    q.finish_stop()
    assert q.recovery_ready()
    assert q.fault
    assert q.submit(0.1, 0.0) is None

    # 6. Explicit authorization
    assert q.authorize_recovery()
    assert q.clear_fault()
    assert not q.fault

    # 7. Movement restored
    assert q.submit(0.1, 0.0) is not None
    assert q.take()[1:] == (0.1, 0.0)

    # 8. Second fault
    q.set_fault()
    assert q.fault
    assert q.submit(0.1, 0.0) is None
    assert not q.clear_fault()
