import threading
import time

from core.apex_turn_queue import TurnQueue


def test_turns_are_served_in_arrival_order_and_waiters_learn_their_position():
    queue = TurnQueue()
    assert queue.acquire(0) and queue.busy()
    order, positions, threads = [], [], []
    for name in ("first", "second"):
        def worker(name=name):
            assert queue.acquire(5, on_wait=positions.append)
            order.append(name)
            queue.release()
        thread = threading.Thread(target=worker)
        thread.start()
        threads.append(thread)
        time.sleep(0.05)
    assert positions == [1, 2] and order == []
    queue.release()
    for thread in threads:
        thread.join(2)
    assert order == ["first", "second"] and not queue.busy()


def test_timed_out_waiter_is_skipped_without_blocking_later_turns():
    queue = TurnQueue()
    assert queue.acquire(0)
    assert queue.acquire(0.05) is False
    later = []
    thread = threading.Thread(target=lambda: later.append(queue.acquire(5)))
    thread.start()
    time.sleep(0.05)
    assert later == []
    queue.release()
    thread.join(2)
    assert later == [True]
    queue.release()
    assert not queue.busy() and queue.acquire(0)
