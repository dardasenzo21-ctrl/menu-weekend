"""Le 123 Levallois — v2 : maquette enrichie (voisins IGN, orthophoto, meneaux, vitrages inclinés, voitures, grille, UV textures)."""
import bpy, bmesh, json, math, os, random, sys
sys.path.insert(0,'/home/user/menu-weekend/blender/src'); sys.path.append('/home/user/menu-weekend/blender/.venv/lib/python3.13/site-packages')
from mathutils import Vector, Matrix
from blender_buildings import geo, geometry
from blender_buildings.builder import build_building, MeshBuilder
from blender_buildings.materials import get_material
L='/tmp/claude-0/-home-user-menu-weekend/64550aa9-4cba-59e3-8992-8569f55e00f3/scratchpad/levallois'
OUT=f'{L}/v2'; os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=f'{L}/old_import.blend')
rng=random.Random(123)

# ---------- 0. transformations appliquées (les objets importés ont des échelles ≈ 24) ----------
for o in bpy.data.objects:
    if o.type=='MESH':
        o.select_set(True)
bpy.context.view_layer.objects.active=next(o for o in bpy.data.objects if o.type=='MESH')
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
for o in bpy.data.objects: o.select_set(False)
def M(name): return bpy.data.materials.get(name)

# ---------- 1. repère monde (IGN, nord en haut) -> maquette ----------
D=(0.4851523732043603, -0.874429628257287)       # axe de la rue Jules Guesde (IGN), = +Y maquette
RX=(D[1], -D[0])                                  # +X maquette en coordonnées monde
C=(-19.43, -17.43)                                # translation : façade sur rue calée sur les emprises cadastrales
def w2m(p):   # monde -> maquette
    x,y=p[0]-C[0], p[1]-C[1]
    return (x*RX[0]+y*RX[1], x*D[0]+y*D[1])
def m2w(p):
    return (RX[0]*p[0]+D[0]*p[1]+C[0], RX[1]*p[0]+D[1]*p[1]+C[1])

# ---------- 2. voisins IGN (vrais gabarits) à la place des volumes plats ----------
for o in [o for o in bpy.data.objects if o.name.startswith('Voisins')]:
    bpy.data.objects.remove(o, do_unlink=True)
raw=[geo.GeoBuilding.model_validate(x) for x in json.load(open(f'{L}/ign_buildings.json'))]
TARGET_IDS={'batiment.27146194','batiment.27145894','batiment.19237955'}
coll=bpy.data.collections.new('Voisins'); bpy.context.scene.collection.children.link(coll)
PAL=['render_beige','render_white','limestone','render_beige','brick_dark','render_white']
nv=0
for i,b in enumerate(raw):
    if b.id in TARGET_IDS: continue
    ring=[w2m(p) for p in b.ring]
    cx,cy=geometry.centroid(ring)
    if -27<cx<40 and -22<cy<22: continue          # morceaux de l'immeuble lui-même
    if math.hypot(cx,cy)>135: continue
    gb=b.model_copy(update={'ring':ring})
    try:
        spec=geo.building_to_spec(gb, f'Voisins_{nv:03d}', detailed=False, overrides={'facade.material':PAL[i%len(PAL)], 'windows.bay_width': 2.6+0.3*(i%3), 'windows.width':1.1+0.2*(i%2), 'facade.cornice_floors':'top', 'roof.material':'zinc'})
        r=build_building(spec, collection=coll, with_site=False)
        nv+=1
    except Exception as e:
        print('voisin ignoré', b.id, e)
print('voisins construits', nv)

# ---------- 3. orthophoto IGN au sol (260 m, monde) ----------
img=bpy.data.images.load(f'{L}/ortho_levallois.jpg')
mesh=bpy.data.meshes.new('Rue_ortho'); H=130.0
corners=[(-H,-H),(H,-H),(H,H),(-H,H)]
mesh.from_pydata([(*w2m(c),-0.12) for c in corners],[],[[0,1,2,3]])
uv=mesh.uv_layers.new(name='UVMap')
for li,(u,v) in enumerate(((0,0),(1,0),(1,1),(0,1))): uv.data[li].uv=(u,v)
mesh.update()
mo=bpy.data.materials.new('Orthophoto'); mo.use_nodes=True; nt=mo.node_tree
bs=next(n for n in nt.nodes if n.type=='BSDF_PRINCIPLED'); ti=nt.nodes.new('ShaderNodeTexImage'); ti.image=img; nt.links.new(ti.outputs['Color'], bs.inputs['Base Color']); bs.inputs['Roughness'].default_value=0.95
mesh.materials.append(mo)
ortho=bpy.data.objects.new('Rue_ortho', mesh); bpy.context.scene.collection.objects.link(ortho)

