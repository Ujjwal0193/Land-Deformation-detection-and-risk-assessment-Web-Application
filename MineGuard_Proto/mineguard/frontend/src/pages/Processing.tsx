import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

// --- Interfaces ---
interface ProcessingTask {
    task_id: string;
    master_scene: string;
    slave_scene: string;
    master_date: string;
    slave_date: string;
    orbit?: string;
    status: 'pending' | 'processing' | 'complete' | 'failed';
    estimated_progress: number;
    elapsed_seconds?: number;
    error_message?: string;
    gpt_alive?: boolean;
    gpt_stalled?: boolean;
    gpt_pid?: number;
    gpt_log?: string;
}

interface QueueStatus {
    tasks: ProcessingTask[];
    total: number;
    pending: number;
    processing: number;
    complete: number;
    failed: number;
    all_complete: boolean;
    worker_active: boolean;
    gpt_active: boolean;
}

// --- Helper: Extract year from scene filename or date string ---
const extractYear = (dateStr: string): string => {
    if (!dateStr) return '????';
    // Try ISO date first
    const isoMatch = dateStr.match(/^(\d{4})/);
    if (isoMatch) return isoMatch[1];
    // Try Sentinel-1 filename format
    const fnMatch = dateStr.match(/_(\d{4})\d{4}T/);
    if (fnMatch) return fnMatch[1];
    return '????';
};

// --- Helper: Format elapsed time ---
const formatElapsed = (seconds: number): string => {
    if (seconds <= 0) return '0s';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
};

// --- SVG Icons ---
const GearIcon = () => (
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="3"></circle>
        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
    </svg>
);

const CheckIcon = () => (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="20 6 9 17 4 12"></polyline>
    </svg>
);

const AlertIcon = () => (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10"></circle>
        <line x1="12" y1="8" x2="12" y2="12"></line>
        <line x1="12" y1="16" x2="12.01" y2="16"></line>
    </svg>
);

const PlayIcon = () => (
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polygon points="5 3 19 12 5 21 5 3"></polygon>
    </svg>
);

const ArrowRightIcon = () => (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="5" y1="12" x2="19" y2="12"></line>
        <polyline points="12 5 19 12 12 19"></polyline>
    </svg>
);

