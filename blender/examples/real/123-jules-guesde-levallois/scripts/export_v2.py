import bpy, os
L='/tmp/claude-0/-home-user-menu-weekend/64550aa9-4cba-59e3-8992-8569f55e00f3/scratchpad/levallois'
bpy.ops.wm.open_mainfile(filepath=f'{L}/v2.blend')
# deux fichiers : extérieur (chargé d'abord) et intérieurs (mobilier, cloisons, plafonds…)
def is_interior(n):
    return n[0]=='N' and any(t in n for t in ('_mob','_clo','_plinthe','_vert','_siege','_cadre','_porte','_plafond','_sol','_rampe','_fp','_mur','_poteau','_convect','_ceram','_inox','_moquette','_parquet','_lames','_bois','_pied','_terre','_bac','_dalle'))
for o in bpy.data.objects: o.select_set(False)
groups={'ext':[o for o in bpy.data.objects if o.type=='MESH' and not is_interior(o.name)], 'int':[o for o in bpy.data.objects if o.type=='MESH' and is_interior(o.name)]}
for g,objs in groups.items():
    for o in bpy.data.objects: o.select_set(False)
    for o in objs: o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=f'{L}/v2/le123_{g}.glb', export_format='GLB', use_selection=True, export_apply=True, export_yup=True, export_image_format='NONE', export_cameras=False, export_lights=False, export_animations=False, export_skins=False, export_morph=False, export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=6, export_draco_position_quantization=14, export_draco_normal_quantization=10, export_draco_texcoord_quantization=12)
    print(g, len(objs), 'objets', os.path.getsize(f'{L}/v2/le123_{g}.glb')//1024, 'KB')
print('EXPORT_DONE')
