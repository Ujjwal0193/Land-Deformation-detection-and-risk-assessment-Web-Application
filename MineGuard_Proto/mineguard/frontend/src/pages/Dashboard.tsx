import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

// ── Types ────────────────────────────────────────────────────────────────────

interface HotspotFinding {
    label: string;
    risk_level: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
    cumulative_vertical_mm: number;
    cumulative_ew_mm: number;
    key_finding: string;
}

interface SummaryData {
    executive_summary: string;
    observation_period: string;
    hotspot_analysis: HotspotFinding[];
    critical_events: string;
    overall_verdict: string;
    recommended_actions: string[];
    cached?: boolean;
}

// ── Risk badge helper ────────────────────────────────────────────────────────

const RISK_STYLES: Record<string, string> = {
    LOW:      'bg-emerald-900/40 text-emerald-300 border border-emerald-700/50',
    MEDIUM:   'bg-amber-900/40   text-amber-300   border border-amber-700/50',
    HIGH:     'bg-orange-900/40  text-orange-300  border border-orange-700/50',
    CRITICAL: 'bg-red-900/50     text-red-300     border border-red-700/60',
};

function RiskBadge({ level }: { level: string }) {
    return (
        <span className={`text-xs font-bold uppercase px-2.5 py-1 rounded-full tracking-widest ${RISK_STYLES[level] ?? RISK_STYLES.MEDIUM}`}>
            {level}
        </span>
    );
}

// ── Section card ─────────────────────────────────────────────────────────────

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
    return (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl">
            <h2 className="text-sm font-bold uppercase tracking-widest text-teal-400 mb-4">{title}</h2>
            {children}
        </div>
    );
}

// ── Main page ────────────────────────────────────────────────────────────────

