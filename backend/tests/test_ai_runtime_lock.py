import threading
import time


def test_priority_inference_lock_admits_high_priority_waiter_first():
    from main import PriorityInferenceLock

    lock = PriorityInferenceLock()
    order: list[str] = []
    low_waiting = threading.Event()
    high_waiting = threading.Event()
    release_holder = threading.Event()

    def holder():
        with lock.priority(1):
            release_holder.wait(timeout=2)

    def waiter(name: str, priority: int, waiting_event: threading.Event):
        waiting_event.set()
        with lock.priority(priority):
            order.append(name)

    holder_thread = threading.Thread(target=holder)
    holder_thread.start()
    time.sleep(0.02)

    low_thread = threading.Thread(target=waiter, args=("low", 2, low_waiting))
    high_thread = threading.Thread(target=waiter, args=("high", 0, high_waiting))

    low_thread.start()
    assert low_waiting.wait(timeout=1)
    time.sleep(0.02)
    high_thread.start()
    assert high_waiting.wait(timeout=1)

    release_holder.set()
    holder_thread.join(timeout=1)
    low_thread.join(timeout=1)
    high_thread.join(timeout=1)

    assert order == ["high", "low"]


def test_priority_inference_lock_plain_context_defaults_to_normal_priority():
    from main import PriorityInferenceLock

    lock = PriorityInferenceLock()

    with lock:
        assert lock._active is True

    assert lock._active is False
