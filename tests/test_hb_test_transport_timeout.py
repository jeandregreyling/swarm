"""Only bounded guarded checks receive enough transport time to return their receipt."""
import json
import pytest
from core.apex_test_runner import TEST_TIMEOUT_S
from scripts.hummingbird_apex_live_check import AgentAPI


class Reply:
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def read(self,*a):return b'{"ok":true,"output":"recorded result"}'


@pytest.mark.parametrize('path,body,expected', [
    ('/api/agent/v1/tools',{'tool':'run_tests','arguments':{'tests':['tests/test_example.py']}},TEST_TIMEOUT_S+30),
    ('/api/agent/v1/tools',{'tool':'read_file','arguments':{'path':'core/hb_tasks.py'}},20),
    ('/api/agent/v1/whoami',None,20),
    ('/api/peer/v1/messages',{'tool':'run_tests'},20),
])
def test_fixed_test_call_matches_runner_deadline_without_expanding_other_calls(path,body,expected):
    calls=[]
    class Opener:
        def open(self,request,timeout):
            calls.append((request.full_url,timeout))
            # A response arriving after the old20-second boundary remains valid.
            assert timeout==expected
            return Reply()
    api=object.__new__(AgentAPI);api.agent='apex';api._token='test-token';api._opener=Opener()
    assert api.call(path,body)['ok']
    assert len(calls)==1


def test_transport_timeout_does_not_replay_a_test_or_mutation():
    calls=[]
    class Opener:
        def open(self,*a,**k):
            calls.append(1);raise TimeoutError('uncertain transport')
    api=object.__new__(AgentAPI);api.agent='apex';api._token='test-token';api._opener=Opener()
    with pytest.raises(TimeoutError):api.call('/api/agent/v1/tools',{'tool':'run_tests'})
    assert calls==[1]
