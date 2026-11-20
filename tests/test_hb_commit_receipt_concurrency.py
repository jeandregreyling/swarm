"""A successful commit receipt identifies its own object even when HEAD moves immediately."""
import json
import subprocess
from pathlib import Path
from core import hb_change_sets as cs

SID='S-ABCDEF0001'


def repo(tmp_path):
    def git(*args):
        return subprocess.run(['git','-C',str(tmp_path),*args],capture_output=True,text=True,check=True)
    git('init','-q');git('config','user.name','Isolated Test');git('config','user.email','test@example.invalid')
    (tmp_path/'value.py').write_text('value = 1\n')
    (tmp_path/'other.txt').write_text('initial\n')
    git('add','value.py','other.txt');git('commit','-q','-m','base')
    saved=tmp_path/'runtime/change_sets/steps'/SID;saved.mkdir(parents=True)
    (saved/'change_set.json').write_text(json.dumps({'step_id':SID,'why':'value two','edits':[{'path':'value.py','old':'value = 1','new':'value = 2'}]}))
    cs.apply(SID,root=tmp_path)
    return git,saved


def test_concurrent_head_movement_does_not_misattribute_the_committed_files(tmp_path,monkeypatch):
    git,saved=repo(tmp_path)
    (tmp_path/'unrelated.txt').write_text('preserve this dirty work')
    real_run=subprocess.run;made=[]
    def interleaved(command,*args,**kwargs):
        result=real_run(command,*args,**kwargs)
        if 'commit' in command and '--only' in command and result.returncode==0 and not made:
            own=real_run(['git','-C',str(tmp_path),'rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
            made.append(own)
            (tmp_path/'other.txt').write_text('concurrent accepted component\n')
            real_run(['git','-C',str(tmp_path),'add','other.txt'],check=True,capture_output=True)
            real_run(['git','-C',str(tmp_path),'commit','-q','-m','another component'],check=True,capture_output=True)
        return result
    monkeypatch.setattr(cs.subprocess,'run',interleaved)
    result=cs.commit(SID,'Own component',root=tmp_path)
    assert result['state']=='committed'
    receipt=json.loads((saved/'commit.json').read_text())
    assert receipt['commit']==made[0]
    assert git('rev-parse','HEAD').stdout.strip()!=made[0]
    assert git('show','--format=','--name-only',receipt['commit']).stdout.strip()=='value.py'
    assert (tmp_path/'unrelated.txt').read_text()=='preserve this dirty work'
    assert git('status','--porcelain','--','unrelated.txt').stdout.strip()=='?? unrelated.txt'


def test_noop_does_not_replace_a_valid_old_receipt_with_current_head(tmp_path):
    git,saved=repo(tmp_path)
    first=cs.commit(SID,root=tmp_path)
    assert first['state']=='committed'
    prior=(saved/'commit.json').read_bytes()
    (tmp_path/'other.txt').write_text('another component\n');git('add','other.txt');git('commit','-q','-m','other')
    assert cs.commit(SID,root=tmp_path)['state']=='nothing to commit'
    assert (saved/'commit.json').read_bytes()==prior


def test_failed_commit_saves_no_receipt(tmp_path,monkeypatch):
    git,saved=repo(tmp_path);real_run=subprocess.run
    def fail(command,*args,**kwargs):
        if 'commit' in command and '--only' in command:
            return subprocess.CompletedProcess(command,1,'','rejected test commit')
        return real_run(command,*args,**kwargs)
    monkeypatch.setattr(cs.subprocess,'run',fail)
    assert cs.commit(SID,root=tmp_path)['state']=='git commit failed'
    assert not (saved/'commit.json').exists()


def test_unverifiable_summary_never_falls_back_to_head(tmp_path,monkeypatch):
    git,saved=repo(tmp_path);real_run=subprocess.run
    def no_summary(command,*args,**kwargs):
        result=real_run(command,*args,**kwargs)
        if 'commit' in command and '--only' in command and result.returncode==0:
            result.stdout=''
        return result
    monkeypatch.setattr(cs.subprocess,'run',no_summary)
    assert cs.commit(SID,root=tmp_path)['state']=='committed without receipt'
    assert not (saved/'commit.json').exists()
    assert git('show','HEAD:value.py').stdout=='value = 2\n'
