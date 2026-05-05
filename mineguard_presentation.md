# MineGuard: Advanced InSAR Subsidence Monitoring
## Final Project Presentation

---

### Slide 1: Title
**Title:** MineGuard: Automated Satellite InSAR Subsidence Monitoring  
**Subtitle:** An End-to-End Pipeline for Geotechnical Deformation Tracking  
**Presenter:** [Your Name / Ujjwal Rawat]  
**Project Duration:** 8 Weeks  

**Layout/Visual Suggestion:**  
A clean title slide with a high-resolution, wide-angle image of a mining site or a stylized satellite graphic (Sentinel-1) in the background. Logos of the university and your department at the bottom.

**Speaker Notes:**  
"Good morning, respected professors. Today I am presenting MineGuard, an automated monitoring system developed over the past 8 weeks. MineGuard leverages Sentinel-1 satellite radar data to track ground displacement and predict subsidence risks in mining areas. I will walk you through the architecture of this system, demonstrating how we evolved the platform week by week, page by page, into a complete geotechnical tool."

---

### Slide 2: Week 1 – Search Mine (Page 1)
**Title:** Week 1: Global Mine Search & Localization  
**Core Purpose:** Establishing the entry point to instantly locate and map any mine globally.

**Key Technical Features:**
*   **Real-time Geocoding:** Queries the Nominatim OpenStreetMap API instantly as the user types.
*   **Dynamic Dropdown:** Displays live, accurate geographical search matches.
*   **Interactive Mapping:** Automatically centers a high-resolution Leaflet map (Esri World Imagery) on the target coordinates.

**Layout/Visual Suggestion:**  
A screenshot of the MineGuard search bar with the dropdown active, placed next to the Leaflet map zoomed in on a specific mining site.

**Speaker Notes:**  
"In Week 1, we built the foundation: Page 1. The goal was global accessibility. We integrated the Nominatim OpenStreetMap API so users can type the name of any mine in the world. The system instantly fetches the coordinates and centers our interactive map over the site using high-resolution Esri satellite imagery."

---

### Slide 3: Week 2 – Crop Area (Page 2)
**Title:** Week 2: Defining the Region of Interest (ROI)  
**Core Purpose:** Allowing precise, interactive demarcation of the monitoring zone.

**Key Technical Features:**
*   **Interactive Polygon Drawing:** Users physically click points on the map to bound the target area.
*   **Coordinate Extraction:** Automatically extracts exact North, South, East, and West GPS boundaries.
*   **Global State Management:** Employs React Context API to retain coordinates across subsequent pages.

**Layout/Visual Suggestion:**  
A screenshot of Page 2 showing the red bounding box drawn over the mine, with the latitude/longitude input fields visible on the side panel.

**Speaker Notes:**  
"Week 2 focused on spatial bounding on Page 2. Processing satellite data is computationally expensive, so we must limit our focus.  We implemented interactive polygon drawing, allowing the user to simply click on the map to tightly crop the Region of Interest. The exact latitude and longitude boundaries are extracted and saved securely in the app's global state."

---

### Slide 4: Week 3 – Timeline Selection (Page 3)
**Title:** Week 3: Temporal Scope & Processing Estimation  
**Core Purpose:** Configuring the time-series parameters and estimating computational load.

**Key Technical Features:**
*   **Customizable Timeframes:** Users select start/end years and the frequency of data analysis.
*   **Dynamic Estimation Engine:** Mathematically estimates required data volume (in Gigabytes).
*   **Predictive Processing Times:** Gives users real-time feedback on expected backend calculation times.

**Layout/Visual Suggestion:**  
A clean graphic of the timeline selection sliders alongside an infographic or highlighted text showing "Estimated Data: 28 GB, Processing Time: ~3 Hours".

**Speaker Notes:**  
"Moving to Week 3 and Page 3, we targeted time. Users define their monitoring period—say, 2018 to 2021. Because satellite files are massive, our frontend dynamically estimates the total data volume and expected processing time before the user commits, preventing accidental server overloads."

---

### Slide 5: Week 4 – Data Download (Page 4)
**Title:** Week 4: Multi-Gigabyte Data Retrieval  
**Core Purpose:** Robust, asynchronous downloading of massive Sentinel-1 datasets.

**Key Technical Features:**
*   **Background Asynchronous Downloads:** Prevents UI freezing while handling heavy (7GB+) ESA Copernicus queries.
*   **Local Directory Linking:** Allows users to bypass downloads if files already exist on local hardware.
*   **File Verification:** Ensures absolute data integrity before InSAR processing begins.

**Layout/Visual Suggestion:**  
A split view: one side showing the "Link Local Directory" UI button, and the other showing download progress indicators for the heavy satellite files.

**Speaker Notes:**  
"In Week 4, we tackled the heavy lifting on Page 4. Sentinel-1 images are roughly 7 Gigabytes each. We built a robust background download manager so the user interface never freezes. To save immense amounts of time for repeated testing, we also engineered a 'Local Link' feature allowing the pipeline to read existing files directly off the hard drive."

---

