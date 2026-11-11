import pytest
from core.hb_agent_tools import public_error
from core import hb_references


def test_error_detail_preserves_validation_and_removes_credentials():
    text=public_error('Read range exceeds 100 lines; token=hbp_abcdefghijklmnopqrstuvwxyz API_KEY=hidden')
    assert '100 lines' in text and 'hidden' not in text and 'abcdefghijklmnopqrstuvwxyz' not in text


def test_local_first_references_do_not_contact_hub_when_local_evidence_exists(monkeypatch):
    from core import apex_knowledge
    monkeypatch.setattr(apex_knowledge,'search',lambda q:{'items':[{'document_id':17}]})
    import huggingface_hub
    monkeypatch.setattr(huggingface_hub,'HfApi',lambda **_:pytest.fail('Unexpected online request'))
    assert hb_references.lookup('function calling',True)['online_queried'] is False


@pytest.mark.parametrize('revision,path',[('main','README.md'),('a'*40,'../secret.txt'),('a'*40,'tool.py'),('a'*40,'/private.txt')])
def test_reference_import_requires_pinned_safe_text(revision,path):
    with pytest.raises(ValueError):hb_references.ingest('dataset','org/repo',revision,path)


def test_task_and_reference_tools_have_real_schema():
    from core.apex_tools import _call_schema
    assert _call_schema('task_memory')['properties']['arguments']['additionalProperties'] is False
    assert _call_schema('reference_import')['properties']['arguments']['required']==['kind','repo','revision','path']


def test_waiting_provider_receipt_cannot_be_described_as_a_new_queue():
    import json
    from core.hb_agent_tools import ground_answer
    receipts=[{'tool':'ask_instructor','status':'succeeded','output':json.dumps({'status':'waiting','request_ids':[6],
        'recorded_state':'failed','recorded_stage':'HTTP 504','notice':'No new inference was queued.'})}]
    answer=ground_answer('Your request was queued again; please authorize.',receipts)
    assert 'remains failed' in answer and 'HTTP 504' in answer and 'No new online request was queued' in answer


def test_queued_acquisition_is_reported_as_pending_even_if_model_claims_complete():
    import json
    from core.hb_agent_tools import ground_answer
    receipts=[{'tool':'archive_acquire','status':'succeeded','output':json.dumps({'job_id':'J-123','status':'running','stage':'Verifying first file'})}]
    answer=ground_answer('All six files have been indexed.',receipts)
    assert 'J-123 is running' in answer and 'completion is not yet verified' in answer
