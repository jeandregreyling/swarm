"""Acceptance test for the GitHub step (owner 16 Nov 2026): "get github working again ... a good place to get some more tools instead of
creating things from scratch". APEX copies this file to tests/test_hb_references_github.py in its studio_proposal.

reference_lookup with allow_online=True also lists public GitHub repositories (metadata only: name, stars, licence, last push, link),
so HB can find an existing tool before building one. No token is used and no remote code is run."""
import json

from core import hb_references as refs

SAMPLE = {'items': [
    {'full_name': 'octo/payroll-tools', 'description': 'Payroll helpers', 'stargazers_count': 120, 'html_url': 'https://github.com/octo/payroll-tools',
     'license': {'spdx_id': 'MIT'}, 'pushed_at': '2026-10-01T00:00:00Z', 'archived': False},
    {'full_name': 'old/dead-tool', 'description': None, 'stargazers_count': 3, 'html_url': 'https://github.com/old/dead-tool',
     'license': None, 'pushed_at': '2019-01-01T00:00:00Z', 'archived': True}]}


def test_github_repositories_returns_metadata_only():
    asked = []

    def fetch(url):
        asked.append(url)
        return json.dumps(SAMPLE)
    items = refs.github_repositories('sap payroll', limit=5, fetch=fetch)
    assert asked and asked[0].startswith('https://api.github.com/search/repositories?q=sap+payroll')
    assert items[0] == {'kind': 'github', 'repo': 'octo/payroll-tools', 'description': 'Payroll helpers', 'stars': 120,
                        'license': 'MIT', 'pushed_at': '2026-10-01', 'url': 'https://github.com/octo/payroll-tools'}
    assert [i['repo'] for i in items] == ['octo/payroll-tools']          # archived repositories are left out


def test_github_failure_is_an_empty_list_not_a_crash():
    def fetch(url):
        raise OSError('offline')
    assert refs.github_repositories('anything', fetch=fetch) == []


def test_lookup_online_includes_github(monkeypatch):
    import core.apex_knowledge as k
    import huggingface_hub
    monkeypatch.setattr(k, 'search', lambda q: {'items': []})

    class NoHub:
        def __init__(self, token=False):
            pass

        def list_datasets(self, search, limit):
            return []

        def list_models(self, search, limit):
            return []
    monkeypatch.setattr(huggingface_hub, 'HfApi', NoHub)
    monkeypatch.setattr(refs, 'github_repositories', lambda q, limit=5, fetch=None: [{'kind': 'github', 'repo': 'octo/payroll-tools'}])
    out = refs.lookup('sap payroll', allow_online=True)
    assert out['online_queried'] is True
    assert {'kind': 'github', 'repo': 'octo/payroll-tools'} in out['repositories']
