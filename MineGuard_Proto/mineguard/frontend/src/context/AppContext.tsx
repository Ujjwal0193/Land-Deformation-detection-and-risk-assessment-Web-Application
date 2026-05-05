import React, { createContext, useState, useContext, type ReactNode } from 'react';

// Interfaces for our global state
export interface GeocodeResult {
    place_id: number;
    display_name: string;
    lat: string;
    lon: string;
    type: string;
}

export interface BoundingBox {
    north: number;
    south: number;
    east: number;
    west: number;
}

export interface TimelineConfig {
    startYear: number;
    endYear: number;
    frequency: 'Monthly' | 'Quarterly' | 'Yearly';
    orbitMode: 'ASCENDING' | 'DESCENDING' | 'BOTH';
}

export interface QueryResults {
    totalFound: number;
    estimatedDownloadSize: string;
    filteredScenes: any[];
    generatedPairs: any[];
    missingCoverage?: {
        ascending: string[];
        descending: string[];
    };
}

interface AppState {
    selectedLocation: GeocodeResult | null;
    roiBoundingBox: BoundingBox | null;
    timelineConfig: TimelineConfig | null;
    queryResults: QueryResults | null;
}

interface AppContextType {
    state: AppState;
    setSelectedLocation: (location: GeocodeResult | null) => void;
    setRoiBoundingBox: (bbox: BoundingBox | null) => void;
    setTimelineConfig: (config: TimelineConfig | null) => void;
    setQueryResults: (results: QueryResults | null) => void;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

export const AppProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
    const [state, setState] = useState<AppState>({
        selectedLocation: null,
        roiBoundingBox: null,
        timelineConfig: null,
        queryResults: null,
    });

    const setSelectedLocation = (location: GeocodeResult | null) => {
        setState((prev) => ({ ...prev, selectedLocation: location }));
    };

    const setRoiBoundingBox = (bbox: BoundingBox | null) => {
        setState((prev) => ({ ...prev, roiBoundingBox: bbox }));
    };

    const setTimelineConfig = (config: TimelineConfig | null) => {
        setState((prev) => ({ ...prev, timelineConfig: config }));
    };

    const setQueryResults = (results: QueryResults | null) => {
        setState((prev) => ({ ...prev, queryResults: results }));
    };

    return (
        <AppContext.Provider value={{ state, setSelectedLocation, setRoiBoundingBox, setTimelineConfig, setQueryResults }}>
            {children}
        </AppContext.Provider>
    );
};

export const useAppContext = () => {
    const context = useContext(AppContext);
    if (context === undefined) {
        throw new Error('useAppContext must be used within an AppProvider');
    }
    return context;
};