# ---------- 4. façade : meneaux, traverses et vitrages inclinés ----------
fer=M('Fer forge')
def box(mb, c, ax_u, ax_n, lu, ln, z0, z1, mat):
    """boîte : centre c (x,y), demi-longueur lu le long de ax_u, demi-épaisseur ln le long de ax_n."""
    pts=[]
    for su,sn in ((-1,-1),(1,-1),(1,1),(-1,1)):
        pts.append((c[0]+ax_u[0]*su*lu+ax_n[0]*sn*ln, c[1]+ax_u[1]*su*lu+ax_n[1]*sn*ln))
    mb.hexahedron([(*p,z0) for p in pts],[(*p,z1) for p in pts], mat)
TILT=0.22
for o in [o for o in bpy.data.objects if o.name.endswith('_vitre') and o.name[0]=='N']:
    lvl=o.name.split('_')[0]
    mb=MeshBuilder(); mb.materials.append('Fer forge')
    m=o.data
    # vitrage incliné : les sommets du bas sortent de TILT le long de la normale
    for p in m.polygons:
        n=p.normal
        if abs(n.z)>0.3: continue
        zs=[m.vertices[i].co.z for i in p.vertices]; zlo,zhi=min(zs),max(zs)
        if zhi-zlo<0.6: continue
        for i in p.vertices:
            v=m.vertices[i]
            if abs(v.co.z-zlo)<0.01 and 'tilt' not in v.keys() if False else abs(v.co.z-zlo)<0.01:
                pass
    # (déplacement des sommets bas, une seule fois par sommet)
    moved=set()
    for p in m.polygons:
        n=p.normal
        if abs(n.z)>0.3: continue
        zs=[m.vertices[i].co.z for i in p.vertices]; zlo,zhi=min(zs),max(zs)
        if zhi-zlo<0.6: continue
        for i in p.vertices:
            if i in moved: continue
            v=m.vertices[i]
            if abs(v.co.z-zlo)<0.01:
                v.co.x+=n.x*TILT; v.co.y+=n.y*TILT; moved.add(i)
    m.update()
    # meneaux sur chaque bande (après inclinaison : on suit la base déplacée)
    done=set()
    for p in m.polygons:
        n=p.normal
        if abs(n.z)>0.3: continue
        zs=[m.vertices[i].co.z for i in p.vertices]; zlo,zhi=min(zs),max(zs)
        if zhi-zlo<0.6: continue
        hv=[m.vertices[i].co for i in p.vertices]
        u=Vector((-n.y,n.x,0)).normalized()
        proj=[(c.x*u.x+c.y*u.y) for c in hv]; umin,umax=min(proj),max(proj)
        key=(round(n.x,1),round(n.y,1),round(umin,1),round(umax,1),round(zlo,1))
        if key in done or umax-umin<0.4: continue
        done.add(key)
        base=next(c for c in hv if abs(c.z-zlo)<0.01); top=next(c for c in hv if abs(c.z-zhi)<0.01)
        # point de référence sur la base (coordonnées u=0)
        b0=Vector((base.x,base.y))-u.xy*(base.x*u.x+base.y*u.y); t0=Vector((top.x,top.y))-u.xy*(top.x*u.x+top.y*u.y)
        nb=max(1, round((umax-umin)/1.35)); step=(umax-umin)/nb
        for k in range(nb+1):
            uu=umin+k*step
            # meneau vertical suivant l'inclinaison : prisme dont la base est décalée
            pb=b0+u.xy*uu; pt=t0+u.xy*uu
            w=0.035; d=0.05
            quad=lambda P: [(P.x+u.x*w-n.x*d,P.y+u.y*w-n.y*d),(P.x+u.x*w+n.x*d,P.y+u.y*w+n.y*d),(P.x-u.x*w+n.x*d,P.y-u.y*w+n.y*d),(P.x-u.x*w-n.x*d,P.y-u.y*w-n.y*d)]
            mb.hexahedron([(*q,zlo-0.02) for q in quad(pb)],[(*q,zhi+0.02) for q in quad(pt)],'Fer forge')
        # traverse basse (appui) et haute
        cu=(umin+umax)/2; lu=(umax-umin)/2+0.02
        for P,z in ((b0,zlo),(t0,zhi)):
            cen=P+u.xy*cu
            box(mb,(cen.x,cen.y),(u.x,u.y),(n.x,n.y),lu,0.06,z-0.04,z+0.04,'Fer forge')
    if mb.faces:
        ob=mb.to_object(f'{lvl}_meneaux', library_materials=False)
