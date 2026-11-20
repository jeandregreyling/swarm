"""Media writes and serving stay in the selected data root, including collection-time state."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def test_test_root_is_selected_before_collection_imports():
    from core.media_center import framework
    from core.media_center.storage import MEDIA_STORAGE_ROOT
    assert MEDIA_STORAGE_ROOT == Path(os.environ['HUMMINGBIRD_MEDIA_ROOT']).resolve()
    assert MEDIA_STORAGE_ROOT != ROOT.resolve()
    assert framework._STATE_PATH.is_relative_to(MEDIA_STORAGE_ROOT)
    assert framework._ARTIFACT_ROOT.is_relative_to(MEDIA_STORAGE_ROOT)


def test_default_media_root_preserves_production_location(tmp_path):
    env={**os.environ,'SWARM_ROOT':str(tmp_path/'install'),'PYTHONPATH':str(ROOT)}
    env.pop('HUMMINGBIRD_MEDIA_ROOT',None)
    run=subprocess.run([sys.executable,'-c',
        'from pathlib import Path; from core.media_center.storage import MEDIA_STORAGE_ROOT; from utils.swarm_root import SWARM_ROOT; assert MEDIA_STORAGE_ROOT==Path(SWARM_ROOT).resolve()'],
        cwd=ROOT,env=env,capture_output=True,text=True,timeout=15)
    assert run.returncode==0,run.stdout+run.stderr


def test_real_state_wav_manifest_and_download_leave_original_sentinels_untouched(tmp_path):
    install=tmp_path/'installation'
    state=install/'sandpits/shared/media_center_state.json'
    state.parent.mkdir(parents=True)
    state.write_bytes(b'{"owner":"real-state-sentinel"}')
    original_artifact=install/'artifacts/media_center/owner.wav'
    original_artifact.parent.mkdir(parents=True)
    original_artifact.write_bytes(b'owner-artifact-sentinel')
    selected=tmp_path/'selected-media'
    env={**os.environ,'SWARM_ROOT':str(install),'HUMMINGBIRD_MEDIA_ROOT':str(selected),
         'SWARM_DB_PATH':str(tmp_path/'isolated.db'),'STAGE':'UAT','PYTHONPATH':str(ROOT)+':'+str(ROOT/'frontend')}
    code=r"""
import base64, json
from pathlib import Path
from flask import Flask
from utils.db import initialise_database
initialise_database()
from core.media_center import framework as f
from core.media_center.storage import MEDIA_STORAGE_ROOT as data
from utils.swarm_root import SWARM_ROOT
from frontend.blueprints.media_center import media_center_bp
from frontend.blueprints.media_bp import media_bp
assert data != Path(SWARM_ROOT).resolve()
f.save_state({'projects':[],'jobs':[]})
project=f.create_project({'name':'isolated preview','duration_sec':5})
job=f.create_job(project['id'],{'job_type':'generate-audio'})
done=f.run_job_real(job['id'])
assert done['status']=='completed'
wav=next(a for a in done['artifacts'] if a['mime_type']=='audio/wav')
manifest=next(a for a in done['artifacts'] if a['mime_type']=='application/json')
assert (data/wav['path']).read_bytes().startswith(b'RIFF')
assert json.loads((data/manifest['path']).read_text())['job_id']==job['id']
app=Flask(__name__);app.register_blueprint(media_center_bp);app.register_blueprint(media_bp)
with app.test_client() as client:
    assert client.get(wav['url']).data.startswith(b'RIFF')
    assert client.get(manifest['url']).get_json()['job_id']==job['id']
    screenshot=client.post('/api/media/screenshot',json={'data_url':'data:image/png;base64,'+base64.b64encode(b'isolated-image').decode()}).get_json()
    assert screenshot['ok'] and (data/screenshot['output_path']).read_bytes()==b'isolated-image'
    relative=Path(screenshot['output_path']).relative_to('artifacts/media_center').as_posix()
    assert client.get('/api/media/artifacts/'+relative).data==b'isolated-image'
    assert client.get('/api/media/artifacts/../owner.wav').status_code==404
    assert client.get('/api/media-center/artifacts/sandpits/shared/media_center_state.json').status_code==404
assert f._STATE_PATH.is_relative_to(data)
"""
    result=subprocess.run([sys.executable,'-c',code],cwd=ROOT,env=env,capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    assert state.read_bytes()==b'{"owner":"real-state-sentinel"}'
    assert original_artifact.read_bytes()==b'owner-artifact-sentinel'
    assert sorted(p for p in (install/'artifacts').rglob('*') if p.is_file())==[original_artifact]
    assert sorted(p for p in (install/'sandpits').rglob('*') if p.is_file())==[state]
