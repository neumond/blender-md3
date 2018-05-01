from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

import bpy


@pytest.fixture(scope='session')
def tmpdir():
    with TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def testdir():
    return Path(__file__).parent


@pytest.fixture
def simple_blend(testdir):
    bpy.ops.wm.open_mainfile(filepath=str(testdir / 'simple.blend'))
