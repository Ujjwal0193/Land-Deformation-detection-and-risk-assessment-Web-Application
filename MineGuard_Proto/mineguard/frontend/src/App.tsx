import { BrowserRouter as Router, Routes, Route, Navigate, Link } from 'react-router-dom';

// Import pages
import SearchMine from './pages/SearchMine';
import CropArea from './pages/CropArea';
import TimelineSelection from './pages/TimelineSelection';
import DataDownload from './pages/DataDownload';
import Processing from './pages/Processing';
import HotspotSelection from './pages/HotspotSelection';
import ResultSelection from './pages/ResultSelection';
import Dashboard from './pages/Dashboard';

import { AppProvider } from './context/AppContext';

function App() {
  return (
    <AppProvider>
      <Router>
        <div className="app-container">
          <nav className="main-nav">
            <strong>MineGuard Navigation:</strong> &nbsp;
            <Link to="/search">Search</Link> | &nbsp;
            <Link to="/crop">Crop</Link> | &nbsp;
            <Link to="/timeline">Timeline</Link> | &nbsp;
            <Link to="/download">Download</Link> | &nbsp;
            <Link to="/process">Process</Link> | &nbsp;
            <Link to="/hotspots">Hotspots</Link> | &nbsp;
            <Link to="/results">Results</Link> | &nbsp;
            <Link to="/dashboard">Dashboard</Link>
          </nav>

          <main className="main-content">
            <Routes>
              <Route path="/" element={<Navigate to="/search" replace />} />
              <Route path="/search" element={<SearchMine />} />
              <Route path="/crop" element={<CropArea />} />
              <Route path="/timeline" element={<TimelineSelection />} />
              <Route path="/download" element={<DataDownload />} />
              <Route path="/process" element={<Processing />} />
              <Route path="/hotspots" element={<HotspotSelection />} />
              <Route path="/results" element={<ResultSelection />} />
              <Route path="/dashboard" element={<Dashboard />} />
            </Routes>
          </main>
        </div>
      </Router>
    </AppProvider>
  );
}

export default App;
