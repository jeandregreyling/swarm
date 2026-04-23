"""core.knowledge — Knowledge Center package.

Session 29.2: Knowledge Center becomes the owner of test-lab scripts,
change-run history, and (in later sessions) skill/agent docs + search.

For now this module is a thin re-export layer over ``core.testlab_registry``
so we can land the Knowledge Center API surface without duplicating the
registry. A future session can promote the data here and retire the
``testlab_registry`` module once all callers are on ``core.knowledge``.
"""
from . import scripts  # noqa: F401

__all__ = ['scripts']
