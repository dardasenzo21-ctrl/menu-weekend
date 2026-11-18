"""Textures PBR tuilables (albedo / normal / roughness) cuites avec Cycles à partir de matériaux procéduraux."""
import bpy, os, math
OUT='/tmp/claude-0/-home-user-menu-weekend/64550aa9-4cba-59e3-8992-8569f55e00f3/scratchpad/levallois/tex'
bpy.ops.wm.read_factory_settings(use_empty=True)
sc=bpy.context.scene; sc.render.engine='CYCLES'; sc.cycles.samples=32; sc.cycles.device='CPU'
sc.render.bake.use_selected_to_active=False; sc.render.bake.margin=0
bpy.ops.mesh.primitive_plane_add(size=1); plane=bpy.context.object

def node(nt, t, **kw):
    n=nt.nodes.new(t)
    for k,v in kw.items(): setattr(n,k,v)
    return n

def brick_like(nt, links, scale_x, scale_y, mortar_w, color1, color2, mortar_col, noise_scale, bias=0.0):
    """Appareillage : Brick Texture + bruit sur la couleur, retourne (color socket, height socket)."""
    co=node(nt,'ShaderNodeTexCoord'); mp=node(nt,'ShaderNodeMapping'); mp.inputs['Scale'].default_value=(scale_x, scale_y, 1)
    links.new(co.outputs['UV'], mp.inputs['Vector'])
    br=node(nt,'ShaderNodeTexBrick'); br.offset=0.5; br.offset_frequency=2; br.squash=1.0; br.squash_frequency=2
    br.inputs['Scale'].default_value=1.0; br.inputs['Mortar Size'].default_value=mortar_w; br.inputs['Color1'].default_value=color1; br.inputs['Color2'].default_value=color2; br.inputs['Mortar'].default_value=mortar_col
    br.inputs['Bias'].default_value=bias; br.inputs['Brick Width'].default_value=1.0; br.inputs['Row Height'].default_value=1.0
    links.new(mp.outputs['Vector'], br.inputs['Vector'])
    nz=node(nt,'ShaderNodeTexNoise'); nz.inputs['Scale'].default_value=noise_scale; nz.inputs['Detail'].default_value=6; nz.inputs['Roughness'].default_value=0.6
    links.new(co.outputs['UV'], nz.inputs['Vector'])
    mix=node(nt,'ShaderNodeMix'); mix.data_type='RGBA'; mix.blend_type='MULTIPLY'; mix.inputs['Factor'].default_value=0.35
    links.new(br.outputs['Color'], mix.inputs[6]); links.new(nz.outputs['Color'], mix.inputs[7])
    # hauteur = 1 - mortier + grain
    hm=node(nt,'ShaderNodeMath'); hm.operation='SUBTRACT'; hm.inputs[0].default_value=1.0; links.new(br.outputs['Fac'], hm.inputs[1])
    hn=node(nt,'ShaderNodeMath'); hn.operation='MULTIPLY_ADD'; hn.inputs[1].default_value=0.08; links.new(nz.outputs['Fac'], hn.inputs[0]); links.new(hm.outputs[0], hn.inputs[2])
    return mix.outputs[2], hn.outputs[0], nz

