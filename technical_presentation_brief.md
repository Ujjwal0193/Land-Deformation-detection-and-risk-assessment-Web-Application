# MineGuard Prototype - Technical Documentation & Pipeline Overview

This document explains the internal workings of the "MineGuard" satellite monitoring system. Use this as a reference for your presentation.

## 1. High-Level Architecture
The system is an **Automated Interferometric Synthetic Aperture Radar (InSAR) Pipeline**.
It monitors ground deformation (subsidence/uplift) in open-pit mines using **Sentinel-1** satellite data.

**Key Components:**
1.  **Data Acquisition (`main_script.py`)**: Smart downloader using Copernicus Data Space Ecosystem (CDSE) OData API.
2.  **Core Processing (SNAP `gpt`)**: Headless execution of ESA's InSAR processing graph (`process_graph.xml`).
3.  **Analysis & Visualization (`plot_displacement.py`)**: Detecting features (the mine pit) and calculating displacement trends.

---

## 1.5 Study Area
*   **Name**: Chuquicamata Mine
*   **Location**: Calama, Antofagasta Region, Chile
*   **Coordinates**: 22.29° S, 68.90° W (Decimal: -22.29, -68.90)
*   **Type**: Open-pit Copper Mine
*   **Significance**: One of the largest open-pit copper mines in the world by excavated volume.

## 2. Component Details

### A. Data Acquisition (`main_script.py`)
This Python script handles data ingestion.
*   **API**: Uses **OData** (Open Data Protocol) to query the Copernicus `Catalogue` service.
*   **Authentication**: Implements OAuth2 flow with Keycloak to get temporary access tokens (refreshes automatically).
*   **Smart Selection Logic**:
    *   **Filter**: Looking for `SLC` (Single Look Complex) products. These contain both **Intensity** (brightness) and **Phase** (distance), crucial for measuring deformation.
    *   **Relative Orbit (Track)**: InSAR requires images taken from the *exact same point in space*. The script first finds a 2023 image, notes its `RelativeOrbitNumber`, and forces all subsequent years (2024, 2025) to match that orbit. This ensures geometric consistency.
*   **Streaming**: Downloads large ~4GB files in chunks, verifying file integrity (size checks) to avoid partial downloads.

### B. InSAR Processing Engine (SNAP Graph)
We use the **Graph Processing Tool (`gpt`)** from ESA SNAP to run a predefined XML workflow (`graphs/process_graph.xml`) without opening the GUI.

**The Processing Chain:**
1.  **Read (Master & Slave)**: Inputs two SLC images (e.g., 2023 vs 2024).
2.  **TOPSAR-Split**:
    *   **Internal Logic**: Sentinel-1 data is huge ("Swaths"). We split it to only process sub-swath **IW2** (where the mine is located) and polarization **VV** (Vertical-Vertical). This reduces processing time by ~70%.
3.  **Apply-Orbit-File**:
    *   **Internal Logic**: Downloads "Precise Orbit Ephemerides" (GPS data for the satellite) to correct the satellite's position accuracy from meters down to roughly **5 centimeters**.
4.  **Back-Geocoding**:
    *   **Internal Logic**: The registration step. It uses a **Digital Elevation Model (SRTM 3sec)** to simulate the terrain and align the two images pixel-by-pixel.
5.  **Interferogram Generation**:
    *   **Internal Logic**: Computes the phase difference ($\Delta\phi$) between the two images.
    *   $\Delta\phi_{int} = \phi_{slave} - \phi_{master}$
    *   This phase difference contains contributions from: **Topography + Atmosphere + Deformation + Noise**.
    *   We subtract the *Topographic Phase* (using the DEM) so the remaining phase represents mostly **Deformation** (movement).
6.  **TOPSAR-Deburst**:
    *   **Internal Logic**: Sentinel-1 scans in "bursts" (stripes). This operator stitches them into a continuous, seamless image.
7.  **Write**: Outputs a `.dim` file containing the **Phase** and **Coherence** bands.

### C. Analysis & "feature detection" (`plot_displacement.py`)
This script turns raw data into actionable insight.

**Algorithm: Auto-Pit Detection**
1.  **Read Coherence**: Opens the `coh` (Coherence) band from the processed file.
    *   **Coherence ($|\gamma|$)**: A measure of similarity between images (0 to 1).
    *   **Stable Ground** (Rock, Desert) has **High Coherence (~0.8 - 1.0)**.
    *   **Changing Ground** (Active Mining, Trucks, Vegetation) has **Low Coherence (~0.0 - 0.3)**.
2.  **Filtering**:
    *   Masks invalid data (0.0 edges).
    *   Applies a **Uniform Filter** (smoothing) to reduce speckle noise.
3.  **Minimization**: Finds the coordinates $(x, y)$ with the **lowest smoothed coherence value**. This reliably identifies the center of the active mine pit.

