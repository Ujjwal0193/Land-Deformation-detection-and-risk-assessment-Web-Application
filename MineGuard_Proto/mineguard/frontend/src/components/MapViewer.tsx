import React from 'react';
import { MapContainer, TileLayer } from 'react-leaflet';
import MapController from './MapController';
import 'leaflet/dist/leaflet.css';
import './MapViewer.css';

interface MapViewerProps {
  children?: React.ReactNode;
  mapCenter?: [number, number] | null;
  mapZoom?: number;
}

const MapViewer: React.FC<MapViewerProps> = ({ children, mapCenter, mapZoom = 12 }) => {
  return (
    <div className="map-viewer-container">
      <MapContainer
        center={[0, 0]}
        zoom={2}
        zoomControl={true}
        zoomSnap={0.1}
        className="leaflet-map"
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <MapController mapCenter={mapCenter || null} zoom={mapZoom} />
        {children}
      </MapContainer>
    </div>
  );
};

export default MapViewer;
