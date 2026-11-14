from test_chat_continuity import healthy_route, isolated_apex_lifecycle


def test_browser_task_selection_isolates_topics_and_can_resume_original_context(healthy_route):
    client,connect,calls=healthy_route
    first=client.post('/api/chat',json={'message':'Review the HF file selection','new_thread':True,'task_id':None}).get_json()
    assert first['ok'] and first['task']
    room=first['conversation_id'];hf=first['task']['task_id']
    second=client.post('/api/chat',json={'message':'Inspect Gemini connectivity','conversation_id':room,'task_id':None}).get_json()
    assert second['ok'] and second['task']['task_id']!=hf
    assert 'Review the HF file selection' not in str(calls[-1][1])
    resumed=client.post('/api/chat',json={'message':'Keep the broad mirror paused','conversation_id':room,'task_id':hf}).get_json()
    assert resumed['ok'] and resumed['task']['task_id']==hf
    prompt=str(calls[-1][1])
    assert 'Review the HF file selection' in prompt and 'Keep the broad mirror paused' in prompt
    assert 'Inspect Gemini connectivity' not in prompt
