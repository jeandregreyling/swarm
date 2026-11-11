import json
import queue
from core.hb_codex_runtime import CodexRuntime


class FakeProcess:
    def __init__(self,*args,**kwargs):
        self.events=queue.Queue();self.sent=[]
        self.stdin=self;self.stdout=self
    def write(self,line):
        message=json.loads(line);self.sent.append(message)
        method=message.get('method');request=message.get('id')
        if method=='initialize':self.put({'id':request,'result':{}})
        elif method in {'thread/start','thread/resume'}:
            self.put({'id':request,'result':{'thread':{'id':'hb-thread'},'model':'account-configured-codex'}})
        elif method=='turn/start':
            # Deliberately deliver completed events before the start response.
            self.put({'id':900,'method':'item/tool/call','params':{'threadId':'wrong-thread','turnId':'turn-1','tool':'hb_read_file','arguments':{}}})
            self.put({'id':901,'method':'item/tool/call','params':{'threadId':'hb-thread','turnId':'turn-1','tool':'hb_read_file','arguments':{'path':'README.md'}}})
            self.put({'method':'item/completed','params':{'threadId':'other-thread','turnId':'turn-1','item':{'id':'other','type':'agentMessage','text':'wrong answer'}}})
            self.put({'method':'item/completed','params':{'threadId':'hb-thread','turnId':'turn-1','item':{'id':'answer','type':'agentMessage','phase':'final_answer','text':'Read the source through HB.'}}})
            self.put({'method':'turn/completed','params':{'threadId':'hb-thread','turn':{'id':'turn-1','status':'completed'}}})
            self.put({'id':request,'result':{'turn':{'id':'turn-1'}}})
    def put(self,event):self.events.put(json.dumps(event)+'\n')
    def readline(self,limit):return self.events.get(timeout=5)
    def flush(self):pass
    def close(self):self.events.put('')
    def wait(self,timeout=None):return 0
    def terminate(self):self.close()


def test_codex_uses_persistent_thread_and_hb_tools_with_strict_conversation_binding(tmp_path):
    process=FakeProcess();calls=[]
    runtime=CodexRuntime(process_factory=lambda *_a,**_k:process,timeout=3)
    try:
        result=runtime.turn('Inspect the file',cwd=tmp_path,tools=[],handler=lambda name,args:calls.append((name,args)) or {'ok':True},progress=lambda _:None)
        assert result=={'thread_id':'hb-thread','model':'account-configured-codex','answer':'Read the source through HB.'}
        assert calls==[('hb_read_file',{'path':'README.md'})]
        rejected=next(m for m in process.sent if m.get('id')==900 and 'result' in m)
        assert rejected['result']['success'] is False
        accepted=next(m for m in process.sent if m.get('id')==901 and 'result' in m)
        assert accepted['result']['success'] is True
        start=next(m for m in process.sent if m.get('method')=='thread/start')
        assert start['params']['sandbox']=='read-only' and 'model' not in start['params']
        assert start['params']['dynamicTools']==[]
        runtime.turn('Continue',cwd=tmp_path,tools=[],handler=lambda *_:{},progress=lambda _:None,thread_id='hb-thread')
        assert any(m.get('method')=='thread/resume' for m in process.sent)
    finally:runtime.close()


def test_provider_usage_is_scoped_to_thread_turn_and_counts_only_new_tokens(tmp_path):
    class UsageProcess(FakeProcess):
        def __init__(self):super().__init__();self.completed=0
        def put(self,event):
            if event.get('method')=='turn/completed':
                self.completed+=1
                n=self.completed
                super().put({'method':'thread/tokenUsage/updated','params':{'threadId':'hb-thread','turnId':'turn-1',
                    'tokenUsage':{'total':{'inputTokens':120*n,'outputTokens':30*n,'totalTokens':150*n,
                      'cachedInputTokens':20*n,'reasoningOutputTokens':5*n},'last':{}}}})
            super().put(event)
    process=UsageProcess();runtime=CodexRuntime(process_factory=lambda *_a,**_k:process,timeout=3)
    try:
        first=runtime.turn('Inspect',cwd=tmp_path,tools=[],handler=lambda *_:{},progress=lambda _:None)
        second=runtime.turn('Continue',cwd=tmp_path,tools=[],handler=lambda *_:{},progress=lambda _:None,thread_id='hb-thread')
        assert first['usage']==second['usage']=={'source':'provider','input_tokens':120,'output_tokens':30,
            'total_tokens':150,'cached_tokens':20,'reasoning_tokens':5}
    finally:runtime.close()
