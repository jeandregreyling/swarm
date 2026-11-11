import sqlite3
import pytest
from core import hb_task_operations as operations
from core.tool_approval import ApprovalStore
from test_apex_final_answer import repository


def execute(conn,repository,task,args,*,save_receipt=True):
    store=ApprovalStore()
    tx=store.propose(repository,'propose_patch',args,'owner','session',1)
    key=operations.begin(conn,task,'propose_patch',args,tx)
    receipt=store.decide(tx.id,True,tx.owner,tx.session,tx.csrf,lambda _:True)
    if save_receipt:operations.finish(conn,key,receipt)
    return key,receipt


def test_receipt_survives_new_turn_without_repeated_source_effect(repository):
    conn=sqlite3.connect(':memory:');task={'task_id':'T-SCOPED'}
    args={'file_path':'sample.py','exact_old_text':'hello','new_text':'hello\n# once'}
    key,first=execute(conn,repository,task,args)
    replay=operations.replay(conn,repository,task,'propose_patch',args)
    assert replay['replayed'] and not replay['executed']
    assert replay['transaction_id']==first['transaction_id']
    assert (repository.root/'sample.py').read_text().count('# once')==1


def test_crash_after_write_before_receipt_is_reconciled_from_hash(repository):
    conn=sqlite3.connect(':memory:');task={'task_id':'T-CRASH'}
    args={'file_path':'sample.py','exact_old_text':'hello','new_text':'hello\n# recovered'}
    key,first=execute(conn,repository,task,args,save_receipt=False)
    assert conn.execute('SELECT state FROM hb_task_operations').fetchone()[0]=='pending'
    recovered=operations.replay(conn,repository,task,'propose_patch',args)
    assert recovered['replayed'] and recovered['transaction_id']==first['transaction_id']
    assert (repository.root/'sample.py').read_text().count('# recovered')==1


def test_changed_source_is_not_overwritten_by_old_operation(repository):
    conn=sqlite3.connect(':memory:');task={'task_id':'T-CHANGE'}
    args={'file_path':'sample.py','exact_old_text':'hello','new_text':'hello\n# once'}
    execute(conn,repository,task,args)
    path=repository.root/'sample.py';path.write_text(path.read_text()+'# newer work\n')
    with pytest.raises(ValueError,match='Source changed'):operations.replay(conn,repository,task,'propose_patch',args)
    assert '# newer work' in path.read_text()


def test_old_unguarded_insertion_already_present_cannot_be_repeated(repository):
    (repository.root/'sample.py').write_text('hello\n# already\n')
    with pytest.raises(ValueError,match='already present'):
        ApprovalStore().propose(repository,'propose_patch',{'file_path':'sample.py','exact_old_text':'hello','new_text':'hello\n# already'},'owner','session',1)


def test_human_popup_intent_survives_write_before_receipt(repository):
    conn=sqlite3.connect(':memory:');task={'task_id':'T-POPUP'}
    args={'file_path':'sample.py','exact_old_text':'hello','new_text':'hello\n# popup once'}
    store=ApprovalStore()
    tx,key,reused=operations.prepare_owner_proposal(conn,store,repository,task,'propose_patch',args,'real-owner','owner-session',1,None)
    assert not reused and conn.execute('SELECT state FROM hb_task_operations').fetchone()[0]=='pending'
    result=store.decide(tx.id,True,tx.owner,tx.session,tx.csrf,lambda _:True)
    assert result['status']=='succeeded'  # Simulate process loss before the UI waiter records finish.
    tx,key,reused=operations.prepare_owner_proposal(conn,ApprovalStore(),repository,task,'propose_patch',args,'real-owner','new-session',1,None)
    assert tx is None and key is None and reused['replayed'] and not reused['executed']
    assert (repository.root/'sample.py').read_text().count('# popup once')==1


def test_popup_write_receipt_is_recovered_after_real_process_exit(repository,tmp_path):
    import multiprocessing
    import os
    path=tmp_path/'persistent-popup.sqlite'
    task={'task_id':'T-PERSISTENT-POPUP'}
    args={'file_path':'sample.py','exact_old_text':'hello','new_text':'hello\n# persistent popup once'}
    def approved_process():
        with sqlite3.connect(path) as conn:
            store=ApprovalStore()
            tx,key,_=operations.prepare_owner_proposal(conn,store,repository,task,'propose_patch',args,'owner','session',1,None)
            conn.commit()  # Intent survives independently of this process and UI waiter.
            result=store.decide(tx.id,True,tx.owner,tx.session,tx.csrf,lambda _:True)
            if result['status']!='succeeded':os._exit(59)
            os._exit(57)  # No finish receipt and no connection cleanup.
    process=multiprocessing.get_context('fork').Process(target=approved_process)
    process.start();process.join(timeout=10)
    if process.is_alive():process.terminate();process.join();pytest.fail('Popup crash fixture did not exit')
    assert process.exitcode==57
    before=(repository.root/'sample.py').stat().st_mtime_ns
    with sqlite3.connect(path) as conn:
        original=conn.execute('SELECT transaction_id,state FROM hb_task_operations').fetchone()
        assert original[1]=='pending'
        tx,key,recovered=operations.prepare_owner_proposal(conn,ApprovalStore(),repository,task,'propose_patch',args,'owner','new-session',1,None)
        assert tx is None and key is None and recovered['transaction_id']==original[0]
        assert recovered['replayed'] and not recovered['executed']
    assert (repository.root/'sample.py').stat().st_mtime_ns==before
    assert (repository.root/'sample.py').read_text().count('# persistent popup once')==1
