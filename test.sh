export BLENDER_USER_SCRIPTS=.
export PYTHONPATH=.
PARAMS=$(python -c 'from sys import argv; print(repr(argv[1:]))' $@)
blender --factory-startup -noaudio --background --python-exit-code 1 --python-expr "import pytest; pytest.main($PARAMS)"
