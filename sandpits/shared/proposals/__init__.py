def promote_proposal(filename):
    """Promote a proposal to the next stage by copying its file to the next stage's directory."""
    import shutil
    stage = int(os.environ.get('STAGE', 3))
    if stage <= 1:
        return False  # Already in production
    dir_path = _get_stage_dir()
    src_path = os.path.join(dir_path, filename)
    if not os.path.exists(src_path):
        return False
    with open(src_path, 'r') as f:
        data = json.load(f)
    # Update stage for the promoted copy
    next_stage = stage - 1
    data['stage'] = next_stage
    # Write to next stage directory
    base = os.path.dirname(os.path.dirname(__file__))
    dest_dir = os.path.join(base, f'sandpits_stage{next_stage}', 'proposals')
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, filename)
    with open(dest_path, 'w') as f:
        json.dump(data, f, indent=2)
    return True
# Proposal helpers for multi-stage workflow
import os, json

PROPOSALS_DIR = os.path.join(os.path.dirname(__file__), 'proposals')
os.makedirs(PROPOSALS_DIR, exist_ok=True)

def _get_stage_dir():
    stage = int(os.environ.get('STAGE', 3))
    base = os.path.dirname(os.path.dirname(__file__))
    return os.path.join(base, f'sandpits_stage{stage}', 'proposals')

def list_proposals():
    """List all proposals with metadata (including stage if present)."""
    dir_path = _get_stage_dir()
    os.makedirs(dir_path, exist_ok=True)
    proposals = []
    for fname in os.listdir(dir_path):
        if not fname.endswith('.json'):
            continue
        fpath = os.path.join(dir_path, fname)
        try:
            with open(fpath, 'r') as f:
                data = json.load(f)
            proposals.append(data)
        except Exception:
            continue
    return proposals
def update_proposal_stage(filename, stage):
    """Update the stage of a proposal (by filename)."""
        """Read a proposal by filename (JSON)."""
        dir_path = _get_stage_dir()
        path = os.path.join(dir_path, filename)
        if not os.path.exists(path): return None
        with open(path, 'r') as f:
            return json.load(f)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
        """Update the stage of a proposal (by filename)."""
        dir_path = _get_stage_dir()
        path = os.path.join(dir_path, filename)
        if not os.path.exists(path): return False
        with open(path, 'r') as f:
            data = json.load(f)
        data['stage'] = stage
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        return True
