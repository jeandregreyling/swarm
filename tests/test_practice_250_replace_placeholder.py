"""Practice 250: a placeholder test can be replaced by a real one; real definitions stay protected."""
import ast

from core.tool_approval import placeholder_definition


def _fn(src):
    return ast.parse(src).body[0]


def test_placeholders_are_recognised():
    assert placeholder_definition(_fn('def test_placeholder():\n    assert True\n'))
    assert placeholder_definition(_fn('def test_x():\n    """later"""\n    pass\n'))
    assert placeholder_definition(_fn('@pytest.mark.skip(reason="later")\ndef test_x():\n    assert 1 == 2\n'))


def test_real_tests_and_code_are_not_placeholders():
    assert not placeholder_definition(_fn('def test_x():\n    assert add(1, 2) == 3\n'))
    assert not placeholder_definition(_fn('def helper(a):\n    return a + 1\n'))
