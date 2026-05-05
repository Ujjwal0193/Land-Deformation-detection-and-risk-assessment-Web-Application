import { useEffect, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { MapContainer, TileLayer, Marker, Rectangle } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { useAppContext } from '../context/AppContext';

interface ResultsState {
    running: boolean;
    graphs: string[];
    dir: string;
}

// Metadata for the 3 known plot files — order and titles are fixed
const PLOT_PANELS = [
    {
        file: 'plot_01_horizontal_displacement.png',
        title: 'Horizontal (East–West) Displacement Per Year',
        description: 'Cumulative east–west ground movement derived from InSAR LOS measurements. Uses 2D ASC+DSC decomposition when both orbits are available; falls back to single-orbit geometric projection otherwise.',
        colSpan: 'md:col-span-1',
    },
    {
        file: 'plot_03_3d_trajectory.png',
        title: '3D Hotspot Displacement Trajectory',
        description: '3D trajectory of each monitored hotspot through time. X = east–west displacement (mm), Y = vertical displacement (mm), Z = time (decimal year). Shows both the direction and rate of ground deformation simultaneously.',
        colSpan: 'md:col-span-1',
    },
    {
        file: 'plot_02_los_displacement.png',
        title: 'LOS Displacement',
        description: 'Line-of-sight displacement per interferometric pair (bar chart) and cumulative LOS over the full time series (line chart). Negative values indicate ground moving away from the satellite (subsidence).',
        colSpan: 'md:col-span-1',
    },
];

function PlotPanels({ graphs, dir }: { graphs: string[]; dir: string }) {
    const graphSet = new Set(graphs);

    return (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            {PLOT_PANELS.map(panel => {
                const available = graphSet.has(panel.file);
                return (
                    <div
                        key={panel.file}
                        className={`${panel.colSpan} bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-2xl hover:border-slate-700 transition-colors group`}
                    >
                        {/* Header */}
                        <div className="bg-slate-950/60 border-b border-slate-800 px-5 py-4 flex justify-between items-start gap-4">
                            <div>
                                <h3 className="font-bold text-slate-200 text-base tracking-wide">{panel.title}</h3>
                                <p className="text-slate-500 text-xs mt-1 leading-relaxed max-w-xl">{panel.description}</p>
                            </div>
                            {available && (
                                <a
                                    href={`http://localhost:8000${dir}/${panel.file}`}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="shrink-0 text-xs text-blue-500 hover:text-blue-400 uppercase font-bold tracking-widest opacity-0 group-hover:opacity-100 transition-opacity mt-1"
                                >
                                    Open Full
                                </a>
                            )}
                        </div>

                        {/* Body */}
                        {available ? (
                            <div className="p-1 bg-white">
                                <img
                                    src={`http://localhost:8000${dir}/${panel.file}`}
                                    alt={panel.title}
                                    className="w-full h-auto object-contain"
                                />
                            </div>
                        ) : (
                            <div className="flex flex-col items-center justify-center py-16 text-slate-600">
                                <svg className="w-10 h-10 mb-3 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                                </svg>
                                <span className="text-sm">Plot not yet generated</span>
                            </div>
                        )}
                    </div>
                );
            })}

            {/* Show any unexpected extra plots so nothing is silently dropped */}
            {graphs.filter(g => !PLOT_PANELS.find(p => p.file === g)).sort().map((graphName, i) => (
                <div key={`extra-${i}`} className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-2xl hover:border-slate-700 transition-colors group">
                    <div className="bg-slate-950/50 border-b border-slate-800 px-5 py-3 flex justify-between items-center">
                        <span className="font-semibold text-slate-400 text-sm tracking-wide">
                            {graphName.replace('.png', '').replace(/_/g, ' ')}
                        </span>
                        <a
                            href={`http://localhost:8000${dir}/${graphName}`}
                            target="_blank"
                            rel="noreferrer"
                            className="text-xs text-blue-500 hover:text-blue-400 uppercase font-bold tracking-widest opacity-0 group-hover:opacity-100 transition-opacity"
                        >
                            Open Full
                        </a>
                    </div>
                    <div className="p-1 bg-white">
                        <img src={`http://localhost:8000${dir}/${graphName}`} alt={graphName} className="w-full h-auto object-contain max-h-[500px]" />
                    </div>
                </div>
            ))}
        </div>
    );
}

export default function ResultSelection() {
    const navigate = useNavigate();
    const [status, setStatus] = useState<ResultsState>({ running: true, graphs: [], dir: '' });
    const [errorMsg, setErrorMsg] = useState('');
    const [elapsedTime, setElapsedTime] = useState(0);
    const hasTriggered = useRef(false);
    
    // Modal state
    const { state } = useAppContext();
    const bbox = state.roiBoundingBox;
    const [showModal, setShowModal] = useState(false);
    const [savedHotspots, setSavedHotspots] = useState<any[]>([]);

    const handlePreview = async () => {
        try {
            const res = await fetch('http://localhost:8000/api/hotspots/list');
            const data = await res.json();
            setSavedHotspots(data.hotspots || []);
            setShowModal(true);
        } catch (e) {
            console.error("Failed to fetch hotspots", e);
        }
    };

    useEffect(() => {
        const triggerAnalysis = async () => {
            if (hasTriggered.current) return;
            hasTriggered.current = true;
            try {
                await fetch('http://localhost:8000/api/hotspots/run', { method: 'POST' });
            } catch (err) {
                console.error("Failed to trigger background analysis:", err);
                setErrorMsg("Backend connection failed.");
            }
        };

        triggerAnalysis();
    }, []);

    useEffect(() => {
        let pollInterval: ReturnType<typeof setInterval>;
        let timerInterval: ReturnType<typeof setInterval>;

        if (status.running && !errorMsg) {
            timerInterval = setInterval(() => {
                setElapsedTime(prev => prev + 1);
            }, 1000);

            pollInterval = setInterval(async () => {
                try {
                    const res = await fetch('http://localhost:8000/api/hotspots/results');
                    if (res.ok) {
                        const data: ResultsState = await res.json();
                        setStatus(data);
                    }
                } catch (err) {
                    console.error("Failed to poll results:", err);
                }
            }, 3000);
        }

        return () => {
            clearInterval(pollInterval);
            clearInterval(timerInterval);
        };
    }, [status.running, errorMsg]);

    const formatTime = (seconds: number) => {
        const m = Math.floor(seconds / 60);
        const s = seconds % 60;
        return `${m}:${s.toString().padStart(2, '0')}`;
    };

    return (
        <div className="h-[calc(100vh-32px)] overflow-y-auto bg-slate-950 text-white p-8 font-sans pb-32">
            <div className="flex justify-between items-start mb-8 border-b border-slate-800 pb-6">
                <div>
                    <h1 className="text-3xl font-bold bg-gradient-to-r from-teal-400 to-blue-500 bg-clip-text text-transparent">
                        Advanced Analysis Results
                    </h1>
                    <p className="text-slate-400 text-sm mt-2 max-w-2xl">
                        Millimetric Displacement, Subsidence Gradients, and Vertical Cross-Profiles based on Sentinel-1 Precise Orbit.
                    </p>
                </div>
                {!status.running && (
                    <div className="flex gap-4">
                        <button
                            onClick={handlePreview}
                            className="px-6 py-2.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-sm font-bold border border-slate-700 transition-all"
                        >
                            Preview Map
                        </button>
                        <button
                            onClick={() => navigate('/dashboard')}
                            className="px-6 py-2.5 rounded-lg bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white text-sm font-bold shadow-lg shadow-blue-500/20 transition-all"
                        >
                            Export & Finish
                        </button>
                    </div>
                )}
            </div>

            {errorMsg ? (
                <div className="bg-red-900/20 border border-red-800/50 p-6 rounded-2xl text-center">
                    <p className="text-red-400 font-semibold">{errorMsg}</p>
                    <button 
                        onClick={() => navigate('/hotspots')}
                        className="mt-4 bg-slate-800 hover:bg-slate-700 px-4 py-2 rounded-lg transition"
                    >
                        Go Back
                    </button>
                </div>
            ) : status.running ? (
                <div className="flex flex-col items-center justify-center bg-slate-900/50 border border-slate-800 rounded-2xl p-16 shadow-2xl mt-12">
                    <div className="w-16 h-16 border-4 border-slate-700 border-t-blue-500 rounded-full animate-spin mb-8"></div>
                    <h2 className="text-2xl font-bold text-slate-200 mb-3">Generating Advanced Analytics</h2>
                    <p className="text-slate-400 text-center max-w-lg mb-6 leading-relaxed">
                        The Python compute engine is currently unwrapping 2D radar phases and projecting displacement vectors. 
                        This performs heavy matrix operations across your entire Sentinel-1 pipeline.
                    </p>
                    <div className="bg-slate-950 rounded-lg px-6 py-3 font-mono text-blue-400 border border-slate-800 shadow-inner">
                        Elapsed Time: {formatTime(elapsedTime)}
                    </div>
                </div>
            ) : status.graphs.length === 0 ? (
                <div className="bg-slate-900/50 border border-slate-800 p-12 rounded-2xl text-center">
                    <h2 className="text-xl font-semibold text-slate-300">No graphs were generated.</h2>
                    <p className="text-slate-500 mt-2">Analysis completed but no PNG files were found in the results directory.</p>
                </div>
            ) : (
                <PlotPanels graphs={status.graphs} dir={status.dir} />
            )}

            {/* Modal Overlay */}
            {showModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 px-4 py-8 backdrop-blur-sm">
                    <div className="bg-slate-900 border border-slate-700 w-full max-w-5xl h-[85vh] flex flex-col rounded-2xl overflow-hidden shadow-2xl">
                        <div className="flex justify-between items-center px-6 py-4 border-b border-slate-800 bg-slate-950">
                            <div>
                                <h2 className="text-xl font-bold text-slate-200">Map Reference</h2>
                                <p className="text-xs text-slate-500 mt-1">Cross-reference analytical anomalies directly with geographic layout.</p>
                            </div>
                            <button onClick={() => setShowModal(false)} className="text-slate-400 hover:text-white p-2 text-3xl transition-colors">&times;</button>
                        </div>
                        <div className="flex-1 relative bg-black">
                            <MapContainer 
                                center={bbox ? [(bbox.north + bbox.south)/2, (bbox.east + bbox.west)/2] : [0,0]} 
                                zoom={14.5} 
                                className="w-full h-full"
                            >
                                <TileLayer url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}" />
                                
                                {bbox && (
                                    <Rectangle 
                                        bounds={[[bbox.south, bbox.west], [bbox.north, bbox.east]]} 
                                        pathOptions={{ color: '#3b82f6', weight: 2, fillOpacity: 0.1, dashArray: '5, 5' }} 
                                    />
                                )}
                                
                                {savedHotspots.map((h, i) => (
                                    <Marker 
                                        key={i} 
                                        position={[h.lat, h.lon]} 
                                        icon={L.divIcon({
                                            className: 'custom-hotspot-icon',
                                            html: `<div style="background-color: ${h.color}; width: 26px; height: 26px; border: 2px solid white; border-radius: 6px; box-shadow: 0 4px 6px rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; color: white; font-weight: 800; font-size: 13px; text-shadow: 0px 1px 2px rgba(0,0,0,0.8);">${h.label}</div>`,
                                            iconSize: [26, 26],
                                            iconAnchor: [13, 13]
                                        })}
                                    />
                                ))}
                            </MapContainer>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