// --- Main Component ---
const Processing: React.FC = () => {
    const navigate = useNavigate();

    const [queueStatus, setQueueStatus] = useState<QueueStatus>({
        tasks: [], total: 0, pending: 0, processing: 0,
        complete: 0, failed: 0, all_complete: false, worker_active: false, gpt_active: false,
    });
    const [isStarting, setIsStarting] = useState(false);
    const [hasStarted, setHasStarted] = useState(false);
    const [hasLoaded, setHasLoaded] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [isResetting, setIsResetting] = useState(false);
    const [isStopping, setIsStopping] = useState(false);

    // Poll queue status every 3 seconds
    const fetchStatus = useCallback(async () => {
        try {
            const res = await fetch('http://localhost:8000/api/processing/queue-status');
            if (res.ok) {
                const data: QueueStatus = await res.json();
                setQueueStatus(data);
                setHasLoaded(true);
                if (data.worker_active) {
                    setHasStarted(true);
                }
            }
        } catch (e) {
            // Silently fail on poll errors — hasLoaded stays false until backend responds
        }
    }, []);

    useEffect(() => {
        fetchStatus(); // Initial fetch
        const interval = setInterval(fetchStatus, 3000);
        return () => clearInterval(interval);
    }, [fetchStatus]);

    const hasStalled = queueStatus.tasks.some(t => t.gpt_stalled);

    const handleStopWorker = async () => {
        setIsStopping(true);
        setError(null);
        try {
            const res = await fetch('http://localhost:8000/api/processing/stop', { method: 'POST' });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Stop failed');
            setHasStarted(false);
            await fetchStatus();
        } catch (err: any) {
            setError(err.message || 'Failed to stop worker');
        } finally {
            setIsStopping(false);
        }
    };

    const handleResetStuck = async () => {
        setIsResetting(true);
        setError(null);
        try {
            const res = await fetch('http://localhost:8000/api/processing/reset-stuck', { method: 'POST' });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Reset failed');
            await fetchStatus();
        } catch (err: any) {
            setError(err.message || 'Failed to reset stuck tasks');
        } finally {
            setIsResetting(false);
        }
    };

    // Start processing
    const handleStartProcessing = async () => {
        setIsStarting(true);
        setError(null);
        try {
            const res = await fetch('http://localhost:8000/api/processing/start', {
                method: 'POST',
            });
            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.detail || 'Failed to start processing');
            }
            // If all pairs were already on disk, the API skips them and returns
            // all_skipped=true — just refresh status; the queue will show all_complete.
            setHasStarted(true);
            // Immediately poll once so UI reflects the updated queue state
            await fetchStatus();
        } catch (err: any) {
            setError(err.message || 'Failed to start SNAP worker');
        } finally {
            setIsStarting(false);
        }
    };

    // Compute overall progress
    const overallProgress = queueStatus.total > 0
        ? ((queueStatus.complete / queueStatus.total) * 100)
        : 0;

    // Status color helpers
    const getStatusColor = (status: string) => {
        switch (status) {
            case 'complete': return 'text-emerald-400';
            case 'processing': return 'text-blue-400';
            case 'failed': return 'text-red-400';
            default: return 'text-slate-500';
        }
    };

    const getStatusBgGradient = (status: string) => {
        switch (status) {
            case 'complete': return 'from-emerald-500/20 to-emerald-900/10';
            case 'processing': return 'from-blue-500/20 to-indigo-900/10';
            case 'failed': return 'from-red-500/20 to-red-900/10';
            default: return 'from-slate-800/30 to-slate-900/20';
        }
    };

    const getStatusBorderColor = (status: string) => {
        switch (status) {
            case 'complete': return 'border-emerald-500/40';
            case 'processing': return 'border-blue-500/40';
            case 'failed': return 'border-red-500/40';
            default: return 'border-slate-700/50';
        }
    };

    return (
        <div className="min-h-screen bg-slate-950 text-white px-8 py-6">
            {/* Header */}
            <div className="flex justify-between items-start mb-6">
                <div>
                    <h1 className="text-3xl font-bold bg-gradient-to-r from-blue-400 to-indigo-400 bg-clip-text text-transparent">
                        Processing Phase
                    </h1>
                    <p className="text-slate-400 text-sm mt-1">
                        SNAP GPT Interferometric Processing Engine
                    </p>
                </div>
                <div className="flex gap-3">
                    <button
                        onClick={() => navigate('/download')}
                        className="px-5 py-2.5 rounded-lg bg-slate-800 text-slate-300 hover:bg-slate-700 transition-colors text-sm font-medium border border-slate-700"
                    >
                        Back to Download
                    </button>
                    {hasStalled && (
                        <button
                            onClick={handleResetStuck}
                            disabled={isResetting}
                            className="px-5 py-2.5 rounded-lg bg-amber-900/40 hover:bg-amber-900/60 text-amber-300 border border-amber-700/50 text-sm font-bold flex items-center gap-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            {isResetting ? 'Resetting...' : '⟳ Reset Stuck Tasks'}
                        </button>
                    )}
                    {queueStatus.worker_active && !queueStatus.gpt_active && !queueStatus.all_complete && (
                        <button
                            onClick={handleStopWorker}
                            disabled={isStopping}
                            className="px-5 py-2.5 rounded-lg bg-red-900/40 hover:bg-red-900/60 text-red-300 border border-red-700/50 text-sm font-bold flex items-center gap-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            {isStopping ? 'Stopping...' : '■ Stop Worker'}
                        </button>
                    )}
                    {!queueStatus.worker_active && queueStatus.pending > 0 && !queueStatus.all_complete && (
                        <button
                            onClick={handleStartProcessing}
                            disabled={isStarting}
                            className="px-5 py-2.5 rounded-lg bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white text-sm font-bold flex items-center gap-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-blue-500/20"
                        >
                            <PlayIcon />
                            {isStarting ? 'Starting...' : 'Start Processing'}
                        </button>
                    )}
                    {queueStatus.all_complete && (
                        <button
                            onClick={() => navigate('/hotspots')}
                            className="px-5 py-2.5 rounded-lg bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-sm font-bold flex items-center gap-2 transition-all shadow-lg shadow-emerald-500/20"
                        >
                            Continue to Results
                            <ArrowRightIcon />
                        </button>
                    )}
                </div>
            </div>

            {/* Overall Progress Bar */}
            {hasStarted && (
                <div className="mb-6">
                    <div className="flex justify-between items-center mb-2">
                        <span className="text-xs text-slate-400 uppercase tracking-widest font-bold">
                            Overall Progress
                        </span>
                        <span className="text-sm font-mono text-blue-400">
                            {queueStatus.complete} / {queueStatus.total} pairs complete
                        </span>
                    </div>
                    <div className="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
                        <div
                            className="h-full bg-gradient-to-r from-blue-500 to-indigo-500 rounded-full transition-all duration-1000 ease-out shadow-[0_0_10px_rgba(99,102,241,0.5)]"
                            style={{ width: `${overallProgress}%` }}
                        />
                    </div>
                </div>
            )}

            {/* Instruction Banner */}
            <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-5 mb-8">
                <div className="flex items-start gap-3">
                    <div className="mt-0.5 text-blue-400">
                        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
                    </div>
                    <div>
                        <p className="text-sm text-slate-300 leading-relaxed">
                            {queueStatus.all_complete ? (
                                <><span className="text-emerald-400 font-bold">All pairs processed successfully!</span> Click "Continue to Results" to proceed to Hotspot Selection and view your displacement analysis.</>
                            ) : hasStarted ? (
                                <>Please wait while MineGuard processes your interferometric pairs using the SNAP GPT engine. Each pair takes approximately <b>30–60 minutes</b> depending on your hardware. You may leave this page open — processing continues in the background.</>
                            ) : (
                                <>Your interferometric pairs are queued and ready. Click <b>"Start Processing"</b> to begin the SNAP GPT interferometry engine. Each pair block below shows the Master → Slave scene pairing that will be processed.</>
                            )}
                        </p>
                    </div>
                </div>
            </div>

            {/* Error Banner */}
            {error && (
                <div className="bg-red-900/30 border border-red-500/40 rounded-xl p-4 mb-6 flex items-center gap-3">
                    <AlertIcon />
                    <span className="text-sm text-red-300">{error}</span>
                </div>
            )}

            {/* Loading State — before first API response */}
            {!hasLoaded && (
                <div className="flex flex-col items-center justify-center py-20 text-center">
                    <div className="w-8 h-8 rounded-full border-2 border-slate-700 border-t-blue-500 animate-spin mb-4" />
                    <p className="text-sm text-slate-500">Loading processing queue...</p>
                </div>
            )}

            {/* Empty State — shown only after a successful API response returns 0 tasks */}
            {hasLoaded && queueStatus.total === 0 && (
                <div className="flex flex-col items-center justify-center py-20 text-center">
                    <div className="text-slate-600 mb-4">
                        <GearIcon />
                    </div>
                    <h3 className="text-xl font-bold text-slate-400 mb-2">No Pairs in Queue</h3>
                    <p className="text-sm text-slate-500 max-w-md">
                        Go back to the Data Acquisition page and link your local directory or download scenes first. The processing queue will be populated automatically.
                    </p>
                    <button
                        onClick={() => window.history.back()}
                        className="mt-6 px-5 py-2.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 text-sm font-medium transition-colors"
                    >
                        ← Back to Data Acquisition
                    </button>
                </div>
            )}

            {/* Pair Block Grid — grouped by orbit */}
            {queueStatus.total > 0 && (() => {
                const allTasks = queueStatus.tasks;
                const isAsc = (orbit?: string) => { const u = orbit?.toUpperCase() ?? ''; return u === 'ASC' || u === 'ASCENDING'; };
                const isDsc = (orbit?: string) => { const u = orbit?.toUpperCase() ?? ''; return u === 'DSC' || u === 'DESCENDING'; };
                const ascTasks   = allTasks.filter(t => isAsc(t.orbit));
                const dscTasks   = allTasks.filter(t => isDsc(t.orbit));
                const otherTasks = allTasks.filter(t => !isAsc(t.orbit) && !isDsc(t.orbit));

                const openLog = (taskId: string) => {
                    window.open(`http://localhost:8000/api/processing/logs/${taskId.substring(0, 8)}`, '_blank');
                };

                const TaskCard = ({ task, idx }: { task: ProcessingTask; idx: number }) => {
                    const masterYear = extractYear(task.master_date || task.master_scene);
                    const slaveYear  = extractYear(task.slave_date  || task.slave_scene);
                    const isActive   = task.status === 'processing';
                    const isComplete = task.status === 'complete';
                    const isFailed   = task.status === 'failed';

                    // GPT stalled = task is "processing" in queue but java process is gone
                    const isStalled  = isActive && task.gpt_stalled === true;

                    const orbitTag = isAsc(task.orbit) ? 'ASC' : isDsc(task.orbit) ? 'DSC' : null;
                    const orbitBadgeClass = orbitTag === 'ASC'
                        ? 'bg-blue-900/60 text-blue-300 border-blue-700/50'
                        : orbitTag === 'DSC'
                        ? 'bg-amber-900/60 text-amber-300 border-amber-700/50'
                        : 'bg-slate-800 text-slate-500 border-slate-600';

                    const borderClass = isStalled
                        ? 'border-amber-600/60'
                        : getStatusBorderColor(task.status);

                    return (
                        <div
                            key={task.task_id}
                            className={`relative rounded-xl border overflow-hidden transition-all duration-500 ${borderClass} ${isActive && !isStalled ? 'ring-1 ring-blue-500/30 shadow-lg shadow-blue-500/10' : ''} ${isStalled ? 'ring-1 ring-amber-500/30' : ''}`}
                        >
                            <div
                                className={`absolute inset-0 bg-gradient-to-r ${isStalled ? 'from-amber-900/20 to-slate-900/10' : getStatusBgGradient(task.status)} transition-all duration-1000 ease-out`}
                                style={{ width: `${task.estimated_progress}%`, opacity: isActive ? 1 : (isComplete ? 0.6 : 0.3) }}
                            />
                            <div className="relative z-10 p-5">
                                <div className="flex justify-between items-center mb-3">
                                    <div className="flex items-center gap-2">
                                        <span className="text-xs text-slate-500 uppercase tracking-widest font-bold">
                                            Pair {idx + 1}
                                        </span>
                                        <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${orbitBadgeClass}`}>
                                            {orbitTag ?? '---'}
                                        </span>
                                    </div>
                                    <div className={`flex items-center gap-1.5 ${isStalled ? 'text-amber-400' : getStatusColor(task.status)}`}>
                                        {isComplete && <CheckIcon />}
                                        {isActive && !isStalled && <div className="w-2.5 h-2.5 rounded-full bg-blue-400 animate-pulse" />}
                                        {isStalled && <div className="w-2.5 h-2.5 rounded-full bg-amber-400 animate-pulse" />}
                                        {isFailed && <AlertIcon />}
                                        <span className="text-xs font-bold uppercase tracking-wider">
                                            {isStalled ? 'GPT STOPPED' : task.status}
                                        </span>
                                    </div>
                                </div>

                                <div className="flex items-center gap-3 mb-4">
                                    <span className="text-2xl font-bold text-slate-200">{masterYear}</span>
                                    <span className="text-slate-600 text-lg">→</span>
                                    <span className="text-2xl font-bold text-slate-200">{slaveYear}</span>
                                </div>

                                {isActive && !isStalled && (
                                    <div className="mb-3">
                                        <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                                            <div
                                                className="h-full bg-gradient-to-r from-blue-500 to-indigo-400 rounded-full transition-all duration-1000 ease-out shadow-[0_0_8px_rgba(99,102,241,0.5)]"
                                                style={{ width: `${task.estimated_progress}%` }}
                                            />
                                        </div>
                                        <div className="flex justify-between mt-1.5">
                                            <span className="text-xs text-slate-500 font-mono">~{task.estimated_progress?.toFixed(0)}% (time estimate)</span>
                                            <span className="text-xs text-slate-500 font-mono">{task.elapsed_seconds ? formatElapsed(task.elapsed_seconds) : '--'}</span>
                                        </div>
                                    </div>
                                )}
                                {isStalled && (
                                    <div className="mb-2 p-2 bg-amber-950/40 border border-amber-800/40 rounded-lg">
                                        <p className="text-[11px] text-amber-400 leading-relaxed">
                                            SNAP GPT process is no longer running. The worker will mark this task failed and move to the next pair automatically. Check the log for details.
                                        </p>
                                    </div>
                                )}
                                {isFailed && task.error_message && (
                                    <p className="text-xs text-red-400/80 mt-1 line-clamp-2">{task.error_message}</p>
                                )}
                                {isComplete && (
                                    <p className="text-xs text-emerald-400/80 mt-1">Interferogram generated successfully</p>
                                )}
                                {/* View Log button for active/stalled/failed tasks */}
                                {(isActive || isStalled || isFailed) && (
                                    <button
                                        onClick={() => openLog(task.task_id)}
                                        className="mt-2 text-[11px] text-slate-500 hover:text-slate-300 underline underline-offset-2 transition-colors"
                                    >
                                        View SNAP GPT log →
                                    </button>
                                )}
                            </div>
                        </div>
                    );
                };

                const OrbitGroup = ({
                    label, badge, badgeClass, tasks: groupTasks, startIdx
                }: { label: string; badge: string; badgeClass: string; tasks: ProcessingTask[]; startIdx: number }) => (
                    groupTasks.length === 0 ? null : (
                        <div className="mb-8">
                            <div className="flex items-center gap-3 mb-4">
                                <span className={`text-xs font-bold px-2.5 py-1 rounded-full border ${badgeClass}`}>{badge}</span>
                                <h3 className="text-sm font-bold text-slate-400 uppercase tracking-widest">{label}</h3>
                                <div className="flex-1 h-px bg-slate-800" />
                                <span className="text-xs text-slate-600 font-mono">{groupTasks.length} pairs</span>
                            </div>
                            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
                                {groupTasks.map((task, i) => <TaskCard key={task.task_id} task={task} idx={startIdx + i} />)}
                            </div>
                        </div>
                    )
                );

                return (
                    <div>
                        <OrbitGroup label="Ascending Pass" badge="ASC ↗" badgeClass="bg-blue-900/60 text-blue-300 border-blue-700/50" tasks={ascTasks} startIdx={0} />
                        <OrbitGroup label="Descending Pass" badge="DSC ↘" badgeClass="bg-amber-900/60 text-amber-300 border-amber-700/50" tasks={dscTasks} startIdx={ascTasks.length} />
                        <OrbitGroup label="Untagged Pairs" badge="---" badgeClass="bg-slate-800 text-slate-500 border-slate-700" tasks={otherTasks} startIdx={ascTasks.length + dscTasks.length} />
                    </div>
                );
            })()}

            {/* Worker Status Footer */}
            {hasStarted && (
                <div className="mt-8 flex items-center justify-center gap-3 text-sm text-slate-500">
                    {queueStatus.gpt_active ? (
                        <>
                            <div className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
                            <span>SNAP GPT is actively processing (java running, PID verified)</span>
                        </>
                    ) : queueStatus.all_complete ? (
                        <>
                            <div className="w-2 h-2 rounded-full bg-emerald-400" />
                            <span>All processing complete</span>
                        </>
                    ) : queueStatus.worker_active ? (
                        <>
                            <div className="w-2 h-2 rounded-full bg-slate-500 animate-pulse" />
                            <span>Worker script running — waiting for SNAP GPT to start...</span>
                        </>
                    ) : (
                        <>
                            <div className="w-2 h-2 rounded-full bg-amber-400" />
                            <span>Worker stopped — check SNAP GPT logs for details</span>
                        </>
                    )}
                </div>
            )}
        </div>
    );
};

export default Processing;
