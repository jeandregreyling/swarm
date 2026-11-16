"""Practice 55 (owner 14 Nov): the gatekeeper - the GPU model keeps the card; a second model joins only when it fits, else RAM, else it waits."""
from pathlib import Path
import core.hb_gatekeeper as g


def test_practice_55_cpu_models_and_an_empty_card_load_as_registered():
    assert g.decide(14.3, False, 16.0, 11.0, 40.0)['placement'] == 'cpu'
    assert g.decide(9.0, True, 16.0, 0.6, 40.0)['placement'] == 'gpu'              # empty card
    assert g.decide(19.9, True, 16.0, 0.6, 40.0)['placement'] == 'gpu'             # bigger than the card, card empty: spreads as today
    assert g.decide(9.0, True, None, None, 40.0)['placement'] == 'gpu'             # card unreadable: as registered


def test_practice_55_busy_card_only_takes_what_fits_with_margin():
    assert g.decide(2.5, True, 16.0, 11.0, 40.0)['placement'] == 'gpu'             # 2.5 + 1.5 <= 5 free
    squeezed = g.decide(4.7, True, 16.0, 11.0, 40.0)                               # 4.7 + 1.5 > 5 free: this crashed the card
    assert squeezed['placement'] == 'cpu' and 'leaves the card to the GPU model' in squeezed['why']
    assert g.decide(4.7, True, 16.0, 11.0, 6.0)['placement'] == 'refuse'           # no room in RAM either: wait, do not crash


def test_practice_55_loader_asks_the_gatekeeper_before_loading():
    src = (Path(__file__).resolve().parents[1] / 'core/seven_llm/llama_server.py').read_text()
    i = src.index('hb_gatekeeper.decide(')
    block = src[i - 300:i + 900]
    assert 'opts["ngl"] = 0' in block and 'raise RuntimeError("HB gatekeeper: "' in block
    assert src.index('charge = _admit(model, state)') < i < src.index('"--alias", model,')
