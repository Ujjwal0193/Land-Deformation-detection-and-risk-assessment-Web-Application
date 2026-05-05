import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import MapViewer from "../components/MapViewer";
import { useAppContext } from "../context/AppContext";

// Interface for Geocoding Data
interface GeocodeResult {
    place_id: number;
    display_name: string;
    lat: string;
    lon: string;
    type: string;
}

const SearchMine: React.FC = () => {
    const { state, setSelectedLocation } = useAppContext();

    // Default search query to existing global state if it exists
    const [searchQuery, setSearchQuery] = useState(state.selectedLocation ? state.selectedLocation.display_name.split(',')[0] : "");
    const [searchResults, setSearchResults] = useState<GeocodeResult[]>([]);
    const [showDropdown, setShowDropdown] = useState(false);

    // If we have a global location, center the map there initially
    const initialLat = state.selectedLocation ? parseFloat(state.selectedLocation.lat) : 0;
    const initialLon = state.selectedLocation ? parseFloat(state.selectedLocation.lon) : 0;

    const [mapCenter, setMapCenter] = useState<[number, number] | null>(state.selectedLocation ? [initialLat, initialLon] : null);
    const [mapZoom, setMapZoom] = useState<number>(state.selectedLocation ? 12 : 2); // Default zoom level
    const [isSearching, setIsSearching] = useState(false);

    const navigate = useNavigate();

    // Debounced Fetch from Nominatim API
    useEffect(() => {
        if (searchQuery.trim() === "") {
            setSearchResults([]);
            setShowDropdown(false);
            // Reset map to default world view when clear
            setMapCenter([0, 0]);
            setMapZoom(2);
            setSelectedLocation(null);
            return;
        }

        const delayDebounceFn = setTimeout(async () => {
            setIsSearching(true);
            try {
                const response = await fetch(
                    `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(searchQuery)}&limit=8&addressdetails=1&accept-language=en`
                );
                const data: GeocodeResult[] = await response.json();
                setSearchResults(data);
                setShowDropdown(true);
            } catch (error) {
                console.error("Error fetching locations: ", error);
                setSearchResults([]);
            } finally {
                setIsSearching(false);
            }
        }, 500); // 500ms debounce

        return () => clearTimeout(delayDebounceFn);
    }, [searchQuery]);

    const handleSelectLocation = (result: GeocodeResult) => {
        // Extract the main name (before the first comma) for the search bar
        const shortName = result.display_name.split(',')[0];
        setSearchQuery(shortName);
        setSelectedLocation(result); // Save to Global AppContext

        const lat = parseFloat(result.lat);
        const lon = parseFloat(result.lon);

        setMapCenter([lat, lon]);
        setMapZoom(12);
        setShowDropdown(false);
    };

    const handleHoverLocation = (result: GeocodeResult) => {
        const lat = parseFloat(result.lat);
        const lon = parseFloat(result.lon);

        setMapCenter([lat, lon]);
        setMapZoom(12);
    };

    const handleSearchSubmit = () => {
        if (state.selectedLocation || searchQuery) {
            console.log("Proceeding to crop area with: ", state.selectedLocation?.display_name || searchQuery);
            navigate("/crop"); // State is now handled globally, no need to pass via router
        }
    };

    return (
        <div className="relative w-screen h-screen overflow-hidden bg-slate-900">
            <div className="absolute top-[15%] left-1/2 -translate-x-1/2 z-[1000] flex flex-col items-center gap-8 w-full px-4 pointer-events-none">
                <header className="bg-slate-900/80 backdrop-blur-md px-16 py-8 rounded-2xl shadow-[0_8px_32px_rgba(0,0,0,0.5)] border border-slate-700 pointer-events-auto text-center">
                    <h1 className="text-5xl font-extrabold text-white tracking-wide m-0">AI-Based</h1>
                    <h2 className="text-xl font-medium text-slate-400 mt-2 m-0">Deformation Monitoring System</h2>
                </header>

                <div className="relative w-full max-w-[650px] flex flex-col items-center">

                    {/* Instruction Panel */}
                    <div className="bg-slate-800/60 backdrop-blur-sm px-6 py-3 rounded-xl mb-4 text-center border border-slate-700/50 shadow-sm w-full max-w-[500px]">
                        <p className="text-lg text-slate-300 font-large">
                            Enter the location of your mining site and select the correct area from the search results.
                        </p>
                    </div>

                    <div className="flex w-full bg-slate-800/90 backdrop-blur-sm rounded-full shadow-[0_0_20px_rgba(0,0,0,0.4)] overflow-hidden pointer-events-auto border border-slate-700">
                        <input
                            type="text"
                            placeholder="Enter mine location..."
                            className="flex-1 border-none px-8 py-5 text-lg outline-none text-slate-100 bg-transparent placeholder-slate-500"
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            onFocus={() => { if (searchQuery) setShowDropdown(true) }}
                            onBlur={() => setTimeout(() => setShowDropdown(false), 200)}
                        />
                    </div>

                    <div className="relative w-full z-[3000]">
                        {showDropdown && searchResults.length > 0 && (
                            <div className="absolute top-2 left-0 w-full bg-slate-800 rounded-xl shadow-[0_10px_40px_rgba(0,0,0,0.5)] overflow-hidden pointer-events-auto max-h-[350px] overflow-y-auto border border-slate-700">
                                {searchResults.map((result) => (
                                    <div
                                        key={result.place_id}
                                        className="px-8 py-5 cursor-pointer border-b border-slate-700/50 last:border-0 hover:bg-slate-700 transition-colors duration-200"
                                        onMouseDown={(e) => {
                                            // Use onMouseDown instead of onClick to fire before the input's onBlur hides the dropdown
                                            e.preventDefault();
                                            handleSelectLocation(result);
                                        }}
                                        // Trigger preview on hover
                                        onMouseEnter={() => handleHoverLocation(result)}
                                    >
                                        <div className="flex justify-between items-start text-lg text-slate-100 mb-2 gap-4">
                                            <strong className="font-semibold flex-1 leading-tight">{result.display_name}</strong>
                                            <span className="text-xs bg-slate-900/50 text-slate-300 px-3 py-1 rounded-full border border-slate-600 whitespace-nowrap hidden sm:inline-block capitalize">{result.type}</span>
                                        </div>
                                        <div className="text-sm text-slate-400 font-mono">
                                            Lat: {parseFloat(result.lat).toFixed(4)} • Lon: {parseFloat(result.lon).toFixed(4)}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                        {showDropdown && searchResults.length === 0 && searchQuery.trim() !== "" && !isSearching && (
                            <div className="absolute top-2 left-0 w-full bg-slate-800 rounded-xl shadow-[0_10px_40px_rgba(0,0,0,0.5)] overflow-hidden pointer-events-auto border border-slate-700">
                                <div className="px-8 py-5 text-slate-400 text-center cursor-default">No locations found.</div>
                            </div>
                        )}
                        {showDropdown && isSearching && (
                            <div className="absolute top-2 left-0 w-full bg-slate-800 rounded-xl shadow-[0_10px_40px_rgba(0,0,0,0.5)] overflow-hidden pointer-events-auto border border-slate-700">
                                <div className="px-8 py-5 text-slate-400 text-center cursor-default flex items-center justify-center gap-3">
                                    <svg className="animate-spin h-5 w-5 text-slate-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                    </svg>
                                    Searching...
                                </div>
                            </div>
                        )}
                    </div>

                    <button
                        className="mt-6 bg-blue-600 hover:bg-blue-500 text-white font-semibold py-4 px-12 rounded-full shadow-lg transition-colors duration-200 text-lg pointer-events-auto relative z-[1001]"
                        onClick={handleSearchSubmit}
                        disabled={!state.selectedLocation && !searchQuery}
                    >
                        Submit
                    </button>
                </div>
            </div>

            <MapViewer mapCenter={mapCenter} mapZoom={mapZoom} />
        </div>
    );
};

export default SearchMine;