print('meneaux ok')

# ---------- 5. voitures garées, grille du square, haie ----------
CARC=[(0.11,0.11,0.12),(0.85,0.85,0.83),(0.5,0.52,0.55),(0.65,0.67,0.7),(0.35,0.12,0.14),(0.18,0.23,0.2),(0.1,0.15,0.3)]
def car(mb, cx, cy, ang, col_idx):
    """Berline simplifiée : caisse basse, capot et coffre inclinés, habitacle vitré, roues cylindriques."""
    ca,sa=math.cos(ang),math.sin(ang)
    def P(x,y): return (cx+x*ca-y*sa, cy+x*sa+y*ca)
    body=f'Carrosserie {col_idx}'
    def prism(bq,tq,mat):
        mb.hexahedron([(*P(x,y),z) for x,y,z in bq],[(*P(x,y),z) for x,y,z in tq],mat)
    W=0.86
    prism([(-2.2,-W,0.32),(2.2,-W,0.32),(2.2,W,0.32),(-2.2,W,0.32)],[(-2.15,-W,0.75),(2.15,-W,0.75),(2.15,W,0.75),(-2.15,W,0.75)],body)           # caisse
    prism([(0.9,-W,0.75),(2.15,-W,0.75),(2.15,W,0.75),(0.9,W,0.75)],[(0.75,-W+0.05,0.95),(2.0,-W+0.05,0.86),(2.0,W-0.05,0.86),(0.75,W-0.05,0.95)],body)   # capot
    prism([(-2.15,-W,0.75),(-1.1,-W,0.75),(-1.1,W,0.75),(-2.15,W,0.75)],[(-2.05,-W+0.05,0.9),(-1.2,-W+0.05,0.95),(-1.2,W-0.05,0.95),(-2.05,W-0.05,0.9)],body)  # coffre
    prism([(-1.2,-W+0.04,0.75),(0.9,-W+0.04,0.75),(0.9,W-0.04,0.75),(-1.2,W-0.04,0.75)],[(-0.85,-W+0.14,1.42),(0.35,-W+0.14,1.42),(0.35,W-0.14,1.42),(-0.85,W-0.14,1.42)],'Vitre voiture')  # habitacle
    prism([(-0.85,-W+0.14,1.42),(0.35,-W+0.14,1.42),(0.35,W-0.14,1.42),(-0.85,W-0.14,1.42)],[(-0.85,-W+0.14,1.47),(0.35,-W+0.14,1.47),(0.35,W-0.14,1.47),(-0.85,W-0.14,1.47)],body)  # toit
    for wx in (-1.4,1.4):
        for wy in (-W,W):
            ring=[(wx+0.32*math.cos(a), wy, 0.32+0.32*math.sin(a)) for a in [k*math.pi/6 for k in range(12)]]
            side=1 if wy>0 else -1
            inner=[(x, wy-side*0.2, z) for x,_,z in ring]
            outer=[(x, wy+side*0.02, z) for x,_,z in ring]
            for k in range(12):
                a,b=outer[k],outer[(k+1)%12]; c,d=inner[(k+1)%12],inner[k]
                mb.face([(*P(a[0],a[1]),a[2]),(*P(b[0],b[1]),b[2]),(*P(c[0],c[1]),c[2]),(*P(d[0],d[1]),d[2])][::side],'Pneu')
            mb.face([(*P(x,y),z) for x,y,z in outer][::side],'Pneu')
cars=MeshBuilder()
y=-40.0
while y<40:
    if rng.random()<0.8:
        car(cars,-29.0,y+2.3,math.pi/2,rng.randrange(len(CARC)))
    y+=5.4+rng.random()*1.6
