import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parents[1] / 'utils')]

from agents.seven import seven_agent
from utils import qbit_bridge
from utils.local_runtime_policy import normalize_read_only_response


def test_envelope_with_trailing_witness_footer_is_not_double_wrapped():
    raw = '{\n "kind": "analysis",\n "summary": "Found it",\n "evidence": []\n}\n\n— Seven\'s witness —\n callouts: none'
    payload = json.loads(normalize_read_only_response('seven', raw))
    assert payload['kind'] == 'analysis'
    assert payload['summary'].startswith('Found it\n\n— Seven')
    assert '"kind"' not in payload['summary']


def test_fenced_envelope_and_plain_numbers_parse_safely():
    fenced = json.loads(normalize_read_only_response('seven', '```json\n{"kind":"draft","summary":"ok"}\n```'))
    assert (fenced['kind'], fenced['summary']) == ('draft', 'ok')
    plain = json.loads(normalize_read_only_response('seven', '3 torrents are downloading'))
    assert plain['summary'] == '3 torrents are downloading'


class FakeClient:
    closed = False

    def call(self, endpoint):
        return SimpleNamespace(text='v5.3.0\n')

    def json(self, endpoint, **kwargs):
        if endpoint == 'transfer/info':
            return {'connection_status': 'connected', 'dht_nodes': 300, 'dl_info_speed': 2048, 'up_info_speed': 0}
        return [
            {'name': 'Ubuntu ISO', 'progress': 0.5, 'size': 2 * 1024 ** 3, 'state': 'downloading',
             'dlspeed': 1024 ** 2, 'num_seeds': 12, 'num_complete': 90, 'eta': 3700},
            {'name': 'Done file', 'progress': 1, 'size': 10, 'state': 'stalledUP'},
        ]

    def close(self):
        FakeClient.closed = True


def test_report_lists_active_torrents_from_live_api():
    report = qbit_bridge.format_downloads_report(qbit_bridge.downloads_snapshot(FakeClient))
    assert 'qBittorrent v5.3.0 is running' in report
    assert '1 of 2 torrent(s) still downloading' in report
    assert '- Ubuntu ISO — 50.0% of 2.0 GiB, downloading, ↓ 1.0 MiB/s, seeds 12/90, ETA 1h 1m' in report
    assert 'Done file' not in report
    assert FakeClient.closed


def test_report_when_qbittorrent_is_closed():
    def unavailable():
        raise qbit_bridge.QbitError('Cannot reach qBittorrent.')
    report = qbit_bridge.format_downloads_report(qbit_bridge.downloads_snapshot(unavailable))
    assert 'not reachable' in report and 'Open qBittorrent' in report


def test_seven_answers_download_questions_from_snapshot(monkeypatch):
    monkeypatch.setattr(qbit_bridge, 'downloads_snapshot', lambda: {'ok': False, 'error': 'closed'})
    answer = seven_agent._downloads_answer('open qbittorrent and tell me what is downloading?')
    assert 'not reachable' in answer and 'cannot launch qBittorrent myself' in answer
    assert seven_agent._downloads_answer('download the SAP newsletter') is None
    assert seven_agent._downloads_answer('hello seven') is None
