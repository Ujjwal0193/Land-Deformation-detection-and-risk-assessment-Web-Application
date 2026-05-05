import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { MapContainer, TileLayer, Marker, useMapEvents, Rectangle } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { useAppContext } from '../context/AppContext';

// Matching Matplotlib's exact color cycle list dynamically
const HOTSPOT_COLORS = [
    '#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6',
    '#1abc9c', '#e67e22', '#34495e', '#e91e63', '#00bcd4',
];

interface Hotspot {
    lat: number;
    lon: number;
    color: string;
    label: string;
}

// Custom Leaflet hook to capture mouse clicks
function MapClickDetector({ onAddHotspot }: { onAddHotspot: (latlng: L.LatLng) => void }) {
    useMapEvents({
        click(e) {
            onAddHotspot(e.latlng);
        },
    });
    return null;
}

export default function HotspotSelection() {
    const navigate = useNavigate();
    const { state, setRoiBoundingBox } = useAppContext();
    const [hotspots, setHotspots] = useState<Hotspot[]>([]);
    const [isSaving, setIsSaving] = useState(false);
    const [errorMsg, setErrorMsg] = useState('');
    const [isLoadingRoi, setIsLoadingRoi] = useState(!state.roiBoundingBox);

    // If roiBoundingBox is missing from in-memory state (page refresh),
    // fetch it from the backend config.yaml
    useEffect(() => {
        if (state.roiBoundingBox) {
            setIsLoadingRoi(false);
            return;
        }
        const fetchRoi = async () => {
            try {
                const res = await fetch('http://localhost:8000/api/hotspots/roi');
                const data = await res.json();
                if (data.bbox) {
                    setRoiBoundingBox(data.bbox);
                }
            } catch (e) {
                console.error("Failed to fetch ROI from backend:", e);
            } finally {
                setIsLoadingRoi(false);
            }
        };
        fetchRoi();
    }, [state.roiBoundingBox, setRoiBoundingBox]);

    const bbox = state.roiBoundingBox;
    
    // Default center if no bbox is available
    const centerLat = bbox ? (bbox.north + bbox.south) / 2 : 51.505;
    const centerLon = bbox ? (bbox.east + bbox.west) / 2 : -0.09;
    
    const bounds: [[number, number], [number, number]] | undefined = bbox 
        ? [[bbox.south, bbox.west], [bbox.north, bbox.east]]
        : undefined;

    const handleAddHotspot = (latlng: L.LatLng) => {
        if (hotspots.length >= 10) {
            setErrorMsg('Maximum 10 hotspots allowed.');
            setTimeout(() => setErrorMsg(''), 3000);
            return;
        }
        
        // Ensure hotspot is strictly contained inside the bounding box
        if (bbox) {
            if (latlng.lat > bbox.north || latlng.lat < bbox.south || 
                latlng.lng > bbox.east || latlng.lng < bbox.west) {
                setErrorMsg('Hotspot must be placed within the marked Crop Area.');
                setTimeout(() => setErrorMsg(''), 3000);
                return;
            }
        }

        const newIndex = hotspots.length;
        const newHotspot: Hotspot = {
            lat: latlng.lat,
            lon: latlng.lng,
            color: HOTSPOT_COLORS[newIndex],
            label: `P${newIndex + 1}`
        };
        setHotspots([...hotspots, newHotspot]);
    };

    const handleClear = () => {
        setHotspots([]);
    };
    
    const handleUndo = () => {
        setHotspots(prev => prev.slice(0, -1));
    };

    const handleSaveAndAnalyze = async () => {
        if (hotspots.length === 0) {
            setErrorMsg('Please place at least one hotspot to analyze.');
            setTimeout(() => setErrorMsg(''), 3000);
            return;
        }

        setIsSaving(true);
        setErrorMsg('');

        try {
            const res = await fetch('http://localhost:8000/api/hotspots/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ hotspots })
            });

            const data = await res.json();

            if (!res.ok) {
                throw new Error(data.detail || 'Failed to save hotspots.');
            }

            // Successfully mapped coordinates. Proceed to the Dashboard Engine wrapper
            navigate('/results');
            
        } catch (err: any) {
            console.error('Error saving hotspots:', err);
            setErrorMsg(err.message || 'An unknown error occurred while saving.');
        } finally {
            setIsSaving(false);
        }
    };

    const createCustomIcon = (color: string, label: string) => {
        return L.divIcon({
            className: 'custom-hotspot-icon',
            html: `<div style="background-color: ${color}; width: 26px; height: 26px; border: 2px solid white; border-radius: 6px; box-shadow: 0 4px 6px rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; color: white; font-weight: 800; font-size: 13px; text-shadow: 0px 1px 2px rgba(0,0,0,0.8);">${label}</div>`,
            iconSize: [26, 26],
            iconAnchor: [13, 13]
        });
    };

    if (isLoadingRoi) {
        return (
            <div className="flex flex-col items-center justify-center h-full bg-[#13111C] text-slate-300">
                <div className="w-10 h-10 border-4 border-slate-700 border-t-blue-500 rounded-full animate-spin mb-4"></div>
                <p className="text-slate-400">Loading Crop Area...</p>
            </div>
        );
    }

    if (!bbox) {
        return (
            <div className="flex flex-col items-center justify-center h-full bg-[#13111C] text-slate-300">
                <h2 className="text-2xl font-bold mb-4">No Data Area Selected</h2>
                <p className="mb-6">You must define a Crop Region before selecting hotspots.</p>
                <button 
                    onClick={() => navigate('/crop')}
                    className="bg-blue-600 hover:bg-blue-500 text-white px-6 py-2 rounded-lg font-semibold transition-colors"
                >
                    Return to Crop Area
                </button>
            </div>
        );
    }

    return (
        <div className="flex h-[calc(100vh-60px)] w-full bg-[#13111C] text-slate-200 overflow-hidden font-sans">
            {/* Left Sidebar Control Panel */}
            <div className="w-[350px] min-w-[350px] max-w-[350px] h-full flex flex-col bg-slate-900 border-r border-slate-700/50 shadow-2xl z-10 p-6 overflow-y-auto">
                
                <div className="mb-6">
                    <h1 className="text-2xl font-bold text-white tracking-tight mb-2">Track Hotspots</h1>
                    <p className="text-sm text-slate-400">
                        Click on the designated Crop Area to drop pins. Max 10 points. Advanced Analytics will monitor Phase Displacement over these exact radar matrices.
                    </p>
                </div>
                
                {errorMsg && (
                    <div className="mb-4 bg-red-900/30 border border-red-800/50 text-red-400 px-4 py-3 rounded-lg text-sm text-center font-medium animate-pulse">
                        {errorMsg}
                    </div>
                )}
                
                <div className="flex justify-between items-center mb-4">
                    <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
                        Active Points ({hotspots.length}/10)
                    </span>
                    <div className="flex gap-2">
                        <button 
                            onClick={handleUndo} 
                            disabled={hotspots.length === 0}
                            className="text-xs px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded disabled:opacity-50 disabled:cursor-not-allowed transition"
                        >
                            Undo
                        </button>
                        <button 
                            onClick={handleClear} 
                            disabled={hotspots.length === 0}
                            className="text-xs px-2 py-1 bg-red-900/40 hover:bg-red-800/60 text-red-300 border border-red-900/50 rounded disabled:opacity-50 disabled:cursor-not-allowed transition"
                        >
                            Clear
                        </button>
                    </div>
                </div>

                <div className="flex-1 overflow-y-auto min-h-[200px] mb-6 pr-2 space-y-2">
                    {hotspots.length === 0 ? (
                        <div className="text-center py-10 border-2 border-dashed border-slate-800 rounded-xl text-slate-500">
                            No markers placed.
                        </div>
                    ) : (
                        hotspots.map((h, i) => (
                            <div key={i} className="flex items-center bg-slate-800/60 border border-slate-700/50 p-3 rounded-lg shadow-sm">
                                <div 
                                    className="w-4 h-4 rounded-sm shadow-inner flex-shrink-0" 
                                    style={{ backgroundColor: h.color }}
                                />
                                <span className="ml-3 font-semibold text-slate-300 w-8">{h.label}</span>
                                <div className="text-xs text-slate-500 flex-1 text-right font-mono truncate">
                                    {h.lat.toFixed(4)}, {h.lon.toFixed(4)}
                                </div>
                            </div>
                        ))
                    )}
                </div>

                <button
                    onClick={handleSaveAndAnalyze}
                    disabled={isSaving || hotspots.length === 0}
                    className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 disabled:text-slate-500 text-white py-4 rounded-xl font-bold text-lg transition-all duration-200 shadow-lg"
                >
                    {isSaving ? 'Mapping Pixels...' : 'Save & Analyze'}
                </button>
            </div>

            {/* Right Map Canvas */}
            <div className="flex-1 relative bg-black/50 z-0">
                <MapContainer 
                    center={[centerLat, centerLon]} 
                    zoom={14} 
                    zoomSnap={0.5}
                    className="w-full h-full"
                    maxBounds={bounds ? [
                        [bounds[0][0] - 0.5, bounds[0][1] - 0.5],
                        [bounds[1][0] + 0.5, bounds[1][1] + 0.5]
                    ] : undefined}
                >
                    <TileLayer
                        url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
                        attribution='Tiles &copy; Esri'
                    />
                    
                    <MapClickDetector onAddHotspot={handleAddHotspot} />

                    {/* Highly visible semi-transparent polygon highlighting exact Crop bounds */}
                    {bounds && (
                        <Rectangle 
                            bounds={bounds} 
                            pathOptions={{ 
                                color: '#3b82f6', 
                                weight: 2, 
                                fillOpacity: 0.2,
                                dashArray: '5, 5' 
                            }} 
                        />
                    )}

                    {hotspots.map((h, i) => (
                        <Marker 
                            key={i} 
                            position={[h.lat, h.lon]} 
                            icon={createCustomIcon(h.color, h.label)}
                        />
                    ))}
                </MapContainer>
            </div>
        </div>
    );
}