y=-38.0
while y<38:
    if rng.random()<0.55: car(cars,45.3,y+2.3,math.pi/2,rng.randrange(len(CARC)))
    y+=5.6+rng.random()*2.0
carob=cars.to_object('Rue_voitures', library_materials=False)
carob.data.materials.clear()
for mn in cars.materials:
    mat=bpy.data.materials.new(mn); mat.use_nodes=True; b=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    if mn.startswith('Carrosserie'): c=CARC[int(mn.split()[-1])]; b.inputs['Base Color'].default_value=(*c,1); b.inputs['Roughness'].default_value=0.25; b.inputs['Metallic'].default_value=0.5
    elif mn=='Vitre voiture': b.inputs['Base Color'].default_value=(0.06,0.08,0.1,1); b.inputs['Roughness'].default_value=0.05; b.inputs['Metallic'].default_value=0.6
    else: b.inputs['Base Color'].default_value=(0.03,0.03,0.03,1); b.inputs['Roughness'].default_value=0.9
    carob.data.materials.append(mat)
# grille + haie côté square (x≈-38,3 ; le square est à x<-38)
g=MeshBuilder(); g.materials.append('Fer forge')
for yy in range(-44,47,2):
    g.hexahedron([(-38.35,yy-0.03,0.1),(-38.25,yy-0.03,0.1),(-38.25,yy+0.03,0.1),(-38.35,yy+0.03,0.1)],[(-38.35,yy-0.03,1.9),(-38.25,yy-0.03,1.9),(-38.25,yy+0.03,1.9),(-38.35,yy+0.03,1.9)],'Fer forge')
    if yy<46:
        for k in range(1,5):
            x=-38.3; yk=yy+k*0.4
            g.hexahedron([(x-0.012,yk-0.012,0.15),(x+0.012,yk-0.012,0.15),(x+0.012,yk+0.012,0.15),(x-0.012,yk+0.012,0.15)],[(x-0.012,yk-0.012,1.75),(x+0.012,yk-0.012,1.75),(x+0.012,yk+0.012,1.75),(x-0.012,yk+0.012,1.75)],'Fer forge')
for z in (0.3,1.1,1.8):
    g.hexahedron([(-38.33,-44,z-0.02),(-38.27,-44,z-0.02),(-38.27,46,z-0.02),(-38.33,46,z-0.02)],[(-38.33,-44,z+0.02),(-38.27,-44,z+0.02),(-38.27,46,z+0.02),(-38.33,46,z+0.02)],'Fer forge')
gr=g.to_object('Rue_grille', library_materials=False)
h=MeshBuilder(); h.materials.append('Vegetal')
for yy in range(-44,46,3):
    if rng.random()<0.85:
        h.hexahedron([(-40.2,yy,0),(-38.6,yy,0),(-38.6,yy+2.8,0),(-40.2,yy+2.8,0)],[(-40.1,yy+0.1,0.9+rng.random()*0.4),(-38.7,yy+0.1,0.9+rng.random()*0.4),(-38.7,yy+2.7,0.9+rng.random()*0.4),(-40.1,yy+2.7,0.9+rng.random()*0.4)],'Vegetal')
hob=h.to_object('Rue_haie', library_materials=False)
print('voirie ok')

# ---------- 6. UV « boîte » en mètres pour les matériaux texturés ----------
TEX={'Pierre de taille':2.4,'Corniche':2.4,'Corniche.001':2.4,'Trottoir':2.0,'Chaussee':3.0,'Chaussee.001':3.0,'Enduit courette':2.0,'Sol cour':2.0,'Pavage cour':2.0,'Bordures':2.0,'Sol terrasse.001':2.0,'Moquette escalier.001':2.0,'Faux plafond':2.4,'Murs interieurs':2.0,'Murs interieurs.001':2.0,'Terre':2.0,'Joints zinc':2.0,'Caniveau granit':2.0}
for mname in list(bpy.data.materials.keys()):
    if mname.startswith('BB_'): TEX[mname]=2.0
def box_uv(obj, size):
    me=obj.data
    uvl=me.uv_layers.get('UVMap') or me.uv_layers.new(name='UVMap'); me.uv_layers.active=uvl
    data=uvl.data
    for poly in me.polygons:
        nx,ny,nz=(abs(c) for c in poly.normal)
        for li in poly.loop_indices:
            x,y,z=me.vertices[me.loops[li].vertex_index].co
            if nz>=nx and nz>=ny: data[li].uv=(x/size,y/size)
            elif nx>=ny: data[li].uv=(y/size,z/size)
            else: data[li].uv=(x/size,z/size)
