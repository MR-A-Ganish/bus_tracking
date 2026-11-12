let routeDraft = [];
let routeEditorMap = null;
let routeEditorMarkers = [];
let selectedRouteStop = 0;

function updateRouteOptions() {
  const selector = document.getElementById("route-editor-select");
  const previous = selector.value;
  selector.innerHTML = lookup.routes.map(route => `<option value="${route.id}">${escapeHtml(route.route_name)}</option>`).join("");
  const preferred = lookup.routes.find(route => route.route_name === "Vadalur to IFET College");
  selector.value = lookup.routes.some(route => String(route.id) === previous) ? previous : String(preferred?.id || lookup.routes[0]?.id || "");
  loadRouteDraft();
}

function loadRouteDraft() {
  const routeId = Number(document.getElementById("route-editor-select").value);
  routeDraft = lookup.stops.filter(stop => stop.route_id === routeId).sort((a,b) => a.sequence_order-b.sequence_order).map(stop => ({
    id:stop.id,stop_name:stop.stop_name,distance_from_start_km:Number(stop.distance_from_start_km),
    latitude:stop.latitude == null ? null : Number(stop.latitude),longitude:stop.longitude == null ? null : Number(stop.longitude)
  }));
  selectedRouteStop = 0;
  renderRouteRows();
  refreshRouteMap(true);
}

function renderRouteRows() {
  document.getElementById("route-stop-rows").innerHTML = routeDraft.map((stop,index) => `
    <tr data-index="${index}">
      <td>${index+1}</td>
      <td><input aria-label="Stop ${index+1} name" data-field="stop_name" maxlength="100" required value="${escapeHtml(stop.stop_name)}"></td>
      <td><input aria-label="Stop ${index+1} distance" data-field="distance_from_start_km" type="number" min="0" max="2000" step="any" required ${index===0?'readonly':''} value="${stop.distance_from_start_km ?? ""}" style="width:110px"></td>
      <td><input aria-label="Stop ${index+1} latitude" data-field="latitude" type="number" min="-90" max="90" step="any" required value="${stop.latitude ?? ""}" style="width:120px"></td>
      <td><input aria-label="Stop ${index+1} longitude" data-field="longitude" type="number" min="-180" max="180" step="any" required value="${stop.longitude ?? ""}" style="width:120px"></td>
      <td><button type="button" class="btn ghost sm" data-action="map">Map</button>
        ${index>0 && index<routeDraft.length-1 ? `<button type="button" class="btn ghost sm" data-action="up" ${index===1?'disabled':''} aria-label="Move stop ${index+1} up">Up</button>
        <button type="button" class="btn ghost sm" data-action="down" ${index===routeDraft.length-2?'disabled':''} aria-label="Move stop ${index+1} down">Down</button>
        <button type="button" class="btn danger sm" data-action="remove">Remove</button>` : '<span class="small-muted">Endpoint</span>'}
      </td>
    </tr>`).join("");
}

function initializeRouteMap() {
  if (!window.L) return;
  if (!routeEditorMap) {
    routeEditorMap = L.map("route-editor-map").setView([11.75,79.58],10);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:"&copy; OpenStreetMap contributors"}).addTo(routeEditorMap);
    routeEditorMap.on("click",event => {
      if (!routeDraft[selectedRouteStop]) return;
      routeDraft[selectedRouteStop].latitude = Number(event.latlng.lat.toFixed(6));
      routeDraft[selectedRouteStop].longitude = Number(event.latlng.lng.toFixed(6));
      renderRouteRows();
      refreshRouteMap();
    });
  }
  setTimeout(() => { routeEditorMap.invalidateSize(); refreshRouteMap(true); },50);
}

function refreshRouteMap(fit=false) {
  if (!routeEditorMap) return;
  routeEditorMarkers.forEach(marker => marker.remove());
  routeEditorMarkers = [];
  const points = [];
  routeDraft.forEach((stop,index) => {
    if (stop.latitude == null || stop.longitude == null) return;
    const point = [stop.latitude,stop.longitude];
    points.push(point);
    const marker = L.circleMarker(point,{radius:index===selectedRouteStop?10:6,color:index===selectedRouteStop?'#00e5ff':'#a78bfa'}).addTo(routeEditorMap);
    const label = document.createElement("span");
    label.textContent = `${index+1}. ${stop.stop_name}`;
    marker.bindPopup(label);
    marker.on("click",() => selectRouteStop(index));
    routeEditorMarkers.push(marker);
  });
  if (fit && points.length) routeEditorMap.fitBounds(points,{padding:[30,30],maxZoom:14});
}

function selectRouteStop(index) {
  selectedRouteStop = index;
  document.getElementById("route-map-help").textContent = `Click the map to set the location of ${routeDraft[index].stop_name || "this pickup stop"}.`;
  initializeRouteMap();
  refreshRouteMap();
}

document.getElementById("route-editor-select").addEventListener("change",loadRouteDraft);
document.getElementById("route-stop-rows").addEventListener("input",event => {
  const row = event.target.closest("tr[data-index]");
  const field = event.target.dataset.field;
  if (!row || !field) return;
  routeDraft[Number(row.dataset.index)][field] = field === "stop_name" ? event.target.value : event.target.value === "" ? null : Number(event.target.value);
  refreshRouteMap();
});
document.getElementById("route-stop-rows").addEventListener("click",event => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const index = Number(button.closest("tr").dataset.index);
  const action = button.dataset.action;
  if (action === "map") { selectRouteStop(index); return; }
  if (action === "remove") routeDraft.splice(index,1);
  if (action === "up" && index>1) [routeDraft[index-1],routeDraft[index]] = [routeDraft[index],routeDraft[index-1]];
  if (action === "down" && index<routeDraft.length-2) [routeDraft[index+1],routeDraft[index]] = [routeDraft[index],routeDraft[index+1]];
  selectedRouteStop = Math.min(selectedRouteStop,routeDraft.length-1);
  renderRouteRows();
  refreshRouteMap();
});
document.getElementById("route-add-stop").addEventListener("click",() => {
  if (routeDraft.length<2) return;
  const last = routeDraft.at(-1);
  const previous = routeDraft.at(-2);
  const index = routeDraft.length-1;
  routeDraft.splice(index,0,{id:null,stop_name:"",distance_from_start_km:Number(((previous.distance_from_start_km+last.distance_from_start_km)/2).toFixed(2)),latitude:null,longitude:null});
  renderRouteRows();
  selectRouteStop(index);
});
document.getElementById("route-stops-form").addEventListener("submit",async event => {
  event.preventDefault();
  const button = document.getElementById("route-save-stops");
  button.disabled = true;
  try {
    const routeId = Number(document.getElementById("route-editor-select").value);
    const result = await api(`/api/admin/routes/${routeId}/stops`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({stops:routeDraft})});
    if (!result.success) throw new Error(result.message);
    await loadLookup();
    document.querySelector("#route-stops-form .table-wrap").scrollLeft = 0;
    if (fleetMap) fleetMap.remove();
    fleetMap = null; fleetMarkers = {}; fleetInitialized = false;
    showAlert("stop-alert",true,"Route stops saved. Assign each student's pickup stop under Students.");
  } catch(error) { showAlert("stop-alert",false,error.message); }
  finally { button.disabled = false; }
});
