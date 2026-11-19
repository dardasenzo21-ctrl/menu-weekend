# Greffe du réalisme de la v2 sur la page v1 (three r128, scripts classiques), sans toucher au reste.
import re
L='/tmp/claude-0/-home-user-menu-weekend/64550aa9-4cba-59e3-8992-8569f55e00f3/scratchpad/levallois'
s=open(f'{L}/v1_source.html',encoding='utf-8').read()
# on ne garde que le contenu de la page (le squelette artefact est rajouté à la publication)
s=s[s.index('<title>'):]; s=s[:s.rindex('</body>')]
def rep(old,new,tag,count=1):
    global s
    assert old in s, tag; s=s.replace(old,new,count)
rep('<title>123 Jules Guesde 3D</title>','<meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n<title>123 Jules Guesde réaliste</title>','titre')
rep('<p>Bureaux · R+7 sur 3 sous-sols</p>','<p>Bureaux · R+7 sur 3 sous-sols · rendu réaliste</p>','sous-titre')
rep('<button id="fond">Fond blanc</button></div>','<button id="fond">Fond blanc</button><button id="qual" aria-pressed="true">Occlusion</button></div>','bouton')
rep('<input type="range" id="heure" min="7" max="19" step="0.25">','<input type="range" id="heure" min="5" max="22" step="0.25">','slider')
# scripts supplémentaires (même CDN, même version r128)
rep('<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/utils/BufferGeometryUtils.js"></script>',
    '<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/utils/BufferGeometryUtils.js"></script>\n<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/objects/Sky.js"></script>\n<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/shaders/CopyShader.js"></script>\n<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/shaders/SSAOShader.js"></script>\n<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/shaders/GammaCorrectionShader.js"></script>\n<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/math/SimplexNoise.js"></script>\n<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/postprocessing/EffectComposer.js"></script>\n<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/postprocessing/RenderPass.js"></script>\n<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/postprocessing/ShaderPass.js"></script>\n<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/postprocessing/SSAOPass.js"></script>','scripts')
# rendu : tone mapping filmique, exposition
rep("r.outputEncoding=THREE.sRGBEncoding; r.shadowMap.enabled=true;","r.outputEncoding=THREE.sRGBEncoding; r.toneMapping=THREE.ACESFilmicToneMapping; r.toneMappingExposure=.9; r.shadowMap.enabled=true;",'tonemap')
rep("sun.shadow.bias=-.0004; sc.add(sun);","sun.shadow.bias=-.0003; sun.shadow.normalBias=.04; sc.add(sun);",'shadow')
# ciel physique + environnement PMREM recalculé avec le soleil (remplace le dégradé)
i0=s.index("  (function(){var s=new THREE.Scene(),c=document.createElement('canvas');"); i1=s.index("fromScene(s).texture})();",i0)+len("fromScene(s).texture})();")
s=s[:i0]+"""  /* Ciel physique (Sky) : le soleil réel l'éclaire, et l'environnement PBR (reflets, lumière diffuse) en est recalculé. */
  var sky=new THREE.Sky(); sky.scale.setScalar(3000); sc.add(sky); var SKYU=sky.material.uniforms; SKYU.turbidity.value=2.8; SKYU.rayleigh.value=1.6; SKYU.mieCoefficient.value=.006; SKYU.mieDirectionalG.value=.82;
  var pmrem=new THREE.PMREMGenerator(r),envRT=null,envTimer=null;
  function environnement(){var s2=new THREE.Scene(),k2=new THREE.Sky();k2.scale.setScalar(3000);['turbidity','rayleigh','mieCoefficient','mieDirectionalG'].forEach(function(k){k2.material.uniforms[k].value=SKYU[k].value});k2.material.uniforms.sunPosition.value.copy(SKYU.sunPosition.value);s2.add(k2);if(envRT)envRT.dispose();envRT=pmrem.fromScene(s2);sc.environment=envRT.texture}"""+s[i1:]
