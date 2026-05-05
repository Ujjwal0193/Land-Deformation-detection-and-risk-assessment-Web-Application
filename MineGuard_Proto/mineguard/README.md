# MineGuard Web Application

MineGuard is a geospatial deformation monitoring platform designed to analyze mining sites using InSAR processing.

## Project Structure

```text
mineguard/
├── frontend/   # React frontend (Vite)
├── backend/    # FastAPI server (Python)
├── pipeline/   # InSAR processing scripts (SNAP integration) 
├── datasets/   # Geospatial datasets (GeoJSON, etc.)
├── shared/     # Common configuration files
└── docs/       # Project documentation
```

## Setup Instructions

### 1. Prerequisites
- **Node.js** (for the React frontend)
- **Python 3.9+** (for the FastAPI backend and InSAR pipeline)

### 2. Frontend Development Server
Since `npm` and `npx` were not available during initialization, you will need to manually install dependencies or set up the React project.
Once Node.js is installed:
```bash
cd frontend
npm install
npm run dev
```

### 3. Backend Development Server
To start the FastAPI server:
```bash
cd backend
python -m venv venv
venv\Scripts\activate   # (Windows)
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```
