import pytest
from frontend.blueprints.mondcraft import parse_decision
from frontend.blueprints.mondcraft import teaching_lesson


@pytest.fixture(autouse=True)
def no_live_game_requests(monkeypatch):
    from frontend.blueprints import mondcraft
    def blocked(*args, **kwargs):
        raise mondcraft.requests.ConnectionError('Isolated test: no live Minecraft calls')
    monkeypatch.setattr(mondcraft.requests,'get',blocked)
    monkeypatch.setattr(mondcraft.requests,'post',blocked)


def test_game_decisions_are_data_not_executable_skills():
    allowed = [{'id': 'C4', 'owner': None}]
    assert parse_decision('{"action":"claim","target":"C4","reason":"Expand"}', allowed)['target'] == 'C4'
    assert parse_decision('{"action":"explore","target":"C4","reason":"Look around"}', allowed)['action'] == 'explore'
    assert parse_decision('{"action":"gather","target":"C4","reason":"Collect stone"}', allowed)['action'] == 'gather'
    for raw in ('SKILL shell rm anything', '{"action":"shell","target":"C4"}', '{"action":"claim","target":"Z9"}'):
        with pytest.raises((ValueError, KeyError)):
            parse_decision(raw, allowed)


def test_teaching_advances_only_from_verified_inventory_and_discoveries():
    legal=[{'id':'A1','resource':{'remaining':2}},{'id':'A2','resource':None}]
    assert teaching_lesson({'resources':{},'visited':[]},legal)['action']=='gather'
    assert teaching_lesson({'resources':{'stone':1},'visited':['A1']},legal)['targets']==['A2']
    assert teaching_lesson({'resources':{'stone':1},'visited':['A1','A2']},legal)['action']=='gather'
    assert teaching_lesson({'resources':{'stone':2},'visited':['A1','A2']},legal)['action'] is None
    assert teaching_lesson({'resources':{},'visited':[]},[{'id':'A1','resource':{'remaining':0}}])['action']=='explore'


def test_native_thinking_rejects_external_identity_and_operational_commands(monkeypatch):
    from flask import Flask
    from frontend.blueprints import mondcraft
    monkeypatch.setattr(mondcraft,'local_roster',lambda:[{'name':'apex','model':'local'}])
    monkeypatch.setattr('core.llm.chat_via_gateway',lambda *args,**kwargs:('{"action":"shell","args":{}}',10))
    app=Flask(__name__);app.register_blueprint(mondcraft.mondcraft_bp);client=app.test_client()
    assert client.post('/api/mondcraft/think',json={'agent':'paid','state':{}}).status_code==400
    assert client.post('/api/mondcraft/think',json={'agent':'apex','state':{}}).status_code==422
    monkeypatch.setattr('core.llm.chat_via_gateway',lambda *args,**kwargs:('{"action":"defend","args":{}}',10))
    response=client.post('/api/mondcraft/think',json={'agent':'apex','state':{'nearby_entities':[{'name':'zombie'}]}})
    assert response.status_code==200 and response.json['action']=='defend'


def test_pause_and_resume_target_native_population_without_world_reset(monkeypatch):
    from flask import Flask
    from types import SimpleNamespace
    from frontend.blueprints import mondcraft
    calls=[]
    monkeypatch.setattr(mondcraft.requests,'get',lambda *args,**kwargs:SimpleNamespace(ok=True,json=lambda:{'mode':'native-survival-mindcraft'}))
    monkeypatch.setattr(mondcraft.requests,'post',lambda url,**kwargs:(calls.append(url) or SimpleNamespace(ok=True,json=lambda:{'ok':True,'paused':url.endswith('/pause')})))
    app=Flask(__name__);app.register_blueprint(mondcraft.mondcraft_bp);client=app.test_client()
    assert client.post('/api/mondcraft/pause',json={}).status_code==200
    assert client.post('/api/mondcraft/start',json={}).status_code==202
    assert calls==['http://127.0.0.1:6062/pause','http://127.0.0.1:6062/resume']


def test_game_api_rejects_external_players_and_invalid_rounds(monkeypatch):
    from flask import Flask
    from frontend.blueprints import mondcraft
    monkeypatch.setattr(mondcraft, 'local_roster', lambda: [{'name':'gemma','model':'local'},{'name':'apex','model':'local'}])
    app = Flask(__name__)
    app.register_blueprint(mondcraft.mondcraft_bp)
    client = app.test_client()
    assert client.post('/api/mondcraft/start', json={'agents':['gemma','paid_model']}).status_code == 400
    assert client.post('/api/mondcraft/start', json={'rounds':0}).status_code == 400
    assert client.post('/api/mondcraft/start', json={'agents':['gemma']}).status_code == 400


