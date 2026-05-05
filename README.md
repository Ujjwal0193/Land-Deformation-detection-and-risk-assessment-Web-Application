# Land Deformation Detection and Risk Assessment Web Application

## Overview
**MineGuard** is a sophisticated system designed for monitoring land deformation in mining regions using Sentinel-1 InSAR (Interferometric Synthetic Aperture Radar) data. This application provides automated processing pipelines, hotspot detection, and risk assessment visualizations to ensure the safety and stability of mining environments.

## Key Features
- **InSAR Processing Pipeline:** Automated integration with SNAP (Sentinel Application Platform) for SLC data processing.
- **CDSE Integration:** Seamless searching and downloading of Sentinel-1 products from the Copernicus Data Space Ecosystem.
- **Risk Assessment:** Advanced analysis of ground displacement to identify high-risk zones.
- **Web Interface:** Interactive frontend for selecting regions of interest and visualizing deformation trends.

## Project Structure
- `MineGuard_Proto/`: Main application source code.
  - `mineguard/`: Backend (FastAPI) and Frontend (React) code.
  - `pipeline/`: Data download and processing queue management.
  - `src/`: Core InSAR analysis and plotting scripts.
- `mineguard_ieee_report.tex`: Technical research documentation.
- `requirements.txt`: Python dependency list.

## Setup Instructions
1. **Prerequisites:** 
   - Python 3.10+
   - SNAP (Sentinel Application Platform) installed and in PATH.
2. **Environment Variables:**
   Create a `.env` file in the root directory with your CDSE credentials:
   ```env
   CDSE_USER=your_email@example.com
   CDSE_PASS=your_password
   ```
3. **Installation:**
   ```bash
   pip install -r requirements.txt
   ```

## License
This project is for academic and professional research purposes.
