"""13 Nov: practice 11's patch copied a block into home-chat.js and broke main chat. JS patches must parse before they land."""
from core.tool_approval import _javascript_problem


def test_valid_javascript_passes():
    assert _javascript_problem('let a = 1;\nfunction f() { return a; }\n') is None


def test_redeclared_variable_is_refused_with_the_reason():
    problem = _javascript_problem('let a = 1;\nlet a = 2;\n')
    assert problem and 'already been declared' in problem