export default function Dashboard() {
    const navigate = useNavigate();
    const [data, setData]       = useState<SummaryData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError]     = useState('');
    const [regenerating, setRegenerating] = useState(false);

    const fetchSummary = async () => {
        setLoading(true);
        setError('');
        try {
            const res = await fetch('http://localhost:8000/api/summary/generate');
            if (!res.ok) {
                const detail = await res.json().catch(() => ({ detail: res.statusText }));
                throw new Error(detail.detail || res.statusText);
            }
            setData(await res.json());
        } catch (e: any) {
            setError(e.message ?? 'Failed to generate summary.');
        } finally {
            setLoading(false);
        }
    };

    const handleRegenerate = async () => {
        setRegenerating(true);
        try {
            await fetch('http://localhost:8000/api/summary/cache', { method: 'DELETE' });
        } catch {/* ignore */}
        setRegenerating(false);
        await fetchSummary();
    };

    useEffect(() => { fetchSummary(); }, []);

    return (
        <div className="h-[calc(100vh-32px)] overflow-y-auto bg-slate-950 text-white font-sans flex flex-col">

            {/* ── Header ────────────────────────────────────────────────── */}
            <div className="border-b border-slate-800 px-8 py-6 bg-slate-950/80 backdrop-blur-sm sticky top-0 z-10">
                <h1 className="text-3xl font-bold text-center bg-gradient-to-r from-teal-400 to-blue-500 bg-clip-text text-transparent tracking-tight">
                    Summary / Conclusion
                </h1>
                <p className="text-center text-slate-500 text-sm mt-1">
                    AI-generated geotechnical report based on Sentinel-1 InSAR analysis
                </p>
            </div>

            {/* ── Body ──────────────────────────────────────────────────── */}
            <div className="flex-1 overflow-y-auto px-6 md:px-12 py-8 max-w-5xl mx-auto w-full pb-40">

                {/* Loading */}
                {loading && (
                    <div className="flex flex-col items-center justify-center py-32">
                        <div className="w-14 h-14 border-4 border-slate-700 border-t-teal-500 rounded-full animate-spin mb-6" />
                        <p className="text-slate-400 text-base">Analysing displacement plots with AI...</p>
                        <p className="text-slate-600 text-xs mt-2">This may take 10–20 seconds on first run.</p>
                    </div>
                )}

                {/* Error */}
                {!loading && error && (
                    <div className="bg-red-900/20 border border-red-800/50 rounded-2xl p-8 text-center">
                        <p className="text-red-400 font-semibold text-base mb-2">Summary generation failed</p>
                        <p className="text-red-300/70 text-sm mb-6 max-w-lg mx-auto">{error}</p>
                        <button
                            onClick={fetchSummary}
                            className="px-5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-sm font-semibold border border-slate-700 transition"
                        >
                            Retry
                        </button>
                    </div>
                )}

                {/* Content */}
                {!loading && data && (
                    <div className="flex flex-col gap-6">

                        {/* Cache indicator + regenerate */}
                        {data.cached && (
                            <div className="flex items-center justify-between bg-slate-900/60 border border-slate-800 rounded-xl px-5 py-3">
                                <span className="text-slate-500 text-xs">
                                    Showing cached summary from previous analysis.
                                </span>
                                <button
                                    onClick={handleRegenerate}
                                    disabled={regenerating}
                                    className="text-xs text-teal-400 hover:text-teal-300 font-semibold disabled:opacity-50 transition"
                                >
                                    {regenerating ? 'Regenerating...' : '↺ Regenerate'}
                                </button>
                            </div>
                        )}

                        {/* Executive Summary */}
                        <SectionCard title="Executive Summary">
                            <p className="text-slate-200 text-base leading-relaxed">{data.executive_summary}</p>
                            {data.observation_period && (
                                <p className="text-slate-500 text-sm mt-3 italic">{data.observation_period}</p>
                            )}
                        </SectionCard>

                        {/* Hotspot Analysis table */}
                        {data.hotspot_analysis?.length > 0 && (
                            <SectionCard title="Hotspot-by-Hotspot Analysis">
                                <div className="overflow-x-auto">
                                    <table className="w-full text-sm">
                                        <thead>
                                            <tr className="border-b border-slate-800 text-slate-500 text-xs uppercase tracking-widest">
                                                <th className="text-left pb-3 pr-4 font-semibold">Hotspot</th>
                                                <th className="text-left pb-3 pr-4 font-semibold">Risk</th>
                                                <th className="text-right pb-3 pr-4 font-semibold">Vertical (mm)</th>
                                                <th className="text-right pb-3 pr-4 font-semibold">E–W (mm)</th>
                                                <th className="text-left pb-3 font-semibold">Finding</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {data.hotspot_analysis.map((h, i) => (
                                                <tr key={i} className="border-b border-slate-800/50 last:border-0">
                                                    <td className="py-3 pr-4 font-bold text-slate-200">{h.label}</td>
                                                    <td className="py-3 pr-4"><RiskBadge level={h.risk_level} /></td>
                                                    <td className={`py-3 pr-4 text-right font-mono font-semibold ${h.cumulative_vertical_mm < -200 ? 'text-red-400' : h.cumulative_vertical_mm < -100 ? 'text-amber-400' : 'text-emerald-400'}`}>
                                                        {h.cumulative_vertical_mm > 0 ? '+' : ''}{h.cumulative_vertical_mm}
                                                    </td>
                                                    <td className={`py-3 pr-4 text-right font-mono font-semibold ${Math.abs(h.cumulative_ew_mm) > 200 ? 'text-amber-400' : 'text-slate-300'}`}>
                                                        {h.cumulative_ew_mm > 0 ? '+' : ''}{h.cumulative_ew_mm}
                                                    </td>
                                                    <td className="py-3 text-slate-400 text-sm leading-snug">{h.key_finding}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            </SectionCard>
                        )}

                        {/* Critical Events */}
                        {data.critical_events && (
                            <SectionCard title="Critical Events / Anomalies">
                                <p className="text-slate-300 text-sm leading-relaxed">{data.critical_events}</p>
                            </SectionCard>
                        )}

                        {/* Overall Verdict */}
                        <SectionCard title="Overall Site Verdict">
                            <p className="text-slate-200 text-base leading-relaxed">{data.overall_verdict}</p>
                        </SectionCard>

                        {/* Recommended Actions */}
                        {data.recommended_actions?.length > 0 && (
                            <SectionCard title="Recommended Actions">
                                <ul className="flex flex-col gap-2">
                                    {data.recommended_actions.map((action, i) => (
                                        <li key={i} className="flex gap-3 text-sm text-slate-300 leading-relaxed">
                                            <span className="shrink-0 w-6 h-6 rounded-full bg-teal-900/50 border border-teal-700/50 text-teal-400 flex items-center justify-center text-xs font-bold">
                                                {i + 1}
                                            </span>
                                            {action}
                                        </li>
                                    ))}
                                </ul>
                            </SectionCard>
                        )}

                    </div>
                )}
            </div>

            {/* ── Bottom bar ────────────────────────────────────────────── */}
            <div className="fixed bottom-0 left-0 right-0 border-t border-slate-800 bg-slate-950/95 backdrop-blur-sm px-8 py-4 flex items-center justify-between">
                <button
                    onClick={() => navigate('/hotspots')}
                    className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-sm font-semibold border border-slate-700 transition-all"
                >
                    <span>←</span> Back to Hotspot Selection
                </button>

                {!loading && data && !data.cached && (
                    <button
                        onClick={handleRegenerate}
                        disabled={regenerating}
                        className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 text-sm font-semibold border border-slate-700 transition-all disabled:opacity-40"
                    >
                        {regenerating ? 'Regenerating...' : '↺ Regenerate Summary'}
                    </button>
                )}
            </div>

        </div>
    );
}
