import React, { useState, useEffect } from 'react';
import { useNavigate, Navigate } from 'react-router-dom';
import { MapContainer, TileLayer, Marker, Polygon, useMapEvents, useMap } from 'react-leaflet';
import L from 'leaflet';
import { useAppContext, type BoundingBox } from '../context/AppContext';

import 'leaflet/dist/leaflet.css';

// Fix for default marker icons in Leaflet with bundlers
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png';
import markerIcon from 'leaflet/dist/images/marker-icon.png';
import markerShadow from 'leaflet/dist/images/marker-shadow.png';

delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
    iconUrl: markerIcon,
    iconRetinaUrl: markerIcon2x,
    shadowUrl: markerShadow,
});

const MapClickDetector = ({ points, setPoints }: { points: L.LatLng[], setPoints: React.Dispatch<React.SetStateAction<L.LatLng[]>> }) => {
    useMapEvents({
        click(e) {
            if (points.length < 4) {
                setPoints((prev) => [...prev, e.latlng]);
            }
        }
    });
    return null;
};

const MapEffector = ({ mapBounds }: { mapBounds: L.LatLngBounds | null }) => {
    const map = useMap();
    useEffect(() => {
        if (mapBounds && map) {
            map.fitBounds(mapBounds);
        }
    }, [mapBounds, map]);
    return null;
};

