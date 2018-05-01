import bpy
from io_scene_md3.export_md3 import MD3Exporter


def test_export_doesnt_crash(tmpdir, simple_blend):
    fname = tmpdir / 'output.md3'
    MD3Exporter(bpy.context)(str(fname))
    assert fname.exists()
    assert fname.stat().st_size > 0
