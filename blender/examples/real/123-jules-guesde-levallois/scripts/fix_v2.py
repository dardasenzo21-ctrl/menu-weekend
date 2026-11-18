import bpy
L='/tmp/claude-0/-home-user-menu-weekend/64550aa9-4cba-59e3-8992-8569f55e00f3/scratchpad/levallois'
bpy.ops.wm.open_mainfile(filepath=f'{L}/v2.blend')
o=bpy.data.objects.get('Rue_cour')
if o: bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.wm.save_mainfile()
print('FIX_DONE')
