from dotenv import load_dotenv
from pathlib import Path as _Path
load_dotenv(dotenv_path=_Path(__file__).parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from mineguard.backend.api import download_api
from mineguard.backend.api import processing_api
from mineguard.backend.api import hotspot_api
from mineguard.backend.api import summary_api
from mineguard.backend.services.scene_watcher import start_directory_watcher
from shared.config import PROJECT_ROOT

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    watcher_observer = start_directory_watcher()
    yield
    # Shutdown actions
    if watcher_observer:
        watcher_observer.stop()
        watcher_observer.join()

app = FastAPI(title="MineGuard API", lifespan=lifespan)

# Add CORS to allow React localhost:3000 to talk to FastAPI localhost:8000
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(download_api.router)
app.include_router(processing_api.router)
app.include_router(hotspot_api.router)
app.include_router(summary_api.router)

# Mount local results directory for static Dashboard rendering
results_dir = PROJECT_ROOT / "results"
results_dir.mkdir(parents=True, exist_ok=True)
app.mount("/results", StaticFiles(directory=str(results_dir)), name="results")

@app.get("/")
def read_root():
    return {"message": "Welcome to MineGuard API"}

@app.get("/health")
def health_check():
    return {"status": "ok"}
