/* ============================================================
   Parques y jardines 3D — extensión del "Ver en 3D" (MAIRENA3D_V2)
   Añade la capa de parques y jardines al visor 3D integrado,
   usando los datos que ya trae la propia página (#parques-data).

   No toca el código original: se engancha a la escena 3D en el
   momento en que el visor la crea.
   ============================================================ */
(function(){
'use strict';
if(window.__M3D_PARQUES__)return;window.__M3D_PARQUES__=true;

function boot(){
  if(!window.THREE){setTimeout(boot,300);return;}

  /* 1) Capturar la escena del visor: se intercepta Object3D.add,
        que el visor usa para añadir el suelo a la escena. */
  var origAdd=THREE.Object3D.prototype.add;
  THREE.Object3D.prototype.add=function(){
    if(this.isScene&&!window.__m3dScene)window.__m3dScene=this;
    return origAdd.apply(this,arguments);
  };

  /* 2) Casilla "Parques y jardines" en el panel de capas */
  function addChk(){
    var panel=document.querySelector('.m3d-panel');
    if(!panel||document.getElementById('m3d-l-parques'))return;
    var ref=null,labs=panel.querySelectorAll('label');
    for(var i=0;i<labs.length;i++){if(labs[i].querySelector('#m3d-l-alcorques')){ref=labs[i];break;}}
    var lb=document.createElement('label');
    lb.innerHTML='<input type="checkbox" id="m3d-l-parques" checked> Parques y jardines';
    if(ref)ref.parentNode.insertBefore(lb,ref.nextSibling);
    else panel.appendChild(lb);
    var chk=lb.querySelector('input');
    chk.addEventListener('change',function(){if(grp)grp.visible=chk.checked;});
  }
  addChk();

  /* 3) Esperar a que el visor cree la escena y construir la capa */
  var grp=null,tries=0;
  var iv=setInterval(function(){
    if(++tries>900){clearInterval(iv);return;} /* 90 s de margen */
    var scene=window.__m3dScene;if(!scene)return;
    var dEl=document.getElementById('mairena3d-data'),pEl=document.getElementById('parques-data');
    if(!dEl||!pEl)return;
    var data3,parques;
    try{data3=JSON.parse(dEl.textContent);parques=JSON.parse(pEl.textContent);}catch(e){return;}
    clearInterval(iv);build(scene,data3,parques);
  },100);

  function build(scene,data3,parques){
    var c0=(data3.labels&&data3.labels[0])||{lat:37.344491,lon:-6.060677};
    var OR={lon:c0.lon,lat:c0.lat};
    function toXY(lon,lat){
      var x=(lon-OR.lon)*111320*Math.cos(OR.lat*Math.PI/180);
      var z=-(lat-OR.lat)*110540;
      return[x,z];
    }
    grp=new THREE.Group();grp.name='parques3d';
    var fmat=new THREE.MeshBasicMaterial({color:0x2ecc71,transparent:true,opacity:.42,depthWrite:false,side:THREE.DoubleSide});
    var emat=new THREE.LineBasicMaterial({color:0x8dffb0,transparent:true,opacity:.75});
    (parques.features||[]).forEach(function(f){
      var g=f.geometry;if(!g)return;
      var polys=[];
      if(g.type==='Polygon')polys=[g.coordinates];
      else if(g.type==='MultiPolygon')polys=g.coordinates;
      polys.forEach(function(poly){
        if(!poly||!poly.length)return;
        for(var idx=0;idx<poly.length;idx++){
          var ring=poly[idx],pts=[];
          for(var i=0;i<ring.length;i++){var xy=toXY(ring[i][0],ring[i][1]);pts.push(new THREE.Vector2(xy[0],xy[1]));}
          if(pts.length>1&&Math.abs(pts[0].x-pts[pts.length-1].x)<.01&&Math.abs(pts[0].y-pts[pts.length-1].y)<.01)pts.pop();
          if(pts.length<3)continue;
          if(idx===0){
            var m=new THREE.Mesh(new THREE.ShapeGeometry(new THREE.Shape(pts)),fmat);
            m.rotation.x=Math.PI/2;m.scale.z=-1;m.position.y=.45;m.renderOrder=1;
            grp.add(m);
          }
          var lp=[];for(var j=0;j<pts.length;j++)lp.push(new THREE.Vector3(pts[j].x,.95,pts[j].y));
          grp.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(lp),emat));
        }
      });
    });
    scene.add(grp);
    var chk=document.getElementById('m3d-l-parques');
    if(chk)grp.visible=!!chk.checked;
  }
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);
else boot();
})();