def make_material(name, kind):
    m=bpy.data.materials.new(name); m.use_nodes=True; nt=m.node_tree; links=nt.links
    bsdf=next(n for n in nt.nodes if n.type=='BSDF_PRINCIPLED')
    if kind=='pierre':   # pierre de taille beige, panneaux 1,2 m × 0,6 m (texture = 2,4 m × 1,2 m)
        col,h,nz=brick_like(nt,links,2,2,0.012,(0.80,0.74,0.62,1),(0.76,0.70,0.58,1),(0.55,0.50,0.42,1),9.0)
        rough=0.72
    elif kind=='trottoir':  # dalles béton 40 × 40 (texture 2 m)
        col,h,nz=brick_like(nt,links,5,5,0.02,(0.60,0.60,0.57,1),(0.55,0.55,0.52,1),(0.35,0.35,0.33,1),14.0)
        rough=0.9
    elif kind=='chaussee':  # enrobé
        co=node(nt,'ShaderNodeTexCoord'); nz=node(nt,'ShaderNodeTexNoise'); nz.inputs['Scale'].default_value=40; nz.inputs['Detail'].default_value=8; nz.inputs['Roughness'].default_value=0.7
        links.new(co.outputs['UV'], nz.inputs['Vector'])
        vo=node(nt,'ShaderNodeTexVoronoi'); vo.inputs['Scale'].default_value=120; links.new(co.outputs['UV'], vo.inputs['Vector'])
        rgb=node(nt,'ShaderNodeValToRGB'); rgb.color_ramp.elements[0].color=(0.16,0.16,0.17,1); rgb.color_ramp.elements[1].color=(0.30,0.30,0.31,1)
        mixf=node(nt,'ShaderNodeMath'); mixf.operation='MULTIPLY_ADD'; mixf.inputs[1].default_value=0.5; links.new(nz.outputs['Fac'], mixf.inputs[0]); links.new(vo.outputs['Distance'], mixf.inputs[2])
        links.new(mixf.outputs[0], rgb.inputs['Fac'])
        col=rgb.outputs['Color']; h=mixf.outputs[0]; rough=0.95
    elif kind=='gravier':
        co=node(nt,'ShaderNodeTexCoord'); vo=node(nt,'ShaderNodeTexVoronoi'); vo.inputs['Scale'].default_value=90; vo.feature='SMOOTH_F1'; links.new(co.outputs['UV'], vo.inputs['Vector'])
        nz=node(nt,'ShaderNodeTexNoise'); nz.inputs['Scale'].default_value=30; links.new(co.outputs['UV'], nz.inputs['Vector'])
        rgb=node(nt,'ShaderNodeValToRGB'); rgb.color_ramp.elements[0].color=(0.62,0.60,0.55,1); rgb.color_ramp.elements[1].color=(0.86,0.84,0.78,1)
        links.new(vo.outputs['Distance'], rgb.inputs['Fac'])
        mix=node(nt,'ShaderNodeMix'); mix.data_type='RGBA'; mix.blend_type='MULTIPLY'; mix.inputs['Factor'].default_value=0.3; links.new(rgb.outputs['Color'], mix.inputs[6]); links.new(nz.outputs['Color'], mix.inputs[7])
        col=mix.outputs[2]; h=vo.outputs['Distance']; rough=0.9
    elif kind=='enduit':
        co=node(nt,'ShaderNodeTexCoord'); nz=node(nt,'ShaderNodeTexNoise'); nz.inputs['Scale'].default_value=25; nz.inputs['Detail'].default_value=9; nz.inputs['Roughness'].default_value=0.75
        links.new(co.outputs['UV'], nz.inputs['Vector'])
        nz2=node(nt,'ShaderNodeTexNoise'); nz2.inputs['Scale'].default_value=3; nz2.inputs['Detail'].default_value=3; links.new(co.outputs['UV'], nz2.inputs['Vector'])
        rgb=node(nt,'ShaderNodeValToRGB'); rgb.color_ramp.elements[0].color=(0.74,0.74,0.71,1); rgb.color_ramp.elements[1].color=(0.90,0.90,0.87,1)
        mm=node(nt,'ShaderNodeMath'); mm.operation='MULTIPLY_ADD'; mm.inputs[1].default_value=0.5; links.new(nz.outputs['Fac'], mm.inputs[0]); links.new(nz2.outputs['Fac'], mm.inputs[2])
        links.new(mm.outputs[0], rgb.inputs['Fac']); col=rgb.outputs['Color']; h=nz.outputs['Fac']; rough=0.85
    elif kind=='zinc':   # bacs à joints debout tous les 0,5 m (texture 2 m)
        col,h,nz=brick_like(nt,links,4,1,0.03,(0.48,0.50,0.53,1),(0.45,0.47,0.50,1),(0.30,0.31,0.33,1),20.0)
        rough=0.45
    elif kind=='beton_lave':  # béton lavé (agrégats)
        co=node(nt,'ShaderNodeTexCoord'); vo=node(nt,'ShaderNodeTexVoronoi'); vo.inputs['Scale'].default_value=160; links.new(co.outputs['UV'], vo.inputs['Vector'])
        rgb=node(nt,'ShaderNodeValToRGB'); rgb.color_ramp.elements[0].color=(0.70,0.64,0.52,1); rgb.color_ramp.elements[1].color=(0.86,0.82,0.74,1); rgb.color_ramp.elements[0].position=0.15
        links.new(vo.outputs['Distance'], rgb.inputs['Fac']); col=rgb.outputs['Color']; h=vo.outputs['Distance']; rough=0.8
    elif kind=='moquette':
        col,h,nz=brick_like(nt,links,4,4,0.004,(0.42,0.43,0.46,1),(0.38,0.39,0.42,1),(0.30,0.30,0.33,1),60.0)
        rough=0.95
    elif kind=='faux_plafond':
        col,h,nz=brick_like(nt,links,4,4,0.012,(0.93,0.93,0.91,1),(0.91,0.91,0.89,1),(0.70,0.70,0.68,1),50.0)
        rough=0.8
    links.new(col, bsdf.inputs['Base Color'])
    bump=node(nt,'ShaderNodeBump'); bump.inputs['Strength'].default_value=0.6; bump.inputs['Distance'].default_value=0.02
    links.new(h, bump.inputs['Height']); links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    bsdf.inputs['Roughness'].default_value=rough
    return m

def bake(name, kind, res=1024):
    m=make_material(name, kind); plane.data.materials.clear(); plane.data.materials.append(m)
    nt=m.node_tree
    for btype, suffix, cs in (('DIFFUSE','albedo','sRGB'),('NORMAL','normal','Non-Color'),('ROUGHNESS','rough','Non-Color')):
        img=bpy.data.images.new(f'{name}_{suffix}', res, res, alpha=False); img.colorspace_settings.name=cs
        tex=nt.nodes.new('ShaderNodeTexImage'); tex.image=img; nt.nodes.active=tex
        sc.render.bake.use_pass_direct=False; sc.render.bake.use_pass_indirect=False; sc.render.bake.use_pass_color=True
        bpy.ops.object.bake(type=btype, margin=0, use_clear=True)
        img.filepath_raw=f'{OUT}/{name}_{suffix}.png'; img.file_format='PNG'; img.save()
        nt.nodes.remove(tex)
    print('BAKED', name)

for name, kind in [('pierre','pierre'),('trottoir','trottoir'),('chaussee','chaussee'),('gravier','gravier'),('enduit','enduit'),('zinc','zinc'),('beton_lave','beton_lave'),('moquette','moquette'),('faux_plafond','faux_plafond')]:
    bake(name, kind)
print('BAKE_DONE')
