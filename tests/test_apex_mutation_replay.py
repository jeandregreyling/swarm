import json
from core.apex_tools import run_apex_tools
from test_apex_final_answer import repository


def exercise(repository, payloads):
    dispatches=[]
    outputs=iter([json.dumps({'tool_calls':[call],'answer':''}) for call in payloads]
        +[json.dumps({'tool_calls':[],'answer':'Patch receipts recorded; wider work remains open.'})])
    def model(*_):return next(outputs),1
    def apply(repo,name,args):
        dispatches.append(args.copy())
        path=repo.root/'sample.py'
        path.write_text(path.read_text().replace(args['exact_old_text'],args['new_text'],1))
        return {'status':'succeeded','output':'Patch applied'}
    _,_,receipts=run_apex_tools(model,[{'role':'user','content':'Apply the requested patch to sample.py once.'}],
        lambda:True,lambda _:None,repository,proposal_handler=apply)
    return dispatches,receipts


def test_identical_successful_insertion_is_dispatched_once(repository):
    call={'name':'propose_patch','arguments':{'file_path':'sample.py',
        'exact_old_text':'hello','new_text':'hello\n# inserted'}}
    dispatches,receipts=exercise(repository,[call,call,call])
    assert len(dispatches)==1
    assert len(receipts)==1
    assert (repository.root/'sample.py').read_text().count('# inserted')==1


def test_different_patch_payloads_are_not_suppressed(repository):
    first={'name':'propose_patch','arguments':{'file_path':'sample.py',
        'exact_old_text':'hello','new_text':'hello\n# first'}}
    second={'name':'propose_patch','arguments':{'file_path':'sample.py',
        'exact_old_text':'hello','new_text':'hello\n# second'}}
    dispatches,receipts=exercise(repository,[first,second])
    assert len(dispatches)==2 and len(receipts)==2
    assert '# first' in (repository.root/'sample.py').read_text()
    assert '# second' in (repository.root/'sample.py').read_text()


def test_immutable_task_evidence_is_not_fetched_repeatedly(repository):
    from core.apex_tools import repeated_read
    call={'name':'task_evidence','arguments':{'evidence_id':17,'offset':0}}
    receipt={'tool':'task_evidence','arguments':call['arguments'],'status':'succeeded','output':'saved plan'}
    assert repeated_read(call,[receipt]) is receipt
    assert repeated_read({'name':'task_evidence','arguments':{'evidence_id':17,'offset':1500}},[receipt]) is None


def test_promised_authorized_edit_is_corrected_into_execution(repository):
    outputs=iter([
        {'tool_calls':[],'answer':'The next step is to patch the source; this is not yet performed.'},
        {'tool_calls':[{'name':'propose_patch','arguments':{'file_path':'sample.py','exact_old_text':'hello','new_text':'hello\n# done'}}],'answer':''},
        {'tool_calls':[],'answer':'The guarded patch was applied; remaining checks are separate.'}])
    applied=[]
    def model(_model,messages):
        if len(applied)==0 and 'BACKEND EXECUTION CHECK' in messages[-1]['content']:applied.append('correction')
        return json.dumps(next(outputs)),1
    def proposal(repo,name,args):
        applied.append('write');return {'status':'succeeded','output':'Applied'}
    answer,_,receipts=run_apex_tools(model,[{'role':'user','content':'Implement the approved source change.'}],
        lambda:True,lambda _:None,repository,proposal_handler=proposal,studio_handler=lambda *_:{})
    assert applied==['correction','write'] and receipts[0]['status']=='succeeded'
    assert 'applied' in answer