n_uv=0
for o in bpy.data.objects:
    if o.type!='MESH' or not o.data.materials: continue
    mats=[m.name for m in o.data.materials if m]
    sizes=[TEX[m] for m in mats if m in TEX]
    if sizes:
        box_uv(o, sizes[0]); n_uv+=1
print('uv objets', n_uv)

# ---------- 7. matériaux texturés dans Blender (pour les rendus EEVEE) ----------
TEXMAP={'Pierre de taille':'pierre','Corniche':'pierre','Corniche.001':'pierre','Trottoir':'trottoir','Chaussee':'chaussee','Chaussee.001':'chaussee','Enduit courette':'enduit','Sol cour':'trottoir','Pavage cour':'trottoir','Sol terrasse.001':'trottoir','Moquette escalier.001':'moquette','Faux plafond':'faux_plafond','Joints zinc':'zinc'}
for mname in bpy.data.materials.keys():
    if mname.startswith('BB_render') or mname.startswith('BB_limestone') or mname.startswith('BB_brick'): TEXMAP[mname]='enduit' if 'render' in mname else 'pierre'
for mname,tex in TEXMAP.items():
    m=M(mname)
    if not m or not os.path.exists(f'{L}/tex/{tex}_albedo.png'): continue
    nt=m.node_tree; b=next((n for n in nt.nodes if n.type=='BSDF_PRINCIPLED'),None)
    if not b: continue
    for l in list(nt.links):
        if l.to_node==b and l.to_socket.name in ('Base Color','Normal','Roughness'): nt.links.remove(l)
    ta=nt.nodes.new('ShaderNodeTexImage'); ta.image=bpy.data.images.load(f'{L}/tex/{tex}_albedo.png', check_existing=True)
    mixc=nt.nodes.new('ShaderNodeMix'); mixc.data_type='RGBA'; mixc.blend_type='MULTIPLY'; mixc.inputs['Factor'].default_value=1.0
    mixc.inputs[7].default_value=tuple(b.inputs['Base Color'].default_value)   # teinte d'origine conservée
    base=b.inputs['Base Color'].default_value; lum=(base[0]+base[1]+base[2])/3
    mixc.inputs[7].default_value=(min(1,base[0]/max(lum,1e-3)*0.75+0.25), min(1,base[1]/max(lum,1e-3)*0.75+0.25), min(1,base[2]/max(lum,1e-3)*0.75+0.25), 1)
    nt.links.new(ta.outputs['Color'], mixc.inputs[6]); nt.links.new(mixc.outputs[2], b.inputs['Base Color'])
    if os.path.exists(f'{L}/tex/{tex}_normal.png'):
        tn=nt.nodes.new('ShaderNodeTexImage'); tn.image=bpy.data.images.load(f'{L}/tex/{tex}_normal.png', check_existing=True); tn.image.colorspace_settings.name='Non-Color'
        nm=nt.nodes.new('ShaderNodeNormalMap'); nm.inputs['Strength'].default_value=0.8; nt.links.new(tn.outputs['Color'], nm.inputs['Color']); nt.links.new(nm.outputs['Normal'], b.inputs['Normal'])
    if os.path.exists(f'{L}/tex/{tex}_rough.png'):
        tr=nt.nodes.new('ShaderNodeTexImage'); tr.image=bpy.data.images.load(f'{L}/tex/{tex}_rough.png', check_existing=True); tr.image.colorspace_settings.name='Non-Color'; nt.links.new(tr.outputs['Color'], b.inputs['Roughness'])
# verre plus réaliste
for vn in ('Vitre','Verre','Verre galerie','Verre.001'):
    m=M(vn)
    if m:
        b=next((n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None)
        if b:
            b.inputs['Roughness'].default_value=0.04; b.inputs['Metallic'].default_value=0.0
            if vn=='Vitre': b.inputs['Base Color'].default_value=(0.25,0.33,0.38,1); b.inputs['Metallic'].default_value=0.85
bpy.ops.wm.save_as_mainfile(filepath=f'{L}/v2.blend')
print('BUILD_DONE')
