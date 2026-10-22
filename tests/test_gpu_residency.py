"""Controller contract tests use fake backends; never load or unload real models."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys
import threading

import pytest

from core.gpu_residency import GIB, Resident, ResidencyController, ResidencyError


@pytest.fixture
def rig(tmp_path):
    residents = []
    released = []

    def release(backend, model):
        released.append((backend, model))
        residents[:] = [r for r in residents if (r.backend, r.model) != (backend, model)]

    controller = ResidencyController(
        tmp_path / 'residency.lock', lambda: list(residents), release,
        lambda: 8 * GIB, enabled=True, timeout_s=0.1,
    )
    return controller, residents, released


def test_disabled_default_has_no_callbacks_or_files(tmp_path):
    def unexpected(*args):
        pytest.fail('Disabled controller touched the runtime')

    path = tmp_path / 'missing' / 'lock'
    controller = ResidencyController(path, unexpected, unexpected, unexpected)
    with controller.lease('ollama', 'qwen'):
        pass
    assert not path.parent.exists()


@pytest.mark.parametrize('backend,model', [
    ('ollama', 'qwen'), ('llamacpp', 'apex'), ('llamacpp', 'embedding'),
])
def test_full_operation_releases_exact_owned_model(rig, backend, model):
    controller, residents, released = rig
    with controller.lease(backend, model):
        residents.append(Resident(backend, model, 'gpu', GIB))
        assert released == []
    assert released == [(backend, model)]
    assert residents == []


def test_stream_is_consumed_and_released_inside_lease(rig):
    controller, residents, released = rig

    def stream():
        with controller.lease('ollama', 'qwen'):
            residents.append(Resident('ollama', 'qwen', 'gpu', GIB))
            yield 'first'
            yield 'second'

    iterator = stream()
    assert next(iterator) == 'first'
    assert released == []
    assert list(iterator) == ['second']
    assert released == [('ollama', 'qwen')]


def test_closing_stream_releases_before_another_request(rig):
    controller, residents, released = rig

    def stream():
        with controller.lease('ollama', 'qwen'):
            residents.append(Resident('ollama', 'qwen', 'gpu', GIB))
            yield 'first'

    iterator = stream()
    next(iterator)
    iterator.close()
    assert released == [('ollama', 'qwen')]
    with controller.lease('llamacpp', 'apex'):
        pass


def test_inference_exception_is_preserved_and_releases_model(rig):
    controller, residents, released = rig
    with pytest.raises(LookupError, match='inference failed'):
        with controller.lease('ollama', 'qwen'):
            residents.append(Resident('ollama', 'qwen', 'gpu', GIB))
            raise LookupError('inference failed')
    assert released == [('ollama', 'qwen')]
    with controller.lease('llamacpp', 'apex'):
        pass


def test_release_error_is_explicit_and_does_not_allow_stale_resident(rig):
    controller, residents, _ = rig

    def fail(*args):
        raise OSError('release failed')

    controller.release = fail
    with pytest.raises(OSError, match='release failed'):
        with controller.lease('ollama', 'qwen'):
            residents.append(Resident('ollama', 'qwen', 'gpu', GIB))
    with pytest.raises(ResidencyError, match='Unreleased GPU resident'):
        with controller.lease('llamacpp', 'apex'):
            pytest.fail('Admitted despite unreleased model')


def test_release_failure_keeps_original_inference_error_as_context(rig):
    controller, residents, _ = rig
    controller.timeout_s = 0
    controller.release = lambda *args: None
    with pytest.raises(ResidencyError, match='Release not confirmed') as caught:
        with controller.lease('ollama', 'qwen'):
            residents.append(Resident('ollama', 'qwen', 'gpu', GIB))
            raise LookupError('inference failed')
    assert isinstance(caught.value.__context__, LookupError)


def test_unload_acknowledgement_is_not_release_proof(rig):
    controller, residents, _ = rig
    controller.timeout_s = 0
    controller.release = lambda *args: None
    with pytest.raises(ResidencyError, match='Release not confirmed'):
        with controller.lease('ollama', 'qwen'):
            residents.append(Resident('ollama', 'qwen', 'gpu', GIB))


def test_delayed_release_is_polled_before_unlocking(rig):
    controller, residents, released = rig
    controller.timeout_s = 1
    controller.release = lambda *args: released.append(args)
    observations = 0

    def snapshot():
        nonlocal observations
        observations += 1
        if released and observations >= 4:
            residents.clear()
        return list(residents)

    controller.snapshot = snapshot
    with controller.lease('ollama', 'qwen'):
        residents.append(Resident('ollama', 'qwen', 'gpu', GIB))
    assert observations >= 4
    assert residents == []


@pytest.mark.parametrize('resident', [
    Resident('ollama', 'qwen', 'gpu', GIB),
    Resident('llamacpp', 'apex', 'gpu', GIB),
    Resident('llamacpp', 'embedding', 'gpu', GIB),
    Resident('ollama', 'fred-cpu:24b', 'gpu', GIB),
    Resident('ollama', 'unknown-cpu', 'cpu', GIB),
])
def test_preexisting_or_unbudgeted_models_are_not_silently_evicted(rig, resident):
    controller, residents, released = rig
    residents.append(resident)
    with pytest.raises(ResidencyError):
        with controller.lease('ollama', 'qwen'):
            pytest.fail('Admission should fail closed')
    assert released == []
    assert residents == [resident]


def test_cpu_fred_stays_resident_within_separate_budget(rig):
    controller, residents, released = rig
    fred = Resident('ollama', 'fred-cpu:24b', 'cpu', 16 * GIB)
    residents.append(fred)
    with controller.lease('ollama', 'qwen'):
        residents.append(Resident('ollama', 'qwen', 'gpu', 10 * GIB))
    assert residents == [fred]
    with controller.lease('ollama', 'fred-cpu:24b', cpu_backup=True):
        pass
    assert released == [('ollama', 'qwen')]
    assert residents == [fred]


def test_cpu_fred_budget_exact_threshold_and_one_byte_over(rig):
    controller, residents, _ = rig
    residents.append(Resident('ollama', 'fred-cpu:24b', 'cpu', controller.cpu_budget_bytes))
    with controller.lease('ollama', 'qwen'):
        pass
    residents[0] = Resident('ollama', 'fred-cpu:24b', 'cpu', controller.cpu_budget_bytes + 1)
    with pytest.raises(ResidencyError, match='separate memory budget'):
        with controller.lease('ollama', 'qwen'):
            pytest.fail('Exceeded budget')


def test_host_reserve_exact_threshold_and_one_byte_below(rig):
    controller, _, _ = rig
    controller.available_memory = lambda: controller.reserve_bytes
    with controller.lease('ollama', 'qwen'):
        pass
    controller.available_memory = lambda: controller.reserve_bytes - 1
    with pytest.raises(ResidencyError, match='required reserve'):
        with controller.lease('ollama', 'qwen'):
            pytest.fail('Below host reserve')


def test_cold_cpu_backup_requires_budget_plus_reserve_before_loading(rig):
    controller, _, released = rig
    controller.available_memory = lambda: controller.cpu_budget_bytes + controller.reserve_bytes - 1
    with pytest.raises(ResidencyError, match='required reserve'):
        with controller.lease('ollama', 'fred-cpu:24b', cpu_backup=True):
            pytest.fail('Cold Fred was admitted without room for its budget')
    assert released == []
    controller.available_memory = lambda: controller.cpu_budget_bytes + controller.reserve_bytes
    with controller.lease('ollama', 'fred-cpu:24b', cpu_backup=True):
        pass


@pytest.mark.parametrize('resident', [
    None, Resident('ollama', 'qwen', 'unknown', GIB),
    Resident('', 'qwen', 'gpu', GIB), Resident('ollama', '', 'gpu', GIB),
    Resident('ollama', 'qwen', 'gpu', 0), Resident('ollama', 'qwen', 'gpu', -1),
])
def test_invalid_observations_fail_closed(rig, resident):
    controller, residents, released = rig
    residents.append(resident)
    with pytest.raises(ResidencyError):
        with controller.lease('ollama', 'qwen'):
            pytest.fail('Invalid snapshot was accepted')
    assert released == []


def test_duplicate_snapshot_and_snapshot_errors_are_not_empty_success(rig):
    controller, residents, _ = rig
    fred = Resident('ollama', 'fred-cpu:24b', 'cpu', GIB)
    residents.extend([fred, fred])
    with pytest.raises(ResidencyError, match='duplicate'):
        with controller.lease('ollama', 'qwen'):
            pass

    def unavailable():
        raise ConnectionError('snapshot unavailable')

    controller.snapshot = unavailable
    with pytest.raises(ConnectionError, match='snapshot unavailable'):
        with controller.lease('ollama', 'qwen'):
            pass


@pytest.mark.parametrize('backend,model', [('ollama', 'qwen'), ('llamacpp', 'fred-cpu:24b')])
def test_only_named_ollama_cpu_fred_gets_residency_exception(rig, backend, model):
    controller, _, _ = rig
    with pytest.raises(ValueError, match='CPU-only Fred'):
        with controller.lease(backend, model, cpu_backup=True):
            pass


def test_threads_queue_across_models_until_release_finishes(rig):
    controller, residents, _ = rig
    controller.timeout_s = 2
    first_entered = threading.Event()
    release_started = threading.Event()
    release_allowed = threading.Event()
    second_waiting = threading.Event()
    second_entered = threading.Event()
    release = controller.release

    def slow_release(backend, model):
        if model == 'qwen':
            release_started.set()
            assert release_allowed.wait(2)
        release(backend, model)

    controller.release = slow_release

    def first():
        with controller.lease('ollama', 'qwen'):
            residents.append(Resident('ollama', 'qwen', 'gpu', GIB))
            first_entered.set()

    def second():
        second_waiting.set()
        with controller.lease('llamacpp', 'apex'):
            second_entered.set()
            residents.append(Resident('llamacpp', 'apex', 'gpu', GIB))

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(first)
        assert first_entered.wait(2) and release_started.wait(2)
        b = pool.submit(second)
        assert second_waiting.wait(2)
        assert not second_entered.wait(0.05)
        release_allowed.set()
        a.result(timeout=3)
        b.result(timeout=3)
    assert second_entered.is_set()
    assert residents == []


@pytest.mark.skipif(sys.platform == 'win32', reason='POSIX file-lock contract')
def test_cross_process_lease_timeout_and_crash_release(tmp_path):
    lock = tmp_path / 'residency.lock'
    child = r'''
import sys
from pathlib import Path
from core.gpu_residency import ResidencyController, GIB
controller = ResidencyController(Path(sys.argv[1]), lambda: [], lambda *a: None,
                                 lambda: 8 * GIB, enabled=True)
with controller.lease('ollama', 'qwen'):
    print('lease-held', flush=True)
    sys.stdin.readline()
'''
    process = subprocess.Popen(
        [sys.executable, '-u', '-c', child, str(lock)],
        cwd=Path(__file__).resolve().parents[1],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        from select import select

        assert select([process.stdout], [], [], 5)[0], 'Child lease did not become ready'
        assert process.stdout.readline().strip() == 'lease-held'
        controller = ResidencyController(
            lock, lambda: [], lambda *a: None, lambda: 8 * GIB,
            enabled=True, timeout_s=0,
        )
        with pytest.raises(ResidencyError, match='waiting for a process'):
            with controller.lease('llamacpp', 'apex'):
                pytest.fail('Cross-process overlap')
        process.terminate()
        process.wait(timeout=5)
        with controller.lease('llamacpp', 'apex'):
            pass
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        process.stdin.close()
        process.stdout.close()
        process.stderr.close()


@pytest.mark.parametrize('timeout', [-1, float('inf'), float('nan')])
def test_queue_timeout_must_be_bounded(tmp_path, timeout):
    with pytest.raises(ValueError, match='finite and nonnegative'):
        ResidencyController(tmp_path / 'lock', lambda: [], lambda *a: None,
                            lambda: 8 * GIB, timeout_s=timeout)