**Algorithm: Displacement Calculation**
1.  **Extract Phase**: Reads the interferometric phase ($\phi$) at the detected $(x, y)$ coordinates.
2.  **Convert to Meters**: Uses the radar wavelength formula:
    $$d = \frac{\phi \cdot \lambda}{-4\pi}$$
    *   Where $\lambda$ (Sentinel-1 Wavelength) $\approx 5.6$ cm.
    *   *Note*: The result is "wrapped" (modulo $\lambda/2 \approx 2.8$ cm). For large movements, this shows the residual trend within the ambiguity cycle. Ideally, a "Phase Unwrapping" step (SNAPHU) would be added for absolute values, but for a prototype, this metric effectively tracks activity intensity.
3.  **Cumulative Plotting**:
    *   Sums the displacements over time (2023 $\to$ 2024 $\to$ 2025).
    *   Plots "Altitude Change" vs. Year to visualize the subsidence trend.

---

## 3. Summary of Innovation
*   **"Zero-Touch"**: The user runs one command; the system finds the data, processes it, finds the mine, and plots the graph. No manual interaction required.
*   **Resilience**: Handles API failures and broken downloads automatically.
*   **Scalability**: Built on OData and SNAP Graph (batch processing capable).

---

## 4. Live Demo Troubleshooting

### A. Error: "Referenced rasters are not of the same size"
*   **Reason**: You tried to open the whole `.zip` as an RGB image. Sentinel-1 has separate strips (IW1, IW2, IW3) so this fails.
*   **Fix**: Do not double-click the filename. Expand the product tree instead.

### B. "I only see noise / gray static!" (Your current view)
*   **Reason**: You are viewing raw Radar Intensity (`Intensity_IW2_VV`).
    *   **Black Stripes**: These are gaps between "bursts" of data (Sentinel-1 scans in strips). This is normal.
    *   **Static**: This is "Speckle noise" common in radar.
*   **Fix (The Correct Way to View)**:
    1.  Ensure you have opened **`Intensity_IW2_VV`**.
    2.  **Right-click** on the image.
    3.  Select **"Linear to/from dB"**.
    4.  *Magic*: The image will turn from gray static into a high-contrast map. The mine should appear bright/distinct against the dark background.

---

## 5. Technical Deep Dive (For Professor's Questions)

### Q: "Is this Altitude, or just Displacement?"
**Scientific Answer**: It is **Line-of-Sight (LOS) Displacement**.
*   **Correction**: In our plot, we labeling it as "LOS Displacement" (previously "Altitude") to be scientifically precise.
*   **The Physics**: The satellite looks sideways. It measures Slant Range Change.
*   **Interpretation**: Because it is a mine pit, we *interpret* negative LOS movement as **Vertical Subsidence**.
    *   **Scientific Caveat**: Without a second satellite angle (Ascending/Descending pair), we cannot mathematically separate vertical from horizontal motion. However, "Subsidence" is the dominant vector in a pit collapse.

### Q: "How exactly is it calculated?"
**The Formula**:
$$d_{LOS} = \frac{\Delta\phi_{unwrapped} \cdot \lambda}{-4\pi}$$

*   $d_{LOS}$: Displacement in meters (Line of Sight).
*   $\Delta\phi$: The Interferometric Phase Change (in Radians).
*   $\lambda$: Wavelength of Sentinel-1 C-Band Radar ($\approx 0.05546576$ meters).
*   $-4\pi$: Factor accounting for the two-way travel path (Ping $\to$ Ground $\to$ Ping) and phase cycle.

**Our Prototype's Approximation**:
Since we calculate `Phase` directly without unwrapping (SNAPHU), we are measuring the **change within the ambiguity cycle** ($\pm 2.8$ cm).
*   **If the mine sinks 5cm**: The phase wraps around, and we might see a residual.
*   **However**: By summing the differences over time (2023 $\to$ 2024 $\to$ 2025), we reconstruct the cumulative trend. The "red" areas in our plot prove the ground is moving away from the satellite $\rightarrow$ **Subsidence**.

It is **NOT** the speed (velocity), it is the **position change**.

### Q: "Why is 'Phase Unwrapping' (SNAPHU) skipped?"
**The "Wrapped Phase" Limitations**:
InSAR data is cyclic (like a clock).
*   **0 to 2.8cm movement**: The phase goes from $0 \to \pi$.
*   **2.8cm to 5.6cm movement**: The phase goes from $\pi \to 2\pi$ (which looks like $0$ again!).
*   **Problem**: If the ground moves **10cm**, the raw data only shows the "remainder" (e.g., $10 \text{ mod } 2.8 = 1.6 \text{ cm}$).

