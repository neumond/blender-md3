OUTFILE=blender_md3.zip
[ -f $OUTFILE ] && rm $OUTFILE
zip $OUTFILE -r io_scene_md3/ -i '*.py'