# socle : la maquette repose sur l'orthophoto IGN, plus sur un socle
rep("socle.position.set(0,-.03,0); socle.receiveShadow=true; sc.add(socle);","socle.position.set(0,-.03,0); socle.receiveShadow=true; socle.visible=false;",'socle')
rep("sol.rotation.x=-Math.PI/2; sol.position.y=-4.05; sol.receiveShadow=true; sc.add(sol);",
    """sol.rotation.x=-Math.PI/2; sol.position.y=-.12; sol.receiveShadow=true; sc.add(sol);
  /* Orthophoto IGN 520 m × 520 m (nord en haut), calée dans le repère de la maquette : axe de la rue Jules Guesde = +Y, translation sur les emprises cadastrales. */
  var ORT=(function(){var D=[0.4851523732043603,-0.874429628257287],RX=[D[1],-D[0]],C=[-19.43,-17.43],H=260,g=new THREE.BufferGeometry(),pos=[],uv=[];
    [[-H,-H,0,0],[H,-H,1,0],[H,H,1,1],[-H,H,0,1]].forEach(function(q){var x=q[0]-C[0],y=q[1]-C[1],mx=x*RX[0]+y*RX[1],my=x*D[0]+y*D[1];pos.push(mx,-.08,-my);uv.push(q[2],q[3])});
    g.setAttribute('position',new THREE.Float32BufferAttribute(pos,3));g.setAttribute('uv',new THREE.Float32BufferAttribute(uv,2));g.setIndex([0,1,2,0,2,3]);g.computeVertexNormals();
    var t=new THREE.TextureLoader().load('ortho.jpg');t.encoding=THREE.sRGBEncoding;t.anisotropy=8;var m=new THREE.Mesh(g,new THREE.MeshStandardMaterial({map:t,color:0xBFBFBF,roughness:1}));m.receiveShadow=true;sc.add(m);return m})();""",'ortho')
rep("socle.visible=cur>=0||cur===99; sol.visible=socle.visible}","sol.visible=cur>=0||cur===99; sky.visible=sol.visible; ORT.visible=sol.visible}",'apply')
# le disque gris « Rue_cour » laisse voir l'orthophoto
rep("if(k==='R'){o.visible=cur>=0||cur===99;o.userData.up=0;return}","if(k==='R'){o.visible=(cur>=0||cur===99)&&o.name!=='Rue_cour';o.userData.up=0;return}",'cour')
rep("if(marche){o.userData.up=0;o.visible=k==='V'||k==='R'||k>=0;return}","if(marche){o.userData.up=0;o.visible=(k==='V'||k==='R'||k>=0)&&o.name!=='Rue_cour';return}",'cour2')
# fond : le ciel prend la place du fond uni
rep("function fond(){document.documentElement.classList.toggle('blanc',blanc);sc.background=new THREE.Color(blanc?0xffffff:0x0b0b0b);sol.material.opacity=blanc?.16:0;",
    "function fond(){document.documentElement.classList.toggle('blanc',blanc);sc.background=new THREE.Color(blanc?0xffffff:0x0b0b0b);sol.material.opacity=.18;",'fond')
# verre physique
rep("if(o.material.name==='Vitre'){o.material.metalness=.9;o.material.roughness=.08;o.material.envMapIntensity=1}",
    "if(o.material.name==='Vitre'){var vp=mats['Vitre'].isMeshPhysicalMaterial?mats['Vitre']:new THREE.MeshPhysicalMaterial({name:'Vitre',color:0x33434C,metalness:.05,roughness:.06,clearcoat:1,clearcoatRoughness:.05,envMapIntensity:1.4,side:THREE.DoubleSide});if(!vp.userData.o)vp.userData.o={c:vp.color.clone()};mats['Vitre']=vp;o.material=vp}",'vitre')
# soleil : ciel, nuit, environnement
rep("sun.position.copy(CTR).addScaledVector(dir,170);sun.target.position.copy(CTR);var k=Math.max(0,Math.sin(alt)),mu=marche?1:.6;sun.intensity=alt>0?mu*(.5+1.5*Math.min(1,k*3)):0;",
    "sun.position.copy(CTR).addScaledVector(dir,220);sun.target.position.copy(CTR);var k=Math.max(0,Math.sin(alt)),mu=marche?1:.8;sun.intensity=alt>0?mu*(.8+2.0*Math.min(1,k*3)):0;\n    SKYU.sunPosition.value.copy(dir);SKYU.sunPosition.value.y=Math.max(SKYU.sunPosition.value.y,-.1);var nuit=alt<0;r.toneMappingExposure=nuit?.9:(.75+.25*Math.min(1,Math.max(0,alt/(14*Math.PI/180))));\n    var vm=mats['Vitre'];if(vm&&vm.emissive){vm.emissive.set(0xE8B86A);vm.emissiveIntensity=nuit?1.1:0}var lp=mats['Lampadaire'];if(lp){lp.emissive.set(0xFFE0A0);lp.emissiveIntensity=nuit?2.5:0}clearTimeout(envTimer);envTimer=setTimeout(environnement,120);",'soleil')
