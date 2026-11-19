"""GLB -> glTF JSON (buffer base64) avec EXT_meshopt_compression + KHR_mesh_quantization.
Positions en uint16 (déquantifiées par la translation/échelle du nœud), normales supprimées (ombrage plat côté
three.js), UV conservées uniquement pour les matériaux texturés, index en uint16/uint32. Compatible MeshoptDecoder."""
import struct, json, base64, sys, os
import numpy as np
import meshoptimizer as mo
mo.encode_vertex_version(0); mo.encode_index_version(1)
TEXTURED={'Pierre de taille','Corniche','Corniche.001','Trottoir','Sol cour','Pavage cour','Sol terrasse.001','Bordures','Chaussee','Chaussee.001','Enduit courette','Moquette escalier.001','Faux plafond','Joints zinc','Terre','Orthophoto','BB_zinc'}
CT={5120:'b',5121:'B',5122:'h',5123:'H',5125:'I',5126:'f'}; CN={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}
def pack(src, dst):
    data=open(src,'rb').read(); magic,ver,length=struct.unpack('<III',data[:12]); off=12; chunks={}
    while off<length:
        clen,ctype=struct.unpack('<II',data[off:off+8]); chunks[ctype]=data[off+8:off+8+clen]; off+=8+clen
    g=json.loads(chunks[0x4E4F534A]); binc=chunks[0x004E4942]
    def read(acc_i):
        a=g['accessors'][acc_i]; bv=g['bufferViews'][a['bufferView']]; n=CN[a['type']]; dt=np.dtype('<'+CT[a['componentType']])
        start=bv.get('byteOffset',0)+a.get('byteOffset',0); stride=bv.get('byteStride', n*dt.itemsize)
        if stride==n*dt.itemsize:
            return np.frombuffer(binc, dtype=dt, count=a['count']*n, offset=start).reshape(a['count'],n)
        raw=np.frombuffer(binc, dtype=np.uint8, count=stride*a['count'], offset=start).reshape(a['count'],stride)[:, :n*dt.itemsize].copy()
        return raw.view(dt).reshape(a['count'],n)
    mat_tex=[(m.get('name','') in TEXTURED or m.get('name','').startswith(('Pierre','Corniche','Chaussee','BB_zinc'))) for m in g.get('materials',[])]
    comp=bytearray(); fallback_len=0; views=[]; accessors=[]
    def add_view(buf_bytes, count, stride, mode, is_index):
        nonlocal fallback_len
        enc=mo.encode_vertex_buffer(np.frombuffer(buf_bytes,dtype=np.uint8).reshape(count,stride)) if mode=='ATTRIBUTES' else mo.encode_index_buffer(np.frombuffer(buf_bytes,dtype=np.uint32) if stride==4 else np.frombuffer(buf_bytes,dtype=np.uint16).astype(np.uint32), index_count=count, vertex_count=None)
        while len(comp)%4: comp.append(0)
        c_off=len(comp); comp.extend(enc)
        while fallback_len%4: fallback_len+=1
        v={'buffer':1,'byteOffset':fallback_len,'byteLength':len(buf_bytes),'extensions':{'EXT_meshopt_compression':{'buffer':0,'byteOffset':c_off,'byteLength':len(enc),'byteStride':stride,'count':count,'mode':mode}}}
        if not is_index: v['byteStride']=stride
        fallback_len+=len(buf_bytes); views.append(v); return len(views)-1
    mesh_nodes={}
    for ni,nd in enumerate(g.get('nodes',[])):
        if 'mesh' in nd: mesh_nodes.setdefault(nd['mesh'],[]).append(ni)
    for mi,mesh in enumerate(g['meshes']):
        # bbox commune aux primitives du mesh -> quantification uint16 + transformation du nœud
        poss=[read(p['attributes']['POSITION']) for p in mesh['primitives']]
        allp=np.concatenate(poss); mn=allp.min(0); mx=allp.max(0); ext=np.maximum(mx-mn,1e-6)
        for ni in mesh_nodes.get(mi,[]):
            nd=g['nodes'][ni]; nd['translation']=[float(x) for x in mn]; nd['scale']=[float(x/65535.0) for x in ext]
        for p,pos in zip(mesh['primitives'],poss):
            q=np.rint((pos-mn)/ext*65535.0).astype(np.uint16); n=q.shape[0]
            qp=np.zeros((n,4),dtype=np.uint16); qp[:,:3]=q
            vi=add_view(qp.tobytes(), n, 8, 'ATTRIBUTES', False)
            accessors.append({'bufferView':vi,'componentType':5123,'count':n,'type':'VEC3','min':[int(x) for x in q.min(0)],'max':[int(x) for x in q.max(0)]})
            attrs={'POSITION':len(accessors)-1}
            if 'TEXCOORD_0' in p['attributes'] and p.get('material') is not None and mat_tex[p['material']]:
                uv=read(p['attributes']['TEXCOORD_0']).astype(np.float32)
                vi=add_view(uv.tobytes(), n, 8, 'ATTRIBUTES', False)
                accessors.append({'bufferView':vi,'componentType':5126,'count':n,'type':'VEC2'}); attrs['TEXCOORD_0']=len(accessors)-1
            p['attributes']=attrs
            if 'indices' in p:
                idx=read(p['indices']).reshape(-1).astype(np.uint32); cnt=idx.shape[0]-idx.shape[0]%3; idx=idx[:cnt]
                if n<=65535:
                    vi=add_view(idx.astype(np.uint16).tobytes(), cnt, 2, 'TRIANGLES', True); ct=5123
                else:
                    vi=add_view(idx.tobytes(), cnt, 4, 'TRIANGLES', True); ct=5125
                accessors.append({'bufferView':vi,'componentType':ct,'count':cnt,'type':'SCALAR'}); p['indices']=len(accessors)-1
            p.pop('extensions',None)
    g['accessors']=accessors; g['bufferViews']=views
    g['buffers']=[{'byteLength':len(comp),'uri':'data:application/octet-stream;base64,'+base64.b64encode(bytes(comp)).decode('ascii')},{'byteLength':fallback_len,'extensions':{'EXT_meshopt_compression':{'fallback':True}}}]
    g['extensionsUsed']=['EXT_meshopt_compression','KHR_mesh_quantization']; g['extensionsRequired']=['EXT_meshopt_compression','KHR_mesh_quantization']
    for k in ('images','textures','samplers'): g.pop(k,None)
    for m in g.get('materials',[]):
        pbr=m.get('pbrMetallicRoughness',{}); pbr.pop('baseColorTexture',None); pbr.pop('metallicRoughnessTexture',None); m.pop('normalTexture',None); m.pop('occlusionTexture',None); m.pop('emissiveTexture',None)
    out=json.dumps(g,separators=(',',':')); open(dst,'w').write(out)
    print(os.path.basename(dst), len(out)//1024,'KB', 'meshes',len(g['meshes']),'compressé',len(comp)//1024,'KB','brut',fallback_len//1024,'KB')
pack(sys.argv[1], sys.argv[2])
