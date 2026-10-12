import * as T from './vendor/three.module.js';

// Original procedural circuit and vehicles. No streamed map assets or model downloads.
export class CircuitView {
  constructor(canvas){
    this.renderer=new T.WebGLRenderer({canvas,antialias:true,alpha:false,powerPreference:'high-performance'});
    this.renderer.setPixelRatio(Math.min(devicePixelRatio,1.4));
    this.renderer.shadowMap.enabled=true;this.renderer.shadowMap.type=T.PCFSoftShadowMap;
    this.renderer.toneMapping=T.ACESFilmicToneMapping;this.renderer.toneMappingExposure=1.2;
    this.scene=new T.Scene();this.scene.background=new T.Color('#bdd8e4');this.scene.fog=new T.Fog('#bdd8e4',350,1500);
    this.camera=new T.PerspectiveCamera(62,innerWidth/innerHeight,.1,1600);
    this.scene.add(new T.HemisphereLight('#e0f2ff','#566147',2.1));
    this.sun=new T.DirectionalLight('#ffefd3',3.2);this.sun.castShadow=true;
    this.sun.shadow.mapSize.set(1536,1536);Object.assign(this.sun.shadow.camera,{left:-35,right:35,top:35,bottom:-35,near:1,far:180});this.sun.shadow.bias=-.0002;
    this.scene.add(this.sun,this.sun.target);
    const mat=(color,metalness=0,roughness=.75)=>new T.MeshStandardMaterial({color,metalness,roughness});
    this.mats={grass:mat('#6d855a'),asphalt:mat('#373d43'),white:mat('#eef1e4'),red:mat('#d44835'),runoff:mat('#7292a5'),gravel:mat('#bcaa8d'),steel:mat('#879aa6',.55,.38),black:mat('#152128'),glass:mat('#253b49',.4,.3)};
    const grain=document.createElement('canvas');grain.width=grain.height=128;const gx=grain.getContext('2d'),pixels=gx.createImageData(128,128);let seed=817;
    for(let i=0;i<pixels.data.length;i+=4){seed=(Math.imul(seed,1664525)+1013904223)>>>0;const value=180+(seed%70);pixels.data.set([value,value,value,255],i);}gx.putImageData(pixels,0,0);
    const texture=new T.CanvasTexture(grain);texture.wrapS=texture.wrapT=T.RepeatWrapping;texture.colorSpace=T.SRGBColorSpace;texture.anisotropy=Math.min(4,this.renderer.capabilities.getMaxAnisotropy());this.mats.asphalt.map=texture;
    const knots=[[-300,0,-180],[-70,0,-250],[240,0,-180],[310,0,70],[150,0,210],[20,0,160],[-110,0,300],[-320,0,150]];
    this.path=new T.CatmullRomCurve3(knots.map(p=>new T.Vector3(...p)),true,'centripetal');
    const factor=3000/this.path.getLength();this.path.points.forEach(p=>p.multiplyScalar(factor));this.path.updateArcLengths();
    this.mesh(new T.PlaneGeometry(5000,5000),this.mats.grass,[0,-.04,0],[-Math.PI/2,0,0]).receiveShadow=true;
    this.strip(-14,14,this.mats.gravel,.001);this.strip(-10,10,this.mats.runoff,.006);this.strip(-6,6,this.mats.asphalt,.018);
    this.strip(-5.92,-5.78,this.mats.white,.021);this.strip(5.78,5.92,this.mats.white,.021);
    this.kerbs();this.markings();this.barriers();this.environment();
    this.bike=this.motorcycle('#d1f27c');this.scene.add(this.bike);
    this.rivals=Array.from({length:12},(_,i)=>{const bike=this.motorcycle(['#e3513c','#4e88de','#e7b347','#eceff1'][i%4]);this.scene.add(bike);return bike;});
    this.impactId=0;this.effectAge=10;this.particles=new T.InstancedMesh(new T.SphereGeometry(.07,5,4),new T.MeshBasicMaterial({transparent:true,opacity:1}),80);this.particles.frustumCulled=false;this.particles.visible=false;this.scene.add(this.particles);this.dummy=new T.Object3D();
    this.cameraInitialized=false;this.look=new T.Vector3();this.resize();
  }
  mesh(geometry,material,position=[0,0,0],rotation=[0,0,0],parent=this.scene){const m=new T.Mesh(geometry,material);m.position.set(...position);m.rotation.set(...rotation);parent.add(m);return m;}
  at(z,lateral=0){const t=((z%3000)+3000)%3000/3000,p=this.path.getPointAt(t),tangent=this.path.getTangentAt(t).normalize(),normal=new T.Vector3(-tangent.z,0,tangent.x);return {p:p.addScaledVector(normal,lateral),tangent,normal};}
  strip(left,right,material,height){const positions=[],uv=[],index=[],n=800;for(let i=0;i<=n;i++){for(const offset of [left,right]){const {p}=this.at(i/n*3000,offset);positions.push(p.x,height,p.z);uv.push((offset-left)/3,i/n*1000);}if(i<n){const j=i*2;index.push(j,j+1,j+2,j+1,j+3,j+2);}}
    const g=new T.BufferGeometry();g.setAttribute('position',new T.Float32BufferAttribute(positions,3));g.setAttribute('uv',new T.Float32BufferAttribute(uv,2));g.setIndex(index);g.computeVertexNormals();material.side=T.DoubleSide;const m=this.mesh(g,material);m.receiveShadow=true;
  }
  tile(z,offset,width,length,material){const {p,tangent}=this.at(z,offset);return this.mesh(new T.BoxGeometry(width,.035,length),material,[p.x,.04,p.z],[0,Math.atan2(tangent.x,tangent.z),0]);}
  kerbs(){for(let z=0;z<3000;z+=5)for(const side of [-1,1])this.tile(z,side*6.42,.82,4.9,Math.floor(z/5)%2?this.mats.white:this.mats.red);}
  markings(){
    // Grid boxes and chequered start / finish across the full track.
    for(let i=0;i<10;i++)for(let row=0;row<2;row++)this.tile(12+row*.65,-5.4+i*1.2,1.2,.65,(i+row)%2?this.mats.black:this.mats.white);
    for(let i=0;i<8;i++){this.tile(20+i*7,i%2?-2.7:2.7,2.0,.12,this.mats.white);}
    const {p,tangent}=this.at(10),yaw=Math.atan2(tangent.x,tangent.z),gate=new T.Group();gate.position.copy(p);gate.rotation.y=yaw;this.scene.add(gate);
    for(const side of [-1,1])this.mesh(new T.BoxGeometry(.3,8,.3),this.mats.steel,[side*8,4,0],[0,0,0],gate);
    this.mesh(new T.BoxGeometry(16.6,1.1,.6),this.mats.black,[0,7.5,0],[0,0,0],gate);
    const c=document.createElement('canvas');c.width=1024;c.height=128;const x=c.getContext('2d');x.fillStyle='#162d38';x.fillRect(0,0,1024,128);x.font='bold 58px sans-serif';x.textAlign='center';x.fillStyle='#d1f27c';x.fillText('VENTUNO  //  CIRCUIT',512,83);
    const texture=new T.CanvasTexture(c);texture.colorSpace=T.SRGBColorSpace;this.mesh(new T.PlaneGeometry(15,1.6),new T.MeshBasicMaterial({map:texture,side:T.DoubleSide}),[0,7.5,-.32],[0,Math.PI,0],gate);
  }
  barriers(){
    // Instanced segments keep the circuit's draw calls bounded.
    const geo=new T.BoxGeometry(.25,.72,6.5),material=this.mats.steel,n=460,inst=new T.InstancedMesh(geo,material,n*2),dummy=new T.Object3D();
    for(let i=0;i<n;i++)for(let s=0;s<2;s++){const {p,tangent}=this.at(i/n*3000,(s?1:-1)*13.3);dummy.position.set(p.x,.45,p.z);dummy.rotation.set(0,Math.atan2(tangent.x,tangent.z),0);dummy.updateMatrix();inst.setMatrixAt(i*2+s,dummy.matrix);}this.scene.add(inst);
  }
  environment(){
    const concrete=new T.MeshStandardMaterial({color:'#929c9e',roughness:.9}),roof=new T.MeshStandardMaterial({color:'#dce4e5',metalness:.25,roughness:.6});
    for(let station=0;station<4;station++){
      const {p,tangent}=this.at(60+station*60,-32),g=new T.Group();g.position.copy(p);g.rotation.y=Math.atan2(tangent.x,tangent.z);this.scene.add(g);
      for(let row=0;row<5;row++)this.mesh(new T.BoxGeometry(13,.7,35),concrete,[-row*2,1+row*.85,0],[0,0,0],g);
      this.mesh(new T.BoxGeometry(25,.2,38),roof,[-4,7,0],[0,0,.04],g);
      for(const z of [-15,15])this.mesh(new T.BoxGeometry(.3,7,.3),this.mats.steel,[-12,3.5,z],[0,0,0],g);
      const seats=new T.InstancedMesh(new T.BoxGeometry(.7,.35,.6),new T.MeshStandardMaterial({color:station%2?'#e06642':'#3a759b'}),160),d=new T.Object3D();for(let i=0;i<160;i++){let row=Math.floor(i/32),col=i%32;d.position.set(-row*2+4,1.55+row*.85,-16+col);d.updateMatrix();seats.setMatrixAt(i,d.matrix);}g.add(seats);
    }
    for(let i=0;i<8;i++){const {p,tangent}=this.at(60+i*20,25),g=new T.Group();g.position.copy(p);g.rotation.y=Math.atan2(tangent.x,tangent.z);this.scene.add(g);this.mesh(new T.BoxGeometry(15,5,18),concrete,[0,2.5,0],[0,0,0],g);this.mesh(new T.BoxGeometry(16,.3,19),roof,[0,5,0],[0,0,0],g);this.mesh(new T.BoxGeometry(.06,3,12),this.mats.glass,[-7.53,2.4,0],[0,0,0],g);}
    const treeCount=110,trunks=new T.InstancedMesh(new T.CylinderGeometry(.24,.4,4,5),new T.MeshStandardMaterial({color:'#61564a'}),treeCount),crowns=new T.InstancedMesh(new T.ConeGeometry(3,9,7),new T.MeshStandardMaterial({color:'#365e4c'}),treeCount),d=new T.Object3D();
    for(let i=0;i<treeCount;i++){const {p}=this.at(i/treeCount*3000,(i%2?1:-1)*(40+i%6*6));d.position.set(p.x,2,p.z);d.updateMatrix();trunks.setMatrixAt(i,d.matrix);d.position.y=7;d.updateMatrix();crowns.setMatrixAt(i,d.matrix);}this.scene.add(trunks,crowns);
    for(let i=0;i<14;i++){const angle=i/14*Math.PI*2,r=1500,height=120+i%4*100;this.mesh(new T.ConeGeometry(240,height,8),new T.MeshStandardMaterial({color:i%2?'#869d9a':'#809793'}),[Math.sin(angle)*r,height/2-10,Math.cos(angle)*r]);}
  }
  motorcycle(color){
    const root=new T.Group(),lean=new T.Group();root.add(lean);root.userData.lean=lean;
    const paint=new T.MeshStandardMaterial({color,metalness:.42,roughness:.3}),leather=new T.MeshStandardMaterial({color:'#253545',roughness:.7}),helmet=new T.MeshStandardMaterial({color:'#f0f2de',metalness:.18,roughness:.3});
    let active=lean;
    const mesh=(geo,mat,pos,rot=[0,0,0])=>{const m=this.mesh(geo,mat,pos,rot,active);m.castShadow=true;return m;};
    const box=(size,mat,pos,rot=[0,0,0])=>mesh(new T.BoxGeometry(...size),mat,pos,rot);
    root.userData.wheels=[];
    for(const z of [-.8,.85]){
      const wheel=mesh(new T.TorusGeometry(.35,.115,8,20),this.mats.black,[0,.44,z],[0,Math.PI/2,0]);root.userData.wheels.push(wheel);
      mesh(new T.CylinderGeometry(.28,.28,.075,16),this.mats.steel,[0,.44,z],[0,0,Math.PI/2]);
    }
    box([.36,.32,1.05],this.mats.black,[0,.63,-.07]);box([.14,.16,1.1],this.mats.steel,[0,.42,-.38],[.16,0,0]);
    const tank=mesh(new T.SphereGeometry(.38,12,8),paint,[0,1,.15]);tank.scale.set(.72,.75,1.45);
    const fairing=mesh(new T.SphereGeometry(.48,14,10),paint,[0,.82,.55]);fairing.scale.set(.75,1.2,.92);
    box([.48,.14,.65],this.mats.black,[0,1.06,-.53],[.12,0,0]);box([.4,.18,.35],paint,[0,1.06,-.85],[.2,0,0]);
    const windshield=mesh(new T.SphereGeometry(.28,12,8,0,Math.PI*2,0,Math.PI/2),new T.MeshStandardMaterial({color:'#58829a',transparent:true,opacity:.7,metalness:.3,roughness:.2}),[0,1.28,.63],[-.32,0,0]);windshield.scale.set(1,.6,1.15);
    for(const x of [-.17,.17])box([.065,.65,.065],this.mats.steel,[x,.7,.78],[.2,0,0]);box([.75,.06,.07],this.mats.black,[0,1.2,.45]);
    mesh(new T.CylinderGeometry(.08,.08,.8,8),this.mats.steel,[.32,.58,-.44],[Math.PI/2,0,0]);
    const rider=new T.Group();root.add(rider);root.userData.rider=rider;active=rider;
    const body=mesh(new T.SphereGeometry(.4,12,8),leather,[0,1.37,-.15],[-.72,0,0]);body.scale.set(.7,1.05,.58);
    const head=mesh(new T.SphereGeometry(.23,16,10),helmet,[0,1.67,.24]);head.scale.set(1,1.07,1.05);
    box([.32,.1,.03],this.mats.glass,[0,1.67,.445],[-.2,0,0]);
    for(const side of [-1,1]){box([.16,.46,.17],leather,[side*.26,1.15,-.34],[.6,0,side*.25]);box([.14,.38,.15],leather,[side*.31,.8,-.32],[-.28,0,0]);box([.11,.43,.12],leather,[side*.28,1.35,.13],[.8,0,side*-.22]);box([.14,.08,.15],this.mats.black,[side*.32,1.22,.43]);}
    return root;
  }
  place(group,z,x,lean=0){const {p,tangent}=this.at(z,x*5.4);group.position.set(p.x,.035,p.z);group.rotation.y=Math.atan2(tangent.x,tangent.z);group.userData.lean.rotation.z=lean*.45;group.userData.rider.rotation.set(0,0,lean*.45);group.userData.rider.position.set(0,0,0);return {p,tangent};}
  impact(p){this.effectAge=0;this.effectOrigin=p.clone();this.velocities=Array.from({length:80},(_,i)=>new T.Vector3(Math.sin(i*2.4)*(2+i%5),1+i%7*.5,Math.cos(i*1.9)*(2+i%6)));this.particles.visible=true;for(let i=0;i<80;i++)this.particles.setColorAt(i,new T.Color(i<42?'#ffc063':'#b9ad99'));this.particles.instanceColor.needsUpdate=true;}
  effects(dt){this.effectAge+=dt;const t=this.effectAge;this.particles.visible=t<2;if(!this.particles.visible)return;this.particles.material.opacity=Math.max(0,1-t/2);for(let i=0;i<80;i++){const v=this.velocities[i],p=this.effectOrigin;this.dummy.position.set(p.x+v.x*t,Math.max(.07,.3+v.y*t-3*t*t),p.z+v.z*t);const size=i<42?1:2+t*3;this.dummy.scale.setScalar(size);this.dummy.updateMatrix();this.particles.setMatrixAt(i,this.dummy.matrix);}this.particles.instanceMatrix.needsUpdate=true;}
  resize(){this.renderer.setSize(innerWidth,innerHeight,false);this.camera.aspect=innerWidth/innerHeight;this.camera.updateProjectionMatrix();}
  render(ride,steer,dt){
    const {p,tangent}=this.place(this.bike,ride.z,ride.x,steer);this.bike.visible=ride.crashTime>0||!(ride.invincible>0&&Math.floor(ride.invincible*12)%2);
    if(ride.impactId!==this.impactId){this.impactId=ride.impactId;if(ride.impactId)this.impact(p);}
    if(ride.crashTime>0){const progress=Math.min(1,(2-ride.crashTime)/1.2),sign=steer<0?-1:1;this.bike.userData.lean.rotation.z=sign*Math.min(Math.PI/2,progress*2.5);this.bike.position.y=.35;const rider=this.bike.userData.rider;rider.rotation.set(progress*1.1,0,sign*progress*Math.PI/2);rider.position.set(-sign*progress*2.2,.35+Math.sin(progress*Math.PI)*1.2,progress*.5);}
    this.effects(dt);
    this.rivals.forEach((bike,i)=>{const rival=ride.traffic[i];bike.visible=!!rival&&Math.abs(rival.z-ride.z)<320;if(bike.visible)this.place(bike,rival.z,rival.x,Math.sin(rival.z/100)*.12);});
    const desired=p.clone().addScaledVector(tangent,ride.crashTime>0?-9:-6.8);desired.y=ride.crashTime>0?4.5:3.25;
    const look=p.clone().addScaledVector(tangent,12);look.y=1.2;
    if(!this.cameraInitialized){this.camera.position.copy(desired);this.look.copy(look);this.cameraInitialized=true;}else{const alpha=1-Math.exp(-dt/.12);this.camera.position.lerp(desired,alpha);this.look.lerp(look,alpha);}
    this.camera.lookAt(this.look);this.camera.fov=62+Math.min(7,ride.speed/30);this.camera.updateProjectionMatrix();
    this.sun.position.copy(p).add(new T.Vector3(-35,65,-40));this.sun.target.position.copy(p);this.sun.target.updateMatrixWorld();
    this.renderer.render(this.scene,this.camera);
  }
}
