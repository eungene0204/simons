import threading
import time


def test_priority_inference_lock_admits_high_priority_waiter_first(monkeypatch):
    # 락은 MLX 모드에서만 게이트를 건다(Ollama면 no-op). 우선순위 직렬화 메커니즘을
    # 검증하려면 MLX 모드로 고정한다.
    monkeypatch.setenv("LLM_BACKEND", "mlx")
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


def test_priority_inference_lock_is_noop_under_ollama(monkeypatch):
    """Ollama 모드에서는 .priority() 락이 no-op이라 두 스레드가 동시에 진입할 수 있다
    (전역 직렬화 해제 → 동시 코칭 가능). 락이 직렬화한다면 barrier가 타임아웃돼
    BrokenBarrierError가 나고 ok 가 2개가 되지 못한다."""
    monkeypatch.setenv("LLM_BACKEND", "ollama")
    from main import PriorityInferenceLock

    lock = PriorityInferenceLock()
    both_inside = threading.Barrier(2, timeout=2)
    ok: list[bool] = []

    def worker():
        with lock.priority(1):
            both_inside.wait()  # 두 스레드가 동시에 락 안에 있어야만 통과
            ok.append(True)

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    t1.join(timeout=3)
    t2.join(timeout=3)

    assert ok == [True, True]
    assert lock._active is False
