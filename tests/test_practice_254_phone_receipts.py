"""Practice 254: phone task changes are linked to receipts; claims without them are caught."""
from core.hb_channels import link_phone_receipts


def R(action, tid, status='succeeded', output='ok'):
    return {'tool': 'hb_tasks', 'arguments': {'action': action, 'task_id': tid}, 'status': status, 'output': output}


def test_a_claim_with_no_change_is_replaced_by_the_truth():
    out = link_phone_receipts('T-0000000000AA - cancel - chat with JD', [R('list', '')])
    assert out.startswith('No task was changed this turn')


def test_failed_attempts_are_shown():
    out = link_phone_receipts('Cancelled T-0000000000AA.', [R('cancel', 'T-0000000000AA', 'failed', 'PermissionError: JD step')])
    assert 'No task was changed' in out and 'PermissionError' in out


def test_real_changes_get_receipt_lines():
    out = link_phone_receipts('Cancelled T-0000000000AA.', [R('cancel', 't-0000000000aa')])
    assert 'Receipts (hb_tasks): cancel T-0000000000AA - done' in out


def test_plain_answers_are_untouched():
    assert link_phone_receipts('There are 20 open tasks.', [R('list', '')]) == 'There are 20 open tasks.'