const CropArea: React.FC = () => {
    const navigate = useNavigate();
    const { state, setRoiBoundingBox } = useAppContext();
    const selectedLocation = state.selectedLocation;

    const [bbox, setBbox] = useState<BoundingBox | null>(null);
    const [points, setPoints] = useState<L.LatLng[]>([]);
    const [mapBounds, setMapBounds] = useState<L.LatLngBounds | null>(null);

    const [manualInputs, setManualInputs] = useState({
        north: '', south: '', east: '', west: ''
    });

    // Compute bounding box when 4 points are selected
    useEffect(() => {
        if (points.length === 4) {
            const lats = points.map(p => p.lat);
            const lons = points.map(p => p.lng);
            setBbox({
                north: Math.max(...lats),
                south: Math.min(...lats),
                east: Math.max(...lons),
                west: Math.min(...lons)
            });
        } else {
            setBbox(null);
        }
    }, [points]);

    // Update manual inputs when bbox changes from map drawing
    useEffect(() => {
        if (bbox) {
            setManualInputs({
                north: bbox.north.toFixed(4),
                south: bbox.south.toFixed(4),
                east: bbox.east.toFixed(4),
                west: bbox.west.toFixed(4)
            });
        } else {
            setManualInputs({ north: '', south: '', east: '', west: '' });
        }
    }, [bbox]);

    const handleManualInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        setManualInputs({ ...manualInputs, [e.target.name]: e.target.value });
    };

    const applyManualBbox = () => {
        const n = parseFloat(manualInputs.north);
        const s = parseFloat(manualInputs.south);
        const e = parseFloat(manualInputs.east);
        const w = parseFloat(manualInputs.west);

        if (!isNaN(n) && !isNaN(s) && !isNaN(e) && !isNaN(w) && n > s && e > w) {
            setPoints([
                L.latLng(n, w),
                L.latLng(n, e),
                L.latLng(s, e),
                L.latLng(s, w)
            ]);
            setMapBounds(L.latLngBounds(L.latLng(s, w), L.latLng(n, e)));
        } else {
            alert("Please enter valid coordinates. North must be > South and East must be > West.");
        }
    };

    const clearSelection = () => {
        setPoints([]);
    };

    // Ensure we have a valid selection before rendering map
    if (!selectedLocation) {
        return <Navigate to="/search" replace />;
    }

    const lat = parseFloat(selectedLocation.lat);
    const lon = parseFloat(selectedLocation.lon);

    const handleConfirm = () => {
        if (bbox) {
            setRoiBoundingBox(bbox);
            console.log("Confirmed Bounding Box:", bbox);
            navigate('/timeline'); // Assume next step is timeline, update as needed
        } else {
            alert("Please draw a rectangle on the map to select the monitoring region.");
        }
    };

    return (
        <div className="w-screen h-screen bg-slate-900 text-slate-100 flex overflow-hidden">
            {/* Left Panel: Instructions */}
            <div className="w-[400px] h-full bg-slate-800 border-r border-slate-700 p-8 flex flex-col shadow-2xl z-10 relative">
                <h1 className="text-3xl font-bold text-white mb-8 tracking-tight">Select Monitoring Region</h1>
                
                <div className="bg-blue-900/40 border border-blue-500/30 rounded-xl p-5 mb-6 text-blue-100/90 shadow-inner">
                    <p className="font-semibold text-blue-300 mb-2">Instruction</p>
                    <p className="text-sm">Click 4 points on the map to define the corners of the mining site you want to monitor.</p>
                    <p className="text-xs font-mono mt-3 inline-block px-2 py-1 rounded bg-slate-900/50 border border-slate-700">
                        <span className={points.length === 4 ? "text-green-400" : "text-blue-300"}>Points selected: {points.length}/4</span>
                    </p>
                </div>

                <p className="text-slate-400 text-sm mb-auto leading-relaxed">
                    This selected region will define the area used for satellite deformation analysis.
                </p>

                {/* MANUAL CROP AREA */}
                <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-4 mb-4">
                    <div className="flex justify-between items-center mb-3">
                        <span className="text-sm font-semibold text-slate-300">Coordinates</span>
                        <button 
                            onClick={clearSelection}
                            className="text-xs bg-red-900/40 text-red-300 hover:bg-red-800/60 px-3 py-1.5 rounded transition-colors"
                        >
                            Clear
                        </button>
                    </div>
                    <div className="grid grid-cols-2 gap-3 mb-4">
                        <div>
                            <label className="text-xs text-slate-500 mb-1 block">North</label>
                            <input name="north" value={manualInputs.north} onChange={handleManualInputChange} className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-blue-500 transition-colors" placeholder="Latitude" />
                        </div>
                        <div>
                            <label className="text-xs text-slate-500 mb-1 block">South</label>
                            <input name="south" value={manualInputs.south} onChange={handleManualInputChange} className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-blue-500 transition-colors" placeholder="Latitude" />
                        </div>
                        <div>
                            <label className="text-xs text-slate-500 mb-1 block">East</label>
                            <input name="east" value={manualInputs.east} onChange={handleManualInputChange} className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-blue-500 transition-colors" placeholder="Longitude" />
                        </div>
                        <div>
                            <label className="text-xs text-slate-500 mb-1 block">West</label>
                            <input name="west" value={manualInputs.west} onChange={handleManualInputChange} className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-blue-500 transition-colors" placeholder="Longitude" />
                        </div>
                    </div>
                    <button 
                        onClick={applyManualBbox}
                        className="w-full bg-slate-700 hover:bg-slate-600 text-slate-200 text-sm py-2 rounded transition-colors font-medium border border-slate-600"
                    >
                        Apply Coordinates
                    </button>
                </div>

                <div className="flex flex-col gap-4 mt-2">
                    <button 
                        className={`py-4 rounded-lg font-semibold text-lg transition-all duration-200 ${bbox ? 'bg-blue-600 hover:bg-blue-500 text-white shadow-lg shadow-blue-900/50' : 'bg-slate-700 text-slate-400 cursor-not-allowed hidden'}`}
                        onClick={handleConfirm}
                        style={{ display: bbox ? 'block' : 'none' }}
                    >
                        Confirm
                    </button>
                    {!bbox && (
                        <button 
                            className="bg-slate-700 text-slate-400 py-4 rounded-lg font-semibold text-lg cursor-not-allowed"
                            disabled
                        >
                            Confirm
                        </button>
                    )}
                    <button 
                        className="bg-transparent hover:bg-slate-700/50 text-slate-300 border border-slate-600 py-4 rounded-lg font-semibold transition-colors duration-200"
                        onClick={() => navigate('/search')}
                    >
                        Change Location
                    </button>
                </div>
            </div>

            {/* Right Panel: Preview & Map */}
            <div className="flex-1 h-full flex flex-col relative bg-black/20">
                <div className="absolute top-0 left-0 w-full p-6 z-[1000] pointer-events-none drop-shadow-xl flex flex-col items-center">
                    <div className="bg-slate-900/80 backdrop-blur-md rounded-2xl px-10 py-4 border border-slate-700/80 shadow-2xl pointer-events-auto text-center">
                        <h2 className="text-xl font-bold text-slate-300 uppercase tracking-widest mb-1">Preview</h2>
                        <h3 className="text-3xl font-bold text-white">{selectedLocation.display_name.split(',')[0]}</h3>
                    </div>
                </div>

                <div className="flex-1 w-full relative z-0">
                    <MapContainer 
                        center={[lat, lon]} 
                        zoom={13} 
                        zoomSnap={0.1}
                        zoomControl={true}
                        className="w-full h-full"
                    >
                        <TileLayer
                            url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
                            attribution='Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community'
                        />
                        
                        <MapClickDetector points={points} setPoints={setPoints} />
                        <MapEffector mapBounds={mapBounds} />
                        
                        {points.map((p, i) => (
                            <Marker key={i} position={p} />
                        ))}
                        
                        {points.length === 4 && (
                            <Polygon 
                                positions={points} 
                                pathOptions={{ color: '#3b82f6', weight: 4, fillOpacity: 0.3 }} 
                            />
                        )}
                    </MapContainer>
                </div>
            </div>
        </div>
    );
};

export default CropArea;