def test_resume_preserves_existing_world_and_issues_manual(monkeypatch):
    from flask import Flask
    from frontend.blueprints import mondcraft
    roster=[{'name':'gemma','model':'local'},{'name':'apex','model':'local'}]
    monkeypatch.setattr(mondcraft,'local_roster',lambda:roster)
    monkeypatch.setitem(mondcraft._MATCH,'running',False)
    calls=[]

    def arena(path,data=None,timeout=45):
        calls.append(path)
        assert path=='/state', 'Resume must never reset or configure the world'
        return {'matchId':'existing','players':[dict(row,connected=True) for row in roster]}

    class Thread:
        def __init__(self,**kwargs):
            self.kwargs=kwargs
        def start(self):
            pass

    monkeypatch.setattr(mondcraft,'arena',arena)
    monkeypatch.setattr(mondcraft.threading,'Thread',Thread)
    app=Flask(__name__);app.register_blueprint(mondcraft.mondcraft_bp)
    response=app.test_client().post('/api/mondcraft/start',json={'resume':True,'rounds':3})
    assert response.status_code==202 and response.json['match_id']=='existing'
    assert calls==['/state']
    assert 'Ghost' in (mondcraft.ROOT/'mondcraft'/'MANUAL.md').read_text()
    mondcraft._MATCH['running']=False


def test_native_wrapper_reports_queue_and_loaded_model_placement(monkeypatch):
    from flask import Flask
    from types import SimpleNamespace
    from frontend.blueprints import mondcraft
    monkeypatch.setattr(mondcraft,'local_roster',lambda:[{'name':'gemma','model':'gemma3:latest'}])
    native={'status':'living','mode':'native-survival-mindcraft','inference':{'active':2,'limit':2,'queued':12},'players':[{'name':'gemma','model':'gemma3:latest','connected':True,'status':'thinking'}]}
    def get(url,**kwargs):
        if url.endswith('/state'):
            return SimpleNamespace(ok=True,json=lambda:native)
        raise AssertionError(url)
    monkeypatch.setattr(mondcraft.requests,'get',get)
    loaded=SimpleNamespace(name='gemma3:latest',model='gemma3:latest',size_vram=4096,details=SimpleNamespace(parameter_size='3.9B'),runtime='llamacpp')
    monkeypatch.setattr('core.llm.ps',lambda:SimpleNamespace(models=[loaded]))
    mondcraft._RUNTIME_CACHE.update(expires=0,value=None)
    app=Flask(__name__);app.register_blueprint(mondcraft.mondcraft_bp)
    response=app.test_client().get('/api/mondcraft/state')
    assert response.status_code==200
    assert response.json['runtime']['loaded_models'][0]['name']=='gemma3:latest'
    assert response.json['inference']=={'active':2,'limit':2,'queued':12}
    assert response.json['players'][0]['model_loaded'] is True
    assert response.json['players'][0]['model_location'].startswith('VRAM ')


def test_chat_reply_is_sent_to_native_population_not_legacy_arena(monkeypatch):
    from flask import Flask
    from types import SimpleNamespace
    from frontend.blueprints import mondcraft
    calls=[]
    monkeypatch.setattr(mondcraft,'local_roster',lambda:[{'name':'qwen','model':'qwen2.5:14b-instruct'}])
    monkeypatch.setattr('core.llm.chat_via_gateway',lambda *args,**kwargs:('Hello Ghost, I am working on the studio.',12))
    monkeypatch.setattr(mondcraft.requests,'post',lambda url,**kwargs:(calls.append((url,kwargs['json'])) or SimpleNamespace(ok=True)))
    monkeypatch.setattr(mondcraft,'arena',lambda *args,**kwargs:pytest.fail('Chat must not use the legacy arena'))

    class InlineThread:
        def __init__(self,**kwargs):self.target=kwargs['target']
        def start(self):self.target()

    monkeypatch.setattr(mondcraft.threading,'Thread',InlineThread)
    app=Flask(__name__);app.register_blueprint(mondcraft.mondcraft_bp)
    response=app.test_client().post('/api/mondcraft/chat',json={'message':'@qwen What are you doing?'})
    assert response.status_code==202
    assert calls==[('http://127.0.0.1:6062/speak',{'agent':'qwen','message':'Hello Ghost, I am working on the studio.'})]
    status=app.test_client().get(f"/api/mondcraft/chat/{response.json['request_id']}")
    assert status.status_code==200
    assert status.json['status']=='sent'
    assert status.json['reply']=='Hello Ghost, I am working on the studio.'