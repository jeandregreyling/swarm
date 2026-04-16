"""
lib/knowledge/categories.py — Knowledge Library category tree.

Defines the hierarchical category structure for the Library.
Each category has an id, label, icon, and optional subcategories.
Agents use category ids to scope their knowledge lookups.
"""

# ── Category Tree ──────────────────────────────────────────────────────────────

CATEGORIES = [
    {
        'id': 'sap_corner',
        'label': 'SAP Corner',
        'icon': '🏢',
        'description': 'SAP HCM, Payroll, ABAP, EC/ECP — consulting knowledge pool',
        'subcategories': [
            {'id': 'payroll_au',    'label': 'Payroll (Australia)',   'icon': '🦘'},
            {'id': 'payroll_global','label': 'Payroll (Global)',      'icon': '🌐'},
            {'id': 'abap',         'label': 'ABAP',                  'icon': '⌨️'},
            {'id': 'ec_ecp',       'label': 'EC / ECP',              'icon': '☁️'},
            {'id': 'onboarding_sap','label': 'SAP Onboarding',       'icon': '🚀'},
            {'id': 'schemas_pcr',  'label': 'Schemas & PCRs',        'icon': '📐'},
            {'id': 'functions_ops','label': 'Functions & Operations', 'icon': '⚙️'},
            {'id': 'bapis',        'label': 'BAPIs & Interfaces',    'icon': '🔌'},
            {'id': 'infotypes',    'label': 'Infotypes',             'icon': '📋'},
            {'id': 'sap_notes',    'label': 'SAP Notes & OSS',       'icon': '📝'},
            {'id': 'wage_types',   'label': 'Wage Types',            'icon': '💰'},
            {'id': 'features',     'label': 'Features (PE03)',       'icon': '🔧'},
        ],
    },
    {
        'id': 'programming',
        'label': 'Programming',
        'icon': '💻',
        'description': 'Best practices, patterns, and coding standards',
        'subcategories': [
            {'id': 'python',       'label': 'Python',                'icon': '🐍'},
            {'id': 'abap_dev',     'label': 'ABAP Development',      'icon': '⌨️'},
            {'id': 'javascript',   'label': 'JavaScript / Web',      'icon': '🌍'},
            {'id': 'design_patterns','label': 'Design Patterns',     'icon': '🏗️'},
            {'id': 'testing',      'label': 'Testing Strategies',    'icon': '🧪'},
            {'id': 'code_review',  'label': 'Code Review',           'icon': '👁️'},
            {'id': 'git_workflow', 'label': 'Git Workflow',           'icon': '🔀'},
        ],
    },
    {
        'id': 'fridays',
        'label': 'Fridays / Swarm',
        'icon': '🤖',
        'description': 'Swarm architecture, agent guides, system reference',
        'subcategories': [
            {'id': 'architecture', 'label': 'Architecture',          'icon': '🏛️'},
            {'id': 'agent_guides', 'label': 'Agent Guides',          'icon': '📖'},
            {'id': 'deployment',   'label': 'Deployment',            'icon': '📦'},
            {'id': 'troubleshoot', 'label': 'Troubleshooting',       'icon': '🔍'},
        ],
    },
    {
        'id': 'general',
        'label': 'General',
        'icon': '📚',
        'description': 'Uncategorised documents, emails, and notes',
        'subcategories': [
            {'id': 'consulting',   'label': 'Consulting',            'icon': '💼'},
            {'id': 'process',      'label': 'Process / Project',     'icon': '📊'},
            {'id': 'reference',    'label': 'Reference',             'icon': '📎'},
        ],
    },
]

# ── Lookup helpers ─────────────────────────────────────────────────────────────

_FLAT = {}
for cat in CATEGORIES:
    _FLAT[cat['id']] = cat
    for sub in cat.get('subcategories', []):
        _FLAT[sub['id']] = sub
        sub['_parent'] = cat['id']


def get_category(cat_id):
    """Return category dict or None."""
    return _FLAT.get(cat_id)


def parent_of(sub_id):
    """Return parent category id for a subcategory, or None."""
    sub = _FLAT.get(sub_id)
    if sub:
        return sub.get('_parent')
    return None


def all_ids_for(cat_id):
    """Return set of ids: the category + all its subcategory ids."""
    cat = get_category(cat_id)
    if not cat:
        return set()
    ids = {cat_id}
    for sub in cat.get('subcategories', []):
        ids.add(sub['id'])
    return ids


def tree_json():
    """Return the full category tree as JSON-serialisable list (no internal keys)."""
    result = []
    for cat in CATEGORIES:
        c = {
            'id': cat['id'],
            'label': cat['label'],
            'icon': cat['icon'],
            'description': cat['description'],
            'subcategories': [
                {'id': s['id'], 'label': s['label'], 'icon': s['icon']}
                for s in cat.get('subcategories', [])
            ],
        }
        result.append(c)
    return result


# ── Tag-to-category mapping ───────────────────────────────────────────────────
# Maps legacy _SAP_TAGS onto the new category system for migration

TAG_TO_CATEGORY = {
    'sap_hcm':     ('sap_corner', None),
    'abap':        ('sap_corner', 'abap'),
    'payroll':     ('sap_corner', 'payroll_au'),
    'sap_note':    ('sap_corner', 'sap_notes'),
    'ecp':         ('sap_corner', 'ec_ecp'),
    'btp':         ('sap_corner', None),
    'schema':      ('sap_corner', 'schemas_pcr'),
    'pcr':         ('sap_corner', 'schemas_pcr'),
    'infotype':    ('sap_corner', 'infotypes'),
    'consulting':  ('general', 'consulting'),
    'client':      ('general', 'consulting'),
    'legal':       ('general', 'reference'),
    'process':     ('general', 'process'),
    'project':     ('general', 'process'),
}


def infer_category_from_tags(tags):
    """Given a list of legacy tags, return (category, subcategory) or (None, None)."""
    for tag in (tags or []):
        if tag in TAG_TO_CATEGORY:
            return TAG_TO_CATEGORY[tag]
    return (None, None)
