import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { Apartment } from "./api";

type Area = { lat: number; lng: number };

type Props = {
  area: Area | null;
  radiusKm: number;
  onAreaChange: (area: Area | null, radiusKm: number) => void;
  listings: Apartment[];
  onSelect: (apartment: Apartment) => void;
  colorFor: (apartment: Apartment) => string;
};

const BERN: L.LatLngExpression = [46.948, 7.4474];
const UNI_BERN: Area = { lat: 46.9505, lng: 7.4381 };
const RADIUS_MIN = 0.5;
const RADIUS_MAX = 10;

const pinIcon = L.divIcon({ className: "map-pin-icon", html: "<span></span>", iconSize: [22, 22], iconAnchor: [11, 11] });

// Map of Bern: click to set the centre of the search area, drag the pin to move it, and set the
// radius below. The dots are the listings currently loaded in the list.
export default function MapRadius({ area, radiusKm, onAreaChange, listings, onSelect, colorFor }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const areaLayer = useRef<L.LayerGroup | null>(null);
  const listingLayer = useRef<L.LayerGroup | null>(null);
  // Latest callbacks, so Leaflet's handlers (registered once) never use stale props.
  const latest = useRef({ onAreaChange, onSelect, radiusKm });
  latest.current = { onAreaChange, onSelect, radiusKm };

  useEffect(() => {
    if (!container.current) return;
    const instance = L.map(container.current, { center: BERN, zoom: 12, scrollWheelZoom: false });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(instance);
    areaLayer.current = L.layerGroup().addTo(instance);
    listingLayer.current = L.layerGroup().addTo(instance);
    instance.on("click", (event: L.LeafletMouseEvent) =>
      latest.current.onAreaChange({ lat: event.latlng.lat, lng: event.latlng.lng }, latest.current.radiusKm));
    map.current = instance;
    const resize = window.setTimeout(() => instance.invalidateSize(), 50);
    return () => {
      window.clearTimeout(resize);
      instance.remove();
      map.current = null;
    };
  }, []);

  // Search area: circle plus a draggable centre pin.
  useEffect(() => {
    const layer = areaLayer.current;
    if (!layer || !map.current) return;
    layer.clearLayers();
    if (!area) return;
    const circle = L.circle([area.lat, area.lng], {
      radius: radiusKm * 1000, color: "#e55242", weight: 2, fillColor: "#e55242", fillOpacity: 0.08, interactive: false,
    }).addTo(layer);
    const pin = L.marker([area.lat, area.lng], { draggable: true, icon: pinIcon, keyboard: false, title: "Centre of the search area" }).addTo(layer);
    pin.on("dragend", () => {
      const { lat, lng } = pin.getLatLng();
      latest.current.onAreaChange({ lat, lng }, latest.current.radiusKm);
    });
    map.current.fitBounds(circle.getBounds(), { padding: [16, 16], maxZoom: 15 }); // keep the whole area in view
  }, [area, radiusKm]);

  // Listings on this page, coloured by reply likelihood like the badges in the list.
  useEffect(() => {
    const layer = listingLayer.current;
    if (!layer) return;
    layer.clearLayers();
    for (const apartment of listings) {
      if (apartment.lat == null || apartment.lng == null) continue;
      L.circleMarker([apartment.lat, apartment.lng], {
        radius: 6, color: "#fff9f3", weight: 1.5, fillColor: colorFor(apartment), fillOpacity: 0.95,
      })
        .bindTooltip(`${apartment.title} · ${apartment.rent} · reply ${apartment.replyLabel.toLowerCase()}`, { direction: "top" })
        .on("click", (event) => {
          L.DomEvent.stopPropagation(event); // don't move the search area
          latest.current.onSelect(apartment);
        })
        .addTo(layer);
    }
  }, [listings, colorFor]);

  return (
    <div className="map-radius">
      <div aria-label="Map of Bern. Click to set the centre of the search area." className="map-box" ref={container} role="application" />
      <div className="label-row map-radius-row">
        <label htmlFor="radius">{area ? `Within ${radiusKm.toLocaleString("de-CH")} km` : "Search area"}</label>
        {area && (
          <button className="map-link" onClick={() => onAreaChange(null, radiusKm)} type="button">Remove area</button>
        )}
      </div>
      <input
        className="range-input" disabled={!area} id="radius" max={RADIUS_MAX} min={RADIUS_MIN} step="0.5" type="range" value={radiusKm}
        onChange={(event) => onAreaChange(area, Number(event.target.value))}
      />
      <small className="filter-hint">
        {area ? "Drag the pin to move the area. " : "Click the map to set the centre. "}
        <button className="map-link" onClick={() => onAreaChange(UNI_BERN, radiusKm)} type="button">Centre on Uni Bern</button>
      </small>
    </div>
  );
}