rep("sun.color.setRGB(1,.72+.26*w,.45+.48*w);hemi.intensity=marche?(alt>0?.5+.3*w:.2):(alt>0?.12+.1*w:.08);","sun.color.setRGB(1,.7+.28*w,.42+.5*w);hemi.intensity=marche?(alt>0?.5+.3*w:.16):(alt>0?.25+.3*w:.16);",'hemi')
rep("heure.value=12.5;","heure.value=14;",'heure')
# matières : textures PBR projetées en triplanaire (repère monde), à la place des aplats et motifs dessinés
rep("  function pierre(){","""  var TLX=new THREE.TextureLoader();
  function texm(n){var t=TLX.load('tex/'+n+'.jpg');t.wrapS=t.wrapT=THREE.RepeatWrapping;t.anisotropy=Math.min(8,r.capabilities.getMaxAnisotropy());return t}
  var TRIP={'Pierre de taille':['pierre',2.4,0xEAE2D2],'Corniche':['pierre',2.4,0xE3DAC8],'Corniche.001':['pierre',2.4,0xDDD4C2],'Trottoir':['trottoir',2.0,0xC4C1B9],'Bordures':['trottoir',2.0,0xCAC5BB],'Sol cour':['trottoir',2.0,0xCFC9BC],'Pavage cour':['trottoir',2.0,0xD6CAB4],'Sol terrasse.001':['trottoir',2.0,0xBBB5A9],'Chaussee':['chaussee',3.0,0xA0A0A2],'Chaussee.001':['chaussee',3.0,0xA0A0A2],'Enduit courette':['enduit',2.0,0xD2CFC8],'Moquette escalier.001':['moquette',2.0,0xC0C4CE],'Faux plafond':['faux_plafond',2.4,0xF2F1EC],'Joints zinc':['zinc',2.0,0xB0B6BE],'Voisins':['enduit',2.0,0xE4E0D8]};
  function triplanaire(){Object.keys(mats).forEach(function(mn){var P=TRIP[mn]||TRIP[mn.replace(/\\.\\d+$/,'')];if(!P)return;var m=mats[mn];if(m.userData.trip)return;m.userData.trip=1;var alb=texm(P[0]+'_albedo'),rou=texm(P[0]+'_rough');m.color.set(P[2]);m.roughness=mn==='Joints zinc'?.5:.9;m.metalness=mn==='Joints zinc'?.4:0;
    m.onBeforeCompile=function(sh){sh.uniforms.uAlb={value:alb};sh.uniforms.uRou={value:rou};sh.uniforms.uS={value:P[1]};
      sh.vertexShader=sh.vertexShader.replace('#include <common>','#include <common>\\nvarying vec3 vWp;varying vec3 vWn;').replace('#include <begin_vertex>','#include <begin_vertex>\\nvWp=(modelMatrix*vec4(transformed,1.)).xyz;vWn=normalize(mat3(modelMatrix)*objectNormal);');
      sh.fragmentShader=sh.fragmentShader.replace('#include <common>','#include <common>\\nvarying vec3 vWp;varying vec3 vWn;uniform sampler2D uAlb;uniform sampler2D uRou;uniform float uS;\\nvec4 trip(sampler2D t){vec3 an=abs(vWn);vec3 w=an/(an.x+an.y+an.z+1e-5);return texture2D(t,vWp.zy/uS)*w.x+texture2D(t,vWp.xz/uS)*w.y+texture2D(t,vWp.xy/uS)*w.z;}')
        .replace('#include <color_fragment>','#include <color_fragment>\\ndiffuseColor.rgb*=sRGBToLinear(trip(uAlb)).rgb*1.15;')
        .replace('#include <roughnessmap_fragment>','#include <roughnessmap_fragment>\\nroughnessFactor*=mix(.75,1.15,trip(uRou).r);')};
    m.customProgramCacheKey=function(){return 'trip-'+P[0]};m.needsUpdate=true})}
  function pierre(){""",'triplanaire')