**Why we skipped Unwrapping:**
1.  **Complexity**: Typically requires an external C-library (SNAPHU) and hours of processing on Linux.
2.  **Our Prototype Strategy**:
    *   We use the **Wrapped Phase** as a **"Proxy for Activity"**.
    *   **Stable Ground** (0 movement) $\rightarrow$ Phase is consistently close to 0.
    *   **Active Ground** (Moving) $\rightarrow$ Phase is non-zero and chaotic.
    *   Therefore, observing *any* consistent displacement trend in the pit (even if it's wrapped) proves **Mining Activity is Happening**, which meets the project's goal of "Activity Monitoring" without the computational cost of full unwrapping.

### Q: "How is the plot sum calculated?"
**Method: Time-Series Reconstruction (Cumulative Sum)**
Since Interferometry measures the *difference* between two dates, we must sum them up to get the *total* change since the start.

1.  **2023 (Baseline)**: We assume $0$ displacement at the start. $$D_{2023} = 0$$
2.  **2024**: We add the displacement measured between 2023 and 2024. $$D_{2024} = D_{2023} + \Delta d_{23-24}$$
3.  **2025**: We add the displacement measured between 2024 and 2025. $$D_{2025} = D_{2024} + \Delta d_{24-25}$$

---

## 6. Requested Technical Details

### A. Full Pipeline Logic
The pipeline is an automated state machine orchestrated by `run_pipeline.py`:
1.  **Initialization**: Loads credentials and checks for SNAP tools.
2.  **Acquisition (`main_script.py`)**: 
    -   Queries CDSE for SLC images over the ROI (Chuquicamata).
    -   Locks the "Relative Orbit" from the first valid image (to ensure consistent viewing geometry).
    -   Downloads missing scenes to `data/input_slc`.
3.  **Interferometry (`main_script.py`)**:
    -   Pairs images chronologically ($t_1 \to t_2$, $t_2 \to t_3$).
    -   Executes SNAP GPT graph: Split $\to$ Orbit $\to$ Back-Geocoding $\to$ Interferogram $\to$ Deburst.
    -   Outputs complex interferograms (.dim) to `data/output_int`.
4.  **Analysis (`plot_*.py`)**:
    -   Scans outputs for the Mine Pit location (lowest coherence).
    -   Extracts Phase and Coherence timeseries.
    -   Generates Plots and CSVs.

### B. Data Flow
`Cloud (CDSE)` $\xrightarrow{\text{Download}}$ `data/input_slc/*.zip` $\xrightarrow{\text{SNAP GPT}}$ `data/output_int/*.dim` $\xrightarrow{\text{Python Analysis}}$ `results/*.png & *.csv`

### C. Scientific Assumptions
1.  **Zero Start**: We assume displacement is 0 at the first date ($t_0$).
2.  **Dominant Verticality**: We assume LOS change corresponds significantly to vertical subsidence in a pit scenario.
3.  **Coherence Filter**: We assume pixels with Coherence $< 0.3$ are unreliable.
4.  **Atmosphere**: We assume atmospheric delay is random and averages out over long time-series.

### D. Folder Structure
*   `src/`: Codebase (Python scripts & SNAP XML graph).
*   `data/`: Large binary files (Input Zips, Output Interferograms).
*   `results/`: Final deliverables (Plots, CSVs).
*   `logs/`: Execution logs.

### E. Processing Sequence (The Graph)
1.  **Read**: Load Master/Slave.
2.  **TOPSAR-Split**: Select Subswath IW2 + Polarization VV.
3.  **Apply-Orbit**: Apply Precise Orbit Ephemerides (POE).
4.  **Back-Geocoding**: DEM-assisted Co-registration (SRTM 3sec).
5.  **Interferogram**: Compute $\Delta\phi = \phi_{slave} - \phi_{master}$.
6.  **TOPSAR-Deburst**: Merge bursts.
7.  **Write**: Save result.

### F. Where Deformation is Computed
*   **Script**: `src/plot_displacement.py`
*   **Method**: `get_displacement_data()`
*   **Logic**:
    1.  Read wrapped phase (radians) at pit center.
    2.  Check coherence $> 0.3$.
    3.  Convert: $d = (\text{phase} * \lambda) / (-4\pi)$.

### G. Where Coherence is Used
1.  **Pit Detection**: `plot_displacement.py` finds the coherence "hole" (the mine).
2.  **Quality Control**: `plot_coherence.py` tracks mean stability.
3.  **Filtering**: Unreliable pixels are rejected.

### H. Limitations
1.  **Wrapped Phase**: Large movements ($>2.8$cm) wrap around.
2.  **1D Measurement**: Cannot separate Vertical vs. Horizontal motion.
3.  **Atmosphere**: Turbulence can mimic deformation.
4.  **Decorrelation**: Fast ground changes destroy the signal.


