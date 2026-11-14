from pathlib import Path
import shutil
import subprocess
import pytest


def test_selected_studio_project_mounts_workflow_without_losing_content():
    node=shutil.which('node')
    if not node:pytest.skip('Node unavailable')
    text=(Path(__file__).resolve().parents[1]/'frontend/static/js/views/projects.js').read_text()
    start=text.index('  function _loadDetail(pid) {')
    end=text.index('\n  function ',start+10)
    script="""
const calls=[];const det={innerHTML:'',children:[],appendChild(x){this.children.push(x);}};
const document={getElementById:()=>det,createElement:()=>({})};
const window={hbOpenTaskBoard:(pid,host)=>calls.push([pid,host])};
const _renderDetail=()=>'<main>Existing project content</main>';const _esc=String;
const fetch=async url=>({json:async()=>url.includes('test-runs')?{items:[]}:{ok:true,project:{project_id:'P-ABCDEF0123'}}});
"""+text[start:end]+"""
    _loadDetail('P-ABCDEF0123');
    setImmediate(()=>{if(calls.length!==1 || calls[0][0]!=='P-ABCDEF0123' || calls[0][1]!==det.children[0] || !det.innerHTML.includes('Existing project content'))throw Error('Studio workflow mount failed');});
"""
    subprocess.run([node,'-e',script],check=True,timeout=10)
