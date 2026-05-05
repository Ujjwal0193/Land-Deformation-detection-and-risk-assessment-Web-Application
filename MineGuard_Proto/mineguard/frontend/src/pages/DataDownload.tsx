import React, { useState } from 'react';
import { useNavigate, Navigate } from 'react-router-dom';
import { useAppContext } from '../context/AppContext';

// Mock Lucide icons as simple SVGs to stay dependency-free if they aren't installed
const UploadCloudIcon = () => (
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="16 16 12 12 8 16"></polyline><line x1="12" y1="12" x2="12" y2="21"></line><path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"></path><polyline points="16 16 12 12 8 16"></polyline></svg>
);

const DownloadIcon = () => (
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
);


interface Scene {
    id: string;
    filename: string;
    acquisitionDate: string;
    [key: string]: any;
}

interface DownloadStatus {
    total_files: number;
    completed_files: number;
    current_file: string;
    progress_percentage: number;
    download_speed_mbps: number;
    estimated_time_remaining_sec: number;
}

const DataDownload: React.FC = () => {
    const navigate = useNavigate();
    const { state } = useAppContext();

    const [scenes, setScenes] = useState<Scene[]>(state.queryResults?.filteredScenes || []);
    const [status, setStatus] = useState<DownloadStatus>({
        total_files: 0,
        completed_files: 0,
        current_file: 'Idle',
        progress_percentage: 0,
        download_speed_mbps: 0,
        estimated_time_remaining_sec: 0
    });
    const [selectedScenes, setSelectedScenes] = useState<Set<string>>(
        new Set(state.queryResults?.filteredScenes.map(s => s.id) || [])
    );
    const [localDirectoryPath, setLocalDirectoryPath] = useState("");
    const [linkingStatus, setLinkingStatus] = useState<{message: string, isError: boolean} | null>(null);
    const [loading] = useState(false); // Forced false since Data runs instantly from RAM
    const [downloadStarted, setDownloadStarted] = useState(false);
    const [error] = useState<string | null>(null); // Kept for structural rendering logic

    // Handle Start Download Click — uses the streaming proxy for browser-native downloads
    const handleStartDownload = async () => {
        if (scenes.length === 0) return;
        
        setDownloadStarted(true);
        setStatus(prev => ({ ...prev, current_file: 'Initiating downloads via CDSE proxy...' }));

        // Scenes with valid CDSE IDs use the streaming proxy (browser-native download manager)
        const proxyScenes = scenes.filter(s => s.id && !s.id.startsWith('manual-') && selectedScenes.has(s.id));
        const manualOnly = proxyScenes.length === 0;

        if (!manualOnly) {
            // Stagger browser downloads to avoid overwhelming the connection
            for (let i = 0; i < proxyScenes.length; i++) {
                const scene = proxyScenes[i];
                const fname = scene.filename.endsWith('.zip') ? scene.filename : `${scene.filename}.zip`;
                const proxyUrl = `http://localhost:8000/api/downloads/proxy-download/${scene.id}?filename=${encodeURIComponent(fname)}`;
                
                // Open download in a hidden iframe to avoid popup blockers
                const iframe = document.createElement('iframe');
                iframe.style.display = 'none';
                iframe.src = proxyUrl;
                document.body.appendChild(iframe);

                // Clean up iframe after 10 seconds (download will continue independently)
                setTimeout(() => document.body.removeChild(iframe), 10000);

                setStatus(prev => ({
                    ...prev,
                    current_file: fname,
                    completed_files: i + 1,
                    total_files: proxyScenes.length,
                    progress_percentage: ((i + 1) / proxyScenes.length) * 100
                }));

                // 3-second stagger between downloads
                if (i < proxyScenes.length - 1) {
                    await new Promise(resolve => setTimeout(resolve, 3000));
                }
            }

            setStatus(prev => ({
                ...prev,
                current_file: 'All downloads dispatched to browser',
                progress_percentage: 100
            }));
        } else {
            // Only local files selected, no downloads needed
            setStatus(prev => ({
                ...prev,
                current_file: 'Local files linked and ready',
                total_files: selectedScenes.size,
                completed_files: selectedScenes.size,
                progress_percentage: 100
            }));
            setDownloadStarted(false); // Reset so they can still see it's done
        }
    };

    // Polling Status (Every 2 seconds)

    const toggleSelection = (id: string) => {
        const newSet = new Set(selectedScenes);
        if (newSet.has(id)) newSet.delete(id);
        else newSet.add(id);
        setSelectedScenes(newSet);
    };

    const handleLinkDirectory = async () => {
        if (!localDirectoryPath.trim()) return;
        setLinkingStatus({ message: "Scanning directory for InSAR scenes...", isError: false });

        try {
            const res = await fetch("http://localhost:8000/api/downloads/link-local-directory", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    directory_path: localDirectoryPath,
                    orbit_mode: state.timelineConfig?.orbitMode || "UNKNOWN"
                })
            });

            if (res.ok) {
                const data = await res.json();
                setLinkingStatus({ message: data.message || "Directory linked successfully.", isError: false });
                
                // Add the new linked scenes to the UI
                // Backend returns [{filename, orbitDirection}] so we can split into ASC/DSC sections
                if (data.linked_scenes && data.linked_scenes.length > 0) {
                    const now = Date.now();
                    const newScenes: Scene[] = data.linked_scenes.map(
                        (item: { filename: string; orbitDirection: string } | string, i: number) => {
                            const fname = typeof item === 'string' ? item : item.filename;
                            const orbit = typeof item === 'string' ? undefined : item.orbitDirection;
                            return {
                                id: `manual-${now}-${i}`,
                                filename: fname,
                                acquisitionDate: "Local Linked",
                                orbitDirection: orbit,
                            };
                        }
                    );
                    setScenes(prev => {
                        // Replace any previous local scenes; keep CDSE scenes
                        const cdseScenes = prev.filter(s => !s.id.startsWith('manual-'));
                        return [...newScenes, ...cdseScenes];
                    });
                    // Auto-select all linked scenes so "Proceed to Processing" becomes enabled
                    setSelectedScenes(prev => {
                        const updated = new Set(prev);
                        newScenes.forEach(s => updated.add(s.id));
                        return updated;
                    });
                }
            } else {
                const errData = await res.json();
                setLinkingStatus({ message: errData.detail || "Failed to link directory.", isError: true });
            }
        } catch (err) {
            setLinkingStatus({ message: "Network error linking directory.", isError: true });
        }
    };

    const handleDeleteAll = () => {
        setLocalDirectoryPath("");
        setLinkingStatus(null);
    };

    // Navigation shield
    if (!state.roiBoundingBox || !state.timelineConfig) {
        return <Navigate to="/timeline" replace />;
    }

    return (
        <div className="w-screen h-screen bg-slate-950 text-slate-200 overflow-hidden flex flex-col font-sans">
            
            {/* Header */}
            <header className="px-8 py-5 border-b border-slate-800 bg-slate-900/50 flex justify-between items-center z-10">
                <div>
                    <h1 className="text-2xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-indigo-400 tracking-wide flex items-center gap-3">
                        <DownloadIcon />
                        Data Acquisition
                    </h1>
                    <p className="text-slate-500 text-sm mt-1">Retrieving Sentinel-1 SLC datasets for interferometry</p>
                </div>                <div className="flex gap-4">
                    <button 
                        onClick={() => navigate('/timeline')}
                        className="px-5 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-sm font-semibold transition-colors"
                    >
                        Back to Timeline
                    </button>
                    
                    {/* Start Download Sequence Button */}
                    {downloadStarted && status.completed_files < status.total_files ? (
                        <button 
                            disabled 
                            className="px-6 py-2.5 bg-slate-800 text-slate-400 rounded-lg text-sm font-bold border border-slate-700 opacity-50 cursor-not-allowed"
                        >
                            Downloading Array...
                        </button>
                    ) : (
                        <button 
                            onClick={handleStartDownload}
                            className={`px-6 py-2.5 rounded-lg text-sm font-bold shadow-lg transition-all z-10 ${
                                selectedScenes.size === 0 
                                ? 'bg-slate-800 text-slate-500 cursor-not-allowed'
                                : 'bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white shadow-blue-500/20 cursor-pointer'
                            }`}
                            disabled={selectedScenes.size === 0}
                        >
                            Start Download Sequence
                        </button>
                    )}

                    {/* Proceed to Processing Button */}
                    <button 
                        onClick={() => navigate('/process')}
                        disabled={!(
                            (status.completed_files > 0 && status.completed_files === status.total_files) || 
                            Array.from(selectedScenes).some(id => id.startsWith('manual-'))
                        )}
                        className={`px-6 py-2.5 rounded-lg text-sm font-bold shadow-lg transition-all z-10 ${
                            ((status.completed_files > 0 && status.completed_files === status.total_files) || Array.from(selectedScenes).some(id => id.startsWith('manual-')))
                            ? 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-500/20 cursor-pointer'
                            : 'bg-slate-800 text-slate-500 cursor-not-allowed border border-slate-700'
                        }`}
                    >
                        Proceed to Processing
                    </button>
                </div>
            </header>

            {/* Main Content Area */}
            <div className="flex-1 flex gap-6 p-6 overflow-hidden">
                
                {/* LEFT PANEL */}
                <div className="w-1/2 flex flex-col gap-6 h-full">
                    
                    {/* Scene List — Split by Orbit Direction */}
                    <div className="flex-1 bg-slate-900/60 border border-slate-800 rounded-2xl overflow-hidden flex flex-col">
                        <div className="px-5 py-4 border-b border-slate-800 bg-slate-900 flex justify-between items-center">
                            <h2 className="font-semibold text-lg text-slate-300 tracking-wide">Target Scenes Filtered</h2>
                            <div className="flex gap-3">
                                <span className="text-xs font-bold px-3 py-1 bg-purple-900/40 text-purple-400 rounded-full border border-purple-800/50">
                                    Size: {state.queryResults?.estimatedDownloadSize || '--'}
                                </span>
                                <span className="text-xs font-bold px-3 py-1 bg-blue-900/40 text-blue-400 rounded-full border border-blue-800/50">
                                    {scenes.length} files total
                                </span>
                            </div>
                        </div>

                        <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
                            {loading ? (
                                <div className="h-full flex items-center justify-center text-slate-500">
                                    <div className="flex flex-col items-center gap-3">
                                        <div className="w-8 h-8 rounded-full border-2 border-slate-700 border-t-blue-500 animate-spin"></div>
                                        <span>Querying Copernicus Data Space Ecosystem...</span>
                                    </div>
                                </div>
                            ) : error ? (
                                <div className="p-4 bg-red-900/20 border border-red-800/50 rounded-lg text-red-400 text-sm">
                                    {error}
                                </div>
                            ) : scenes.length === 0 ? (
                                <div className="h-full flex flex-col items-center justify-center gap-5 text-center p-6">
                                    <div className="w-14 h-14 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-500">
                                        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/></svg>
                                    </div>
                                    <div>
                                        <p className="text-slate-300 font-semibold mb-2">No Sentinel-1 scenes found</p>
                                        <p className="text-slate-500 text-xs leading-relaxed max-w-xs">
                                            CDSE returned 0 IW SLC scenes for the selected ROI, orbit pass, and time window.
                                            Try a wider date range or a different orbit mode.
                                        </p>
                                    </div>
                                    <button
                                        onClick={() => navigate('/timeline')}
                                        className="px-5 py-2 bg-blue-900/30 hover:bg-blue-900/50 text-blue-400 border border-blue-800/50 rounded-xl text-sm font-semibold transition-colors"
                                    >
                                        Adjust Timeline &amp; Retry
                                    </button>
                                </div>
                            ) : (() => {
                                // Partition scenes by orbit direction
                                const ascScenes = scenes.filter(s => s.orbitDirection?.toUpperCase() === 'ASCENDING');
                                const dscScenes = scenes.filter(s => s.orbitDirection?.toUpperCase() === 'DESCENDING');
                                const localScenes = scenes.filter(s => !['ASCENDING','DESCENDING'].includes(s.orbitDirection?.toUpperCase()));
                                const missingAsc: string[] = state.queryResults?.missingCoverage?.ascending || [];
                                const missingDsc: string[] = state.queryResults?.missingCoverage?.descending || [];

                                const SceneRow = ({ scene, idx }: { scene: Scene; idx: number }) => (
                                    <div
                                        key={scene.id}
                                        onClick={() => !downloadStarted && toggleSelection(scene.id)}
                                        className={`p-3 bg-slate-800/50 hover:bg-slate-800 border ${selectedScenes.has(scene.id) ? 'border-indigo-500/70 shadow-[0_0_10px_rgba(99,102,241,0.1)]' : 'border-slate-700/50'} rounded-lg transition-all flex justify-between items-center group ${!downloadStarted ? 'cursor-pointer' : ''}`}
                                    >
                                        <div className="flex items-center gap-4 overflow-hidden w-full">
                                            <div className={`w-5 h-5 rounded flex items-center justify-center border transition-colors flex-shrink-0 ${selectedScenes.has(scene.id) ? 'bg-indigo-500 border-indigo-400 text-white' : 'border-slate-600 bg-slate-900/50'}`}>
                                                {selectedScenes.has(scene.id) && <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>}
                                            </div>
                                            <div className="overflow-hidden w-full">
                                                <div className="text-xs text-blue-400 font-mono mb-1">{scene.acquisitionDate}</div>
                                                <div className="text-sm font-medium text-slate-300 truncate w-full" title={scene.filename}>
                                                    {scene.filename}
                                                </div>
                                            </div>
                                        </div>
                                        <div className="pl-4">
                                            {!downloadStarted ? (
                                                <span className={`text-xs font-bold uppercase tracking-wider ${selectedScenes.has(scene.id) ? 'text-indigo-400' : 'text-slate-500'}`}>
                                                    {selectedScenes.has(scene.id) ? 'Selected' : 'Skipped'}
                                                </span>
                                            ) : idx < status.completed_files ? (
                                                <span className="text-emerald-400 text-xs font-bold uppercase tracking-wider">Ready</span>
                                            ) : idx === status.completed_files && status.progress_percentage > 0 ? (
                                                <div className="w-16 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                                                    <div className="h-full bg-blue-500 animate-pulse" style={{ width: `${status.progress_percentage}%` }}></div>
                                                </div>
                                            ) : (
                                                <span className="text-slate-600 text-xs font-bold uppercase tracking-wider">Queue</span>
                                            )}
                                        </div>
                                    </div>
                                );

                                // Shows a notice when some expected years have no scene in CDSE
                                const MissingYearsNotice = ({ years, orbitLabel }: { years: string[]; orbitLabel: string }) => {
                                    if (years.length === 0) return null;
                                    return (
                                        <div className="mt-2 mx-1 px-3 py-2.5 bg-amber-950/30 border border-amber-800/40 rounded-lg flex items-start gap-2.5">
                                            <svg className="flex-shrink-0 mt-0.5 text-amber-500" xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                                            <p className="text-[11px] text-amber-400/80 leading-relaxed">
                                                <span className="font-bold text-amber-400">No {orbitLabel} data for {years.join(', ')}.</span>
                                                {' '}CDSE confirmed no Sentinel-1 IW SLC scenes exist for this location in {years.length === 1 ? 'that year' : 'those years'}.
                                                This is a genuine archive gap — not a system error.
                                            </p>
                                        </div>
                                    );
                                };

                                const OrbitSection = ({
                                    label, badge, badgeColor, borderColor, sectionScenes, missingYears, orbitLabel
                                }: {
                                    label: string; badge: string;
                                    badgeColor: string; borderColor: string;
                                    sectionScenes: Scene[];
                                    missingYears: string[];
                                    orbitLabel: string;
                                }) => (
                                    <div className={`mb-4 border ${borderColor} rounded-xl overflow-hidden`}>
                                        <div className={`px-4 py-2.5 flex items-center justify-between bg-slate-900/80`}>
                                            <div className="flex items-center gap-2.5">
                                                <span className={`text-xs font-bold px-2.5 py-0.5 rounded-full ${badgeColor}`}>{badge}</span>
                                                <span className="text-sm font-semibold text-slate-300 uppercase tracking-widest">{label}</span>
                                            </div>
                                            <span className="text-xs text-slate-500 font-mono">{sectionScenes.length} scenes</span>
                                        </div>
                                        <div className="p-3 flex flex-col gap-2">
                                            {sectionScenes.length === 0 ? (
                                                <p className="text-xs text-slate-600 italic text-center py-3">No scenes for this orbit</p>
                                            ) : (
                                                sectionScenes.map((scene, idx) => (
                                                    <SceneRow key={scene.id} scene={scene} idx={idx} />
                                                ))
                                            )}
                                            <MissingYearsNotice years={missingYears} orbitLabel={orbitLabel} />
                                        </div>
                                    </div>
                                );

                                return (
                                    <div className="flex flex-col">
                                        <OrbitSection
                                            label="Ascending Orbit"
                                            badge="ASC ↗"
                                            badgeColor="bg-blue-900/60 text-blue-300 border border-blue-700/50"
                                            borderColor="border-blue-800/30"
                                            sectionScenes={ascScenes}
                                            missingYears={missingAsc}
                                            orbitLabel="ascending"
                                        />
                                        <OrbitSection
                                            label="Descending Orbit"
                                            badge="DSC ↘"
                                            badgeColor="bg-amber-900/60 text-amber-300 border border-amber-700/50"
                                            borderColor="border-amber-800/30"
                                            sectionScenes={dscScenes}
                                            missingYears={missingDsc}
                                            orbitLabel="descending"
                                        />
                                        {localScenes.length > 0 && (
                                            <OrbitSection
                                                label="Local Files"
                                                badge="LOCAL"
                                                badgeColor="bg-slate-800 text-slate-400 border border-slate-600"
                                                borderColor="border-slate-700/40"
                                                sectionScenes={localScenes}
                                                missingYears={[]}
                                                orbitLabel="local"
                                            />
                                        )}
                                    </div>
                                );
                            })()}
                        </div>
                    </div>

                    {/* Download Metrics */}
                    <div className="bg-slate-900/80 border border-slate-800 p-6 rounded-2xl relative overflow-hidden">
                        <div className="flex justify-between items-end mb-2">
                            <div>
                                <h3 className="text-lg font-bold text-slate-200 mb-1">Queue Progress</h3>
                                <p className="text-sm text-slate-500">Files Processed Successfully</p>
                            </div>
                            <div className="text-4xl font-mono font-bold text-blue-400">
                                {status.completed_files} <span className="text-2xl text-slate-600">/ {status.total_files || '--'}</span>
                            </div>
                        </div>
                    </div>

                </div>

                {/* RIGHT PANEL */}
                <div className="w-1/2 flex flex-col gap-6 h-full">
                    
                    {/* Active Download Banner */}
                    <div className="bg-gradient-to-br from-indigo-900/40 to-slate-900 border border-indigo-500/30 p-6 rounded-2xl relative overflow-hidden group">
                        <div className="flex items-center gap-4 mb-4 relative z-10">
                            {downloadStarted ? (
                                <div className="w-3 h-3 rounded-full bg-indigo-400 animate-pulse"></div>
                            ) : (
                                <div className="w-3 h-3 rounded-full bg-slate-600"></div>
                            )}
                            <h2 className="text-lg font-bold tracking-widest text-indigo-200 uppercase">Data Downloader Status</h2>
                        </div>
                        
                        <div className="bg-slate-950/50 p-5 rounded-xl border border-indigo-900/50 relative z-10">
                            <p className="text-sm text-slate-300 leading-relaxed">
                                {downloadStarted ? (
                                    <>
                                        <span className="font-bold text-emerald-400 mb-2 block">Downloads Dispatched!</span>
                                        Your browser is now downloading the selected 7GB+ files securely in the background. Press <b>CTRL+J</b> to view your live download speed and time remaining inside your Browser Download Manager. 
                                    </>
                                ) : (
                                    <>
                                        Select the scenes you want from the left panel and click <b>Start Download Sequence</b>. The local server proxy will trigger ultra-fast direct browser downloads.
                                    </>
                                )}
                            </p>
                        </div>
                    </div>

                    {/* Instruction Panel */}
                    <div className="bg-slate-900/60 border border-slate-800 p-6 rounded-2xl">
                         <h3 className="text-[14px] font-bold text-slate-400 uppercase tracking-widest mb-3 flex items-center gap-2">
                             <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
                             What happens next?
                        </h3>
                        <p className="text-sm text-slate-400 leading-relaxed">
                            Because these are massive files, your browser securely saves them to your computer's default `Downloads` folder. <br/><br/>
                            Once your browser finishes downloading the `.zip` files, paste the absolute path to your `Downloads` folder into the <b>Link Local Directory</b> box below. This will securely bind your downloaded files to the MineGuard internal pipeline for interferometric processing.
                        </p>
                    </div>

                    {/* Manual Override Section */}
                    <div className="flex-1 bg-slate-900/60 border border-slate-800 rounded-2xl p-6 flex flex-col">
                        <div className="flex justify-between items-center mb-5">
                            <h3 className="text-[14px] font-bold text-slate-400 uppercase tracking-widest flex items-center gap-2">
                                <UploadCloudIcon />
                                Link Local Directory
                            </h3>
                            <button className="px-3 py-1.5 text-xs font-bold border border-red-900/50 bg-red-900/10 hover:bg-red-900/30 text-red-400 rounded-lg transition-colors" onClick={handleDeleteAll}>
                                RESET FOLDER
                            </button>
                        </div>

                        <div className="flex flex-col gap-6">
                            <p className="text-sm text-slate-400 leading-relaxed">
                                Avoid downloading massive 7GB SLC files through the browser. If you already possess the `.zip` Sentinel-1 datasets locally, specify the absolute folder path below. The AI will instantly bypass bandwidth limits and symlink them directly into the pipeline's raw staging environment.
                            </p>
                            
                            <input
                                type="text"
                                value={localDirectoryPath}
                                onChange={(e) => setLocalDirectoryPath(e.target.value)}
                                placeholder="e.g. C:\Users\SatelliteData\Sentinel1\"
                                className="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-3 text-slate-200 font-mono text-sm focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all placeholder:text-slate-600"
                            />
                            
                            {linkingStatus && (
                                <div className={`text-sm px-4 py-3 rounded-lg border ${linkingStatus.isError ? 'bg-red-900/20 text-red-400 border-red-800/50' : 'bg-emerald-900/20 text-emerald-400 border-emerald-800/50'}`}>
                                    {linkingStatus.message}
                                </div>
                            )}
                            
                            <button 
                                onClick={handleLinkDirectory}
                                disabled={!localDirectoryPath.trim()}
                                className={`w-full py-3 mt-2 flex items-center justify-center gap-2 rounded-xl font-bold transition-colors border ${localDirectoryPath.trim() ? 'bg-blue-600/10 hover:bg-blue-600/20 border-blue-500/30 text-blue-400 shadow-[0_0_15px_rgba(59,130,246,0.15)]' : 'bg-slate-800/50 text-slate-500 border-slate-700 cursor-not-allowed'}`}
                            >
                                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21.2 15c.7-1.2 1-2.5.7-3.9-.6-2-2.4-3.5-4.4-3.5h-1.2c-.7-3-3.2-5.2-6.2-5.6-3-.3-5.9 1.3-7.3 4-1.2 2.5-1 6.5.5 8.8m8.7-1.6V21"/><path d="M16 16l-4-4-4 4"/></svg>
                                BIND LOCAL DIRECTORY
                            </button>
                        </div>
                    </div>
                </div>

            </div>
            
            <style>{`
                .custom-scrollbar::-webkit-scrollbar {
                    width: 6px;
                }
                .custom-scrollbar::-webkit-scrollbar-track {
                    background: rgba(15, 23, 42, 0.5);
                    border-radius: 4px;
                }
                .custom-scrollbar::-webkit-scrollbar-thumb {
                    background: rgba(51, 65, 85, 1);
                    border-radius: 4px;
                }
                .custom-scrollbar::-webkit-scrollbar-thumb:hover {
                    background: rgba(71, 85, 105, 1);
                }
            `}</style>
        </div>
    );
};

export default DataDownload;
