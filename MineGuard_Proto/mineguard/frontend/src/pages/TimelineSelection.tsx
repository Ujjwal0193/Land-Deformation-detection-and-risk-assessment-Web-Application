import React, { useState, useEffect } from 'react';
import { useNavigate, Navigate } from 'react-router-dom';
import { useAppContext, type TimelineConfig } from '../context/AppContext';

const TimelineSelection: React.FC = () => {
    const navigate = useNavigate();
    const { state, setTimelineConfig, setQueryResults } = useAppContext();

    // Default to a recent 5-year period if not set
    const currentYear = new Date().getFullYear();
    const defaultStartYear = currentYear - 5;
    
    // State initialization
    const [startYear, setStartYear] = useState<number>(state.timelineConfig?.startYear || defaultStartYear);
    const [endYear, setEndYear] = useState<number>(state.timelineConfig?.endYear || currentYear);
    const [frequency, setFrequency] = useState<'Monthly' | 'Quarterly' | 'Yearly'>(state.timelineConfig?.frequency || 'Monthly');
    const [orbitMode, setOrbitMode] = useState<'ASCENDING' | 'DESCENDING' | 'BOTH'>(state.timelineConfig?.orbitMode || 'ASCENDING');

    const [error, setError] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(false);

    // Navigation shield: ensure they came from the Crop step
    if (!state.roiBoundingBox) {
        return <Navigate to="/crop" replace />;
    }

    // Generate year options (Sentinel-1 launched in 2014)
    const yearOptions = Array.from({ length: currentYear - 2014 + 1 }, (_, i) => 2014 + i).reverse();

    // Re-verify validation upon every render cycle dependency
    useEffect(() => {
         // Logic validation
        if (endYear < startYear) {
            setError("End Year cannot be earlier than Start Year.");
        } else {
            setError(null);
        }
    }, [startYear, endYear]);


    // Approximation calculations for the side panel
    // InSAR needs 1 scene per frequency period. Consecutive scenes form interferometric pairs.
    // E.g. Yearly over 5 years → 5 scenes → 4 interferograms (Year1→Year2, Year2→Year3, etc.)
    const yearsOfData = Math.max(endYear - startYear + 1, 0);
    
    let scenesPerYear = 12; // Monthly
    if (frequency === 'Quarterly') scenesPerYear = 4;
    if (frequency === 'Yearly') scenesPerYear = 1;

    const multiplier = orbitMode === 'BOTH' ? 2 : 1;
    const estimatedScenes = (yearsOfData * scenesPerYear) * multiplier;
    const estimatedPairs = Math.max(estimatedScenes - (orbitMode === 'BOTH' ? 2 : 1), 0);
    
    // Approximating roughly 4 - 7.5GB per unzipped Sentinel-1 SLC scene
    const estimatedSizeMinGB = estimatedScenes * 4.0;
    const estimatedSizeMaxGB = estimatedScenes * 7.5;
    
    // Approximating roughly 15 minutes processing time per interferogram pair through SNAP graph builder
    const processingTimeMins = estimatedPairs * 15;
    
    // Format hours and minutes
    const processingTimeStr = processingTimeMins > 60 
        ? `${Math.floor(processingTimeMins / 60)}h ${processingTimeMins % 60}m` 
        : `${processingTimeMins}m`;


    const handleContinue = async () => {
        if (!error && estimatedScenes > 0 && !isLoading) {
            const config: TimelineConfig = {
                startYear,
                endYear,
                frequency,
                orbitMode
            };
            setTimelineConfig(config);
            console.log("Saved Timeline Config to Global AppContext:", config);
            
            setIsLoading(true);
            try {
                const queryPayload = {
                    north: state.roiBoundingBox!.north,
                    south: state.roiBoundingBox!.south,
                    east: state.roiBoundingBox!.east,
                    west: state.roiBoundingBox!.west,
                    start_year: startYear.toString(),
                    end_year: endYear.toString(),
                    frequency: frequency,
                    orbit_mode: orbitMode
                };

                // 120-second timeout — CDSE queries can take 60-90s for multi-year searches
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 120000);

                const queryRes = await fetch("http://localhost:8000/api/downloads/query-scenes", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(queryPayload),
                    signal: controller.signal
                });

                clearTimeout(timeoutId);

                if (!queryRes.ok) {
                    const errBody = await queryRes.json().catch(() => ({}));
                    throw new Error(errBody.detail || `Backend returned HTTP ${queryRes.status}`);
                }
                const queryData = await queryRes.json();
                
                setQueryResults(queryData);
                navigate('/download');
            } catch (err: any) {
                console.error(err);
                const msg = err.name === 'AbortError' 
                    ? "CDSE query timed out after 120s. Try a shorter date range or check your internet connection."
                    : (err.message || "CDSE API connection failed. Is the backend running?");
                setError(msg);
                setIsLoading(false);
            }
        }
    };

    // Construct static background map URL
    const bbox = state.roiBoundingBox;
    // We use Esri World Imagery export to fetch a static snapshot of the selected mine
    const mapWidth = window.innerWidth || 1920;
    const mapHeight = window.innerHeight || 1080;
    // Calculate a bounding box string for Esri
    const bboxStr = bbox ? `${bbox.west},${bbox.south},${bbox.east},${bbox.north}` : '-180,-90,180,90';
    
    // Using ArcGIS REST API to export a static map image of the exact bounding box, styled nicely
    const backgroundMapUrl = `https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?bbox=${bboxStr}&bboxSR=4326&size=${mapWidth},${mapHeight}&imageSR=4326&format=jpg&f=image`;

    return (
        <div className="relative w-screen h-screen flex items-center justify-center overflow-hidden bg-slate-950">
            {/* Ambient Map Background */}
            <div 
                className="absolute inset-0 z-0 scale-[1.02]"
                style={{
                    backgroundImage: `linear-gradient(to bottom, rgba(15, 23, 42, 0.4), rgba(15, 23, 42, 0.75)), url('${backgroundMapUrl}')`,
                    backgroundSize: 'cover',
                    backgroundPosition: 'center',
                    filter: 'grayscale(20%) contrast(110%) brightness(90%)',
                }}
            />

            {/* Glowing Accent behind the panel */}
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[700px] bg-blue-900/30 rounded-full blur-[150px] pointer-events-none z-0" />

            <div className="w-full max-w-[800px] bg-slate-900/85 backdrop-blur-xl border border-slate-700/60 p-10 rounded-3xl shadow-[0_0_80px_rgba(0,0,0,0.8)] flex flex-col gap-8 relative z-10 transition-all duration-300">
                
                {/* Header */}
                <header className="text-center border-b border-slate-700/50 pb-6">
                    <h1 className="text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-indigo-300 mb-2 tracking-tight">Timeline Configuration</h1>
                    <p className="text-slate-400 text-lg">Select the time period over which satellite deformation monitoring will be performed.</p>
                </header>

                <div className="flex gap-8 items-stretch pt-2">
                    
                    {/* Left Column: Form Fields */}
                    <div className="flex-1 flex flex-col gap-6 w-full justify-between">
                        
                        <div className="flex flex-col gap-2">
                            <label className="text-slate-300 font-semibold text-sm tracking-wide uppercase">Start Year</label>
                            <select 
                                className="bg-slate-900 border border-slate-600 text-slate-100 px-4 py-3.5 rounded-xl outline-none focus:border-blue-500 hover:border-slate-500 transition-colors shadow-inner appearance-none cursor-pointer"
                                value={startYear}
                                onChange={(e) => setStartYear(parseInt(e.target.value))}
                            >
                                {yearOptions.map(y => (
                                    <option key={`start-${y}`} value={y}>{y}</option>
                                ))}
                            </select>
                        </div>

                        <div className="flex flex-col gap-2">
                            <label className="text-slate-300 font-semibold text-sm tracking-wide uppercase">End Year</label>
                            <select 
                                className={`bg-slate-900 border ${error ? 'border-red-500 shadow-[0_0_10px_rgba(239,68,68,0.2)]' : 'border-slate-600'} text-slate-100 px-4 py-3.5 rounded-xl outline-none focus:border-blue-500 hover:border-slate-500 transition-colors shadow-inner appearance-none cursor-pointer`}
                                value={endYear}
                                onChange={(e) => setEndYear(parseInt(e.target.value))}
                            >
                                {yearOptions.map(y => (
                                    <option key={`end-${y}`} value={y}>{y}</option>
                                ))}
                            </select>
                            {error && <span className="text-red-400 text-xs font-medium ml-2">{error}</span>}
                        </div>

                        <div className="flex flex-col gap-2">
                            <label className="text-slate-300 font-semibold text-sm tracking-wide uppercase">Processing Frequency</label>
                            <select 
                                className="bg-slate-900 border border-slate-600 text-slate-100 px-4 py-3.5 rounded-xl outline-none focus:border-blue-500 hover:border-slate-500 transition-colors shadow-inner appearance-none cursor-pointer"
                                value={frequency}
                                onChange={(e) => setFrequency(e.target.value as any)}
                            >
                                <option value="Monthly">Monthly</option>
                                <option value="Quarterly">Quarterly</option>
                                <option value="Yearly">Yearly</option>
                            </select>
                        </div>
                        <div className="flex flex-col gap-2">
                            <label className="text-slate-300 font-semibold text-sm tracking-wide uppercase">Orbit Pass (V-H Decomposition)</label>
                            <div className="flex bg-slate-900 border border-slate-600 rounded-xl p-1 gap-1">
                                {(['ASCENDING', 'DESCENDING', 'BOTH'] as const).map(mode => (
                                    <button
                                        key={mode}
                                        onClick={() => setOrbitMode(mode)}
                                        className={`flex-1 py-2 text-xs font-bold rounded-lg transition-all ${
                                            orbitMode === mode 
                                            ? 'bg-blue-600 text-white shadow-lg' 
                                            : 'text-slate-500 hover:text-slate-300'
                                        }`}
                                    >
                                        {mode === 'BOTH' ? 'DUAL (2D)' : mode}
                                    </button>
                                ))}
                            </div>
                            <p className="text-[10px] text-slate-500 ml-1 italic">
                                * Dual-Orbit enables True Vertical + East-West measurement.
                            </p>
                        </div>

                        
                    </div>

                    {/* Right Column: Dynamic Data Volume Estimates Panel */}
                    <div className="w-[300px] bg-slate-900/60 backdrop-blur-md border border-slate-700/80 rounded-2xl p-6 flex flex-col justify-center relative overflow-hidden shadow-inner group">
                        
                        {/* Subtle animated background gradient */}
                        <div className="absolute inset-0 bg-gradient-to-br from-blue-900/10 to-transparent pointer-events-none group-hover:from-blue-900/20 transition-all duration-500" />
                        
                        <h3 className="text-sm font-bold text-slate-400 uppercase tracking-widest mb-6 pb-2 border-b border-slate-700/80 relative z-10">Data Volume</h3>
                        
                        <div className="flex flex-col gap-6 relative z-10">
                            <div>
                                <p className="text-slate-500 text-xs uppercase tracking-widest mb-1 flex justify-between items-center">
                                    <span>Estimated Scenes</span>
                                    <svg className="w-4 h-4 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                                    </svg>
                                </p>
                                <p className={`text-4xl font-mono font-bold transition-all duration-300 ${error ? 'text-slate-600' : 'text-blue-400'}`}>
                                    {error ? '0' : estimatedScenes}
                                </p>
                            </div>

                            <div>
                                <p className="text-slate-500 text-xs uppercase tracking-widest mb-1 flex justify-between items-center">
                                    <span>Interferometric Pairs</span>
                                    <svg className="w-4 h-4 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
                                    </svg>
                                </p>
                                <p className={`text-4xl font-mono font-bold transition-all duration-300 ${error ? 'text-slate-600' : 'text-indigo-400'}`}>
                                    {error ? '0' : estimatedPairs}
                                </p>
                            </div>
                            
                            <div>
                                <p className="text-slate-500 text-xs uppercase tracking-widest mb-1 flex justify-between items-center">
                                    <span>Download Size</span>
                                    <svg className="w-4 h-4 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
                                    </svg>
                                </p>
                                <p className={`text-2xl font-mono font-bold tracking-tight transition-all duration-300 ${error ? 'text-slate-600' : 'text-purple-400'}`}>
                                    {error ? '0' : `${estimatedSizeMinGB.toFixed(0)} - ${estimatedSizeMaxGB.toFixed(0)}`} <span className="text-lg font-normal opacity-70">GB</span>
                                </p>
                            </div>
                            
                            <div>
                                <p className="text-slate-500 text-xs uppercase tracking-widest mb-1 flex justify-between items-center">
                                    <span>Est. Processing Time</span>
                                    <svg className="w-4 h-4 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                                    </svg>
                                </p>
                                <p className={`text-3xl font-mono font-bold transition-all duration-300 ${error ? 'text-slate-600' : 'text-emerald-400'}`}>
                                    {error ? '0m' : processingTimeStr}
                                </p>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Footer Controls */}
                <div className="mt-4 border-t border-slate-700/80 pt-8 flex justify-between items-center relative z-10">
                    <div className="flex gap-4">
                        <button 
                            className="bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-600 hover:border-slate-500 py-3 px-6 rounded-xl font-semibold transition-colors duration-200 shadow-sm"
                            onClick={() => navigate('/crop')}
                        >
                            Back to Crop
                        </button>
                        <button 
                            className="bg-slate-800/50 hover:bg-slate-700/50 text-slate-400 border border-slate-700 hover:border-slate-500 py-3 px-6 rounded-xl font-semibold transition-colors duration-200 shadow-sm"
                            onClick={() => navigate('/search')}
                        >
                            Back to Search
                        </button>
                    </div>
                    {error ? (
                         <div className="bg-slate-800 border border-red-900 text-red-400 font-semibold py-3 px-10 rounded-xl cursor-not-allowed opacity-50">
                            Continue
                        </div>
                    ) : (
                        <button 
                            className={`font-bold py-3 px-12 rounded-xl transition-all duration-200 shadow-[0_4px_14px_0_rgba(59,130,246,0.39)] flex justify-center items-center h-[48px] ${isLoading ? 'bg-blue-800 cursor-wait' : 'bg-blue-600 hover:bg-blue-500 active:bg-blue-700 hover:shadow-[0_6px_20px_rgba(59,130,246,0.23)] hover:-translate-y-0.5'}`}
                            onClick={handleContinue}
                            disabled={isLoading}
                        >
                            {isLoading ? (
                                <svg className="animate-spin h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                </svg>
                            ) : (
                                <span className="text-white">Continue</span>
                            )}
                        </button>
                    )}
                </div>

            </div>
            
            {/* Background ambient lighting */}
            <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-blue-900/20 rounded-full blur-[120px] pointer-events-none" />
        </div>
    );
};

export default TimelineSelection;