# l'ancien motif pierre (joints dessinés) et les motifs trottoir/chaussée ne s'appliquent plus : la texture prend le relais
rep("function pierre(){['Pierre de taille','Corniche'].forEach(function(n,i){var m=mats[n];if(!m)return;","function pierre(){[].forEach(function(n,i){var m=mats[n];if(!m)return;",'pierre-off')
rep("  function motifs(){Object.keys(mats).forEach(function(mn){var n=mn.replace(/\\.\\d+$/,''),m=mats[mn];if(!MOTIF[n])return;","  function motifs(){Object.keys(mats).forEach(function(mn){var n=mn.replace(/\\.\\d+$/,''),m=mats[mn];if(!MOTIF[n]||TRIP[mn]||TRIP[n])return;",'motifs-off')
rep("sc.add(g.scene);charge.hidden=true;maquette();pierre();motifs();apply();","sc.add(g.scene);charge.hidden=true;maquette();pierre();motifs();triplanaire();soleil();apply();",'apres-chargement')
# maquette() recolore les matières : ne pas écraser les teintes texturées
rep("function maquette(){Object.keys(mats).forEach(function(k){var m=mats[k],o=m.userData.o;\n    if(maq&&PAL[k]!==undefined){","function maquette(){Object.keys(mats).forEach(function(k){var m=mats[k],o=m.userData.o;if(TRIP[k]||TRIP[k.replace(/\\.\\d+$/,'')])return;\n    if(maq&&PAL[k]!==undefined){",'maquette')
# voisins : opaques et clairs (plus de transparence), ombres portées
rep("if(o.material.name==='Voisins'||o.material.name==='Joints zinc'){o.material.transparent=true;o.material.opacity=.22;o.material.depthWrite=false;o.castShadow=false;if(o.material.name==='Voisins')o.material.side=THREE.FrontSide}","if(o.material.name==='Voisins'){o.material.side=THREE.FrontSide;o.castShadow=true}",'voisins')
rep("var vo=mats['Voisins'];if(vo){vo.opacity=on?1:.22;vo.transparent=!on;vo.depthWrite=on;vo.needsUpdate=true}","",'voisins2')
# occlusion ambiante (SSAO) + correction gamma en post-traitement, repli en rendu direct si ça casse
rep("  window.__pos=pos;window.__dbg={sun:sun,hemi:hemi,sc:sc,cam:cam,r:r};","""  var tactile=matchMedia('(pointer:coarse)').matches,AO=!tactile,direct=tactile,comp=null,ssao=null;
  try{comp=new THREE.EffectComposer(r);comp.addPass(new THREE.RenderPass(sc,cam));ssao=new THREE.SSAOPass(sc,cam,1,1);ssao.kernelRadius=6;ssao.minDistance=.002;ssao.maxDistance=.08;ssao.output=THREE.SSAOPass.OUTPUT.Default;comp.addPass(ssao);comp.addPass(new THREE.ShaderPass(THREE.GammaCorrectionShader))}catch(e){direct=true;console.warn('post-traitement indisponible',e)}
  document.getElementById('qual').setAttribute('aria-pressed',AO);document.getElementById('qual').addEventListener('click',function(){AO=!AO;if(ssao)ssao.enabled=AO;direct=!AO||!comp;this.setAttribute('aria-pressed',AO)});
  window.__pos=pos;window.__dbg={sun:sun,hemi:hemi,sc:sc,cam:cam,r:r,mats:mats};""",'ssao')
rep("function size(){var w=el.clientWidth,h=el.clientHeight;r.setSize(w,h,false);","function size(){var w=el.clientWidth,h=el.clientHeight;r.setSize(w,h,false);if(comp){comp.setSize(w,h);if(ssao)ssao.setSize(w,h)}",'size')
rep("addEventListener('resize',size);size();cam.position.set(-120,70,108);ctl.target.set(0,10,0);ctl.update();fiche();","addEventListener('resize',size);size();cam.position.set(-120,70,108);ctl.target.set(0,10,0);ctl.update();fiche();environnement();",'init')
rep("if(marche){avance(dt_);carteDessine()}else ctl.update();r.render(sc,cam)})();","if(marche){avance(dt_);carteDessine()}else ctl.update();if(direct||!comp)r.render(sc,cam);else{try{comp.render()}catch(e){direct=true;console.warn(e);r.render(sc,cam)}}})();",'loop')
# visite : le ciel reste le ciel physique (plus de dégradé), verre plus transparent
rep("if(on){aller(cur>=0&&cur<=7?cur:6);placer();sc.background=CIEL}else{fond();cur=99;niveau(99)}apply();fiche()}","if(on){aller(cur>=0&&cur<=7?cur:6);placer()}else{fond();cur=99;niveau(99)}apply();fiche()}",'visite')
open(f'{L}/publish3/index.html','w',encoding='utf-8').write(s); print('v1 réaliste écrite', len(s)//1024,'KB')