### Slide 6: Week 5 – Processing Phase (Page 5)
**Title:** Week 5: Live Pipeline Orchestration  
**Core Purpose:** Controlling the SNAP processing engine with parallel worker management.

**Key Technical Features:**
*   **Backend SNAP Integration:** Direct triggering of complex Python InSAR workflows from the browser.
*   **Live Queue Management:** Polling architecture for 3-second real-time status updates without file lock contention.
*   **Visual Status Indicators:** Color-coded badges for 'Pending', 'Processing', and 'Complete' paired interferograms.

**Layout/Visual Suggestion:**  
A screenshot of Page 5's processing dashboard, clearly highlighting the green "Complete" badges and the "Start/Stop" worker controls.

**Speaker Notes:**  
"Week 5 was the most technically complex for the backend. Page 5 orchestrates the SNAP engine. We established a lock-free queue system where the frontend continuously polls the Python backend every 3 seconds. Users see exactly which image pairs are generating interferograms via live progress bars, bridging the gap between heavy data science and smooth user experience."

---

### Slide 7: Week 6 – Hotspot Selection (Page 6)
**Title:** Week 6: Targeted Deformation Tracking  
**Core Purpose:** Empowering users to place virtual sensors on specific high-risk zones.

**Key Technical Features:**
*   **Precision Marker Placement:** Click-to-place tracking functionality for up to 10 high-risk nodes.
*   **Boundary Validation:** Prevents markers from being placed outside the designated ROI.
*   **Coordinate Handoff:** Feeds exact pixel latitude/longitude directly into the final displacement algorithms.

**Layout/Visual Suggestion:**  
A large screenshot of the satellite map containing colourful drop-pins (Hotspots P1 - P5) scattered across a visible mining pit.

**Speaker Notes:**  
"In Week 6, we introduced targeted tracking on Page 6. Rather than simply returning a chaotic colour map of the whole site, users can drop up to 10 specific virtual 'hotspots' on collapsing slopes or critical infrastructure. These precise coordinates are sent back to the engine for highly rigorous time-series extraction."

---

### Slide 8: Week 7 – Results & Advanced Analysis (Page 7)
**Title:** Week 7: True 2D Displacement Analysis  
**Core Purpose:** Displaying mathematically rigorous subsidence metrics using dual-orbit vector decomposition.

**Key Technical Features:**
*   **ASC + DSC Decomposition:** Combines Ascending and Descending orbits to separate true horizontal and vertical movement.
*   **Multi-Dimensional Plotting:** Generates Horizontal (E-W) drift charts and raw Line-of-Sight graphs.
*   **3D Trajectory Visualization:** Plots the exact x/y/z physical failure path of the mine over time.

**Layout/Visual Suggestion:**  
A multi-panel slide. Insert screenshots of the three main plots: the Horizontal Displacement line graph, the bar chart for LOS, and the 3D Trajectory map showing diverging lines.

**Speaker Notes:**  
"Week 7 represents the scientific core of MineGuard. A single satellite pass is mathematically ambiguous. Here on Page 7, we utilized 2D Vector Decomposition—combining both Ascending and Descending passes. This breakthrough allows our software to output three irrefutable graphs: true East-West slide, vertical subsidence, and a 3D trajectory plot showing exactly how and where the ground is failing."

---

### Slide 9: Week 8 – Automated Summary Engine (Page 8)
**Title:** Week 8: Automated Geotechnical Reporting  
**Core Purpose:** Translating raw numerical displacement data into standard engineering verdicts.

**Key Technical Features:**
*   **Data Aggregation:** Automatically calculates total cumulative displacement per hotspot.
*   **Threshold-based Logic:** Assigns standardized risk tiers (Low, Medium, High, Critical).
*   **Dynamic Response Generation:** Outputs natural-language executive summaries and actionable engineering recommendations.

**Layout/Visual Suggestion:**  
A screenshot of the final generated Page 8 report, specifically highlighting the colour-coded risk table (e.g., Critical/Red, Low/Green) and the generated text verdicts.

**Speaker Notes:**  
"Finally, in Week 8, we built Page 8. Raw data is useless without interpretation. We engineered a dynamic summary engine that reads the displacement values, crosses them with standard geotechnical risk thresholds, and generates a professional, ready-to-print report. It outputs a color-coded risk assessment and actionable engineering advice without any human intervention."

---

### Slide 10: Conclusion & Q&A
**Title:** Conclusion & Future Scope  
**Core Purpose:** Summarizing the success of MineGuard and opening the floor to the panel.

**Summary Points:**
*   Successfully automated a highly complex InSAR workflow.
*   Delivered a user-friendly, responsive interface for non-technical site managers.
*   Proved the viability of remote, low-cost subsidence monitoring.

**Layout/Visual Suggestion:**  
A clean slide with a brief bulleted summary of achievements, and a bold "Thank You / Any Questions?" text in the center.

**Speaker Notes:**  
"In conclusion, MineGuard takes an incredibly complex, localized science—InSAR processing—and scales it globally via an intuitive web platform. We have successfully automated the detection of hazardous ground displacement. I want to thank the panel for your time and guidance over these 8 weeks. I am now open to any questions."
