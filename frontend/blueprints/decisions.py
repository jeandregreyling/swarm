"""decisions.py — Decisions & Timeline routes"""
from flask import Blueprint, request, Response, jsonify, send_file
from services import *

decisions_bp = Blueprint('decisions', __name__)

@decisions_bp.route('/api/decisions')
def api_decisions():
    """
    List all decisions from the Time Wizard decision index.
    Returns decision metadata from sandpits/twelve/DECISION_INDEX.md
    """
    import os
    import re
    
    index_path = str(SWARM_ROOT / 'sandpits' / 'twelve' / 'DECISION_INDEX.md')
    
    if not os.path.exists(index_path):
        return jsonify({'decisions': [], 'total': 0, 'message': 'No decisions logged yet'})
    
    try:
        with open(index_path, 'r') as f:
            content = f.read()
        
        # Parse decisions from markdown table 
        # | ID | Title | Status | Proposed | Category | Impact |
        lines = content.split('\n')
        decisions = []
        
        for line in lines:
            if line.startswith('|') and 'Title' not in line and '---' not in line and line.count('|') >= 5:
                parts = [p.strip() for p in line.split('|')[1:-1]]
                if len(parts) >= 5:
                    decisions.append({
                        'id': parts[0],
                        'title': parts[1],
                        'status': parts[2],
                        'proposed': parts[3],
                        'category': parts[4] if len(parts) > 4 else '',
                        'impact': parts[5] if len(parts) > 5 else ''
                    })
        
        return jsonify({
            'decisions': decisions,
            'total': len(decisions),
            'last_updated': datetime.now(timezone.utc).isoformat() + 'Z'
        })
    
    except Exception as e:
        return jsonify({'error': str(e), 'decisions': []}), 500



@decisions_bp.route('/api/decisions/<decision_id>')
def api_decision_detail(decision_id):
    """
    Get full details of a specific decision.
    Reads from sandpits/twelve/proposals/DECISION-NNN-*.md
    """
    import os
    import glob
    
    proposal_dir = str(SWARM_ROOT / 'sandpits' / 'twelve' / 'proposals')
    
    # Find the proposal file — decision_id is already full e.g. "DECISION-001"
    pattern = f'{proposal_dir}/{decision_id}-*.md'
    matches = glob.glob(pattern)
    # Fallback: bare numeric id e.g. "001"
    if not matches:
        pattern = f'{proposal_dir}/DECISION-{decision_id}-*.md'
        matches = glob.glob(pattern)

    if not matches:
        return jsonify({'error': f'Decision {decision_id} not found'}), 404

    try:
        with open(matches[0], 'r') as f:
            content = f.read()

        # Parse markdown decision
        lines = content.split('\n')
        decision_data = {
            'id': decision_id,
            'file': os.path.basename(matches[0]),
            'content': content,
            'sections': {}
        }

        # Extract flat fields from well-known header lines
        for line in lines[:12]:
            if line.startswith('# '):
                decision_data['title'] = line.lstrip('# ').strip()
            if line.startswith('**Status**:'):
                decision_data['status'] = line.split(':', 1)[1].strip().strip('*')
            if line.startswith('**Agent**:'):
                decision_data['agent'] = line.split(':', 1)[1].strip().strip('*')

        current_section = None
        for line in lines:
            if line.startswith('## '):
                current_section = line.replace('## ', '').strip()
                decision_data['sections'][current_section] = []
            elif current_section and line.strip():
                decision_data['sections'][current_section].append(line)

        # Map sections to flat fields expected by the UI
        sec = decision_data['sections']
        decision_data['issue']      = '\n'.join(sec.get('Issue', sec.get('Problem', [])))
        decision_data['solution']   = '\n'.join(sec.get('Proposed Solution', sec.get('Solution', [])))
        decision_data['scope']      = '\n'.join(sec.get('Scope', sec.get('Impact', [])))
        decision_data['risks']      = '\n'.join(sec.get('Risks', sec.get('Risk', [])))
        decision_data['next_steps'] = '\n'.join(sec.get('Next Steps', sec.get('Actions', [])))

        return jsonify(decision_data)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500



@decisions_bp.route('/api/timeline')
def api_decision_timeline():
    """
    Get chronological timeline of all decisions.
    Useful for audit trail and dependency visualization.
    """
    import os
    import glob
    from datetime import datetime as dt
    
    proposal_dir = str(SWARM_ROOT / 'sandpits' / 'twelve' / 'proposals')
    timeline = []
    
    # Find all decision files
    decision_files = glob.glob(f'{proposal_dir}/DECISION-*.md')
    
    for file_path in sorted(decision_files):
        try:
            with open(file_path, 'r') as f:
                content = f.read()
            
            # Extract metadata from top of file
            lines = content.split('\n')
            entry = {
                'file': os.path.basename(file_path),
                'decision_id': os.path.basename(file_path).split('-')[1],
                'proposed': None,
                'status': 'UNKNOWN',
                'title': ''
            }
            
            for line in lines[:20]:
                if line.startswith('# Decision'):
                    entry['title'] = line.replace('# Decision', '').strip()
                elif line.startswith('**Status**:'):
                    entry['status'] = line.split('**Status**:')[1].strip().split('|')[0].strip()
                elif line.startswith('**Proposed**:'):
                    entry['proposed'] = line.split('**Proposed**:')[1].strip()
            
            timeline.append(entry)
        
        except Exception as e:
            print(f'[Time Wizard] Error parsing {file_path}: {e}')
    
    # Sort by proposed date
    timeline.sort(key=lambda x: x['proposed'] or '', reverse=True)
    
    return jsonify({
        'timeline': timeline,
        'total': len(timeline),
        'last_update': datetime.now(timezone.utc).isoformat() + 'Z'
    })



