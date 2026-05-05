# MineGuard Defense: Complex Q&A Cheat Sheet

If the panel presses you with tough technical or architectural questions, stay calm. Use these answers to show that you deeply understand the limitations and complex science behind your project.

---

### Category A: Product Differentiation & Market Fit

**Q1: "There are already commercial InSAR platforms (Tre-Altamira, SkyGeo) and open-source tools (LiCSBAS). How is MineGuard actually different?"**
* **The Answer:** "Most existing tools fall into two extremes. Open-source tools like LiCSBAS require heavy command-line Linux expertise and output raw velocity maps that field engineers can't interpret. Commercial options are 'black boxes' that cost tens of thousands of dollars per mine and require specialists. MineGuard bridges this gap. It fully automates the complex ESA SNAP engine underneath a totally guided 8-page React web UI. Moreover, we explicitly prioritize **2D East-West Decomposition** to warn against lateral failure, whereas many entry-level platforms only provide 1-dimensional Line-of-Sight (LOS) data."

---

### Category B: The InSAR Science & Limitations

**Q2: "InSAR suffers heavily from temporal decorrelation—meaning if the ground changes too much, you lose the signal. An active open-pit mine has trucks digging constantly. How do you get accurate data?"**
* **The Answer:** "You're absolutely right about decorrelation. That is exactly why we enforce a strict **temporal baseline of 12 days or less** when pairing images. By keeping the time window extremely short, stable structures like the high-walls, access ramps, and surrounding infrastructure—which are exactly the danger zones we care about—maintain very high phase coherence. The actively dug pit floor might decorrelate, but our Goldstein adaptive phase filter masks out that noise, ensuring our tracked Hotspots pull from reliable radar scatterers."

**Q3: "Wait, you showed a '3D Trajectory' chart, but in your methodology, you only solve a 2×2 matrix for East-West and Vertical. What happened to North-South deformation?"**
* **The Answer:** "This is a hardware limitation of polar-orbiting radar satellites, not a software flaw. Sentinel-1 orbits almost perfectly North-to-South. Because its radar beam looks out sideways, it is highly sensitive to East-West and Vertical motion, but it is almost completely blind to North-South movement. To measure North-South, we would have to use Amplitude Offset Tracking, which only has an accuracy of several meters, not millimetres. In geotechnical engineering, East-West pit-wall expansion is the primary failure mode, so our 2D decomposition covers the most critical threat vector at millimetre precision."

**Q4: "Radar signals are delayed by water vapor in the atmosphere. Did you apply Atmospheric Phase Screen (APS) corrections? If not, aren't your millimeter measurements wrong?"**
* **The Answer:** "For large regional mapping (like measuring a whole city or state), atmospheric correction is strictly necessary. However, MineGuard focuses on extremely localized Regions of Interest—usually just a 3×3 kilometer mine pit. Over such a tiny spatial scale, the tropospheric delay is uniform across the image. Because we measure differential displacement (how much one side of the pit moved relative to the other), that uniform atmospheric 'error' effectively cancels itself out. Integrating a weather model like GACOS is definitely on our roadmap for a v2.0 upgrade, though."

---

### Category C: Software Architecture & Scaling

**Q5: "Running ESA SNAP interferometry is notoriously slow and crashes computers because it requires massive RAM. If this is a web app, how do you stop the user's browser from timing out while it processes?"**
* **The Answer:** "To solve this, we completely decoupled the frontend from the heavy processing using an asynchronous architecture. When a user clicks 'Process', the React frontend doesn't wait for a synchronous HTTP network response. Instead, the Python FastAPI backend launches a background subprocess worker to handle the heavy SNAP graph. The frontend simply polls a lightweight `/status` endpoint every 3 seconds to update the UI dashboard colors. This prevents browser timeouts entirely and isolates the heavy 16GB memory footprint to the backend server."

**Q6: "Why use SNAP instead of writing your own InSAR algorithms in Python using something like ISCE?"**
* **The Answer:** "ESA SNAP provides rigorously validated, industry-standard graph processing tools natively built for Sentinel-1. While ISCE is powerful, SNAP's XML-based Graph Processing Tool (GPT) allows us to build a highly reproducible, automated pipeline that we can easily trigger from Python via `subprocess`. It offered the most robust phase unwrapping and terrain correction compatibility without sacrificing computational stability."
