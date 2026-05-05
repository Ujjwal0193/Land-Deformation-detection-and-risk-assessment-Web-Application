import { useEffect } from 'react';
import { useMap } from 'react-leaflet';

interface MapControllerProps {
  mapCenter: [number, number] | null;
  zoom?: number;
}

const MapController: React.FC<MapControllerProps> = ({ mapCenter, zoom = 12 }) => {
  const map = useMap();

  useEffect(() => {
    if (mapCenter) {
      map.flyTo(mapCenter, zoom, {
        animate: true,
        duration: 2 // 2 seconds animation
      });
    }
  }, [mapCenter, zoom, map]);

  return null;
};

export default MapController;
