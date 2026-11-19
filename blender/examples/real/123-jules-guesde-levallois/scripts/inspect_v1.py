import bpy, sys, json, collections
L='/tmp/claude-0/-home-user-menu-weekend/64550aa9-4cba-59e3-8992-8569f55e00f3/scratchpad/levallois'
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=f'{L}/old/levallois.gltf')
objs=[o for o in bpy.data.objects if o.type=='MESH']
print('objects', len(objs), 'materials', len(bpy.data.materials), 'collections', [c.name for c in bpy.data.collections])
from mathutils import Vector
import math
lo=Vector((1e9,)*3); hi=Vector((-1e9,)*3)
rows=[]
for o in objs:
    pts=[o.matrix_world @ Vector(c) for c in o.bound_box]
    mn=Vector(min(p[i] for p in pts) for i in range(3)); mx=Vector(max(p[i] for p in pts) for i in range(3))
    lo=Vector(min(a,b) for a,b in zip(lo,mn)); hi=Vector(max(a,b) for a,b in zip(hi,mx))
    rows.append((o.name, len(o.data.polygons), [m.name if m else None for m in o.data.materials], [round(c,1) for c in mn], [round(c,1) for c in mx], o.parent.name if o.parent else None))
print('bounds', [round(c,1) for c in lo], [round(c,1) for c in hi])
rows.sort(key=lambda r:-r[1])
for r in rows[:80]: print(r)
print('--- parents', collections.Counter(r[5] for r in rows))
print('--- materials', sorted(m.name for m in bpy.data.materials))
print('--- faces total', sum(r[1] for r in rows))
mats={}
for m in bpy.data.materials:
    if m.use_nodes:
        b=next((n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None)
        if b: mats[m.name]=[round(c,3) for c in b.inputs['Base Color'].default_value[:3]]+[round(b.inputs['Roughness'].default_value,2), round(b.inputs['Metallic'].default_value,2), round(b.inputs['Alpha'].default_value,2)]
json.dump({'rows':rows,'mats':mats,'bounds':[list(lo),list(hi)]}, open(f'{L}/inventory.json','w'))
bpy.ops.wm.save_as_mainfile(filepath=f'{L}/old_import.blend')
