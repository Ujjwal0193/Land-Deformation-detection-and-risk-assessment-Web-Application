# MineGuard Final Defense: 8-Minute Pitch Script

> **Pacing Strategy**: 8 minutes for 14 slides means an average of **34 seconds per slide**. Don't rush—speak clearly. Use the time guides next to each slide to keep yourself on track. You have about 30 seconds of buffer built in.

---

### Slide 1: Title Card (0:00 - 0:15)
"Good morning, professors and panel members. I'm Ujjwal Rawat, and today I'm excited to present my final year project: **MineGuard**. MineGuard is a fully automated, satellite-powered ground deformation monitoring system. We built it specifically with one user in mind: the everyday mine site engineer."

### Slide 2: Introduction (0:15 - 0:50)
"So, what exactly is MineGuard? Right now, mining excavations cause the ground to sink and slide, and traditional sensors to track this are expensive and geographically limited. MineGuard solves this by using free Sentinel-1 radar data from the European Space Agency. It processes highly complex InSAR interferograms entirely in the background, delivering millimetre-precision displacement data and automated risk reports through a simple web interface. No coding or satellite expertise is required by the user."

### Slide 3: Design Philosophy (0:50 - 1:10)
"Our core design philosophy was total accessibility. We built MineGuard so that a field engineer can log in, easily follow clearly numbered steps, and run complex scientific data pipelines without ever seeing a line of code. We included boundary-safe inputs to prevent user errors, and we translate complex data into auto-generated, plain-English captions."

### Slide 4: Use Cases (1:10 - 1:30)
"This makes the platform incredibly versatile. A mine site engineer can use it for daily operational checks to replace expensive survey teams. Geotechnical consultants can use it to instantly generate printable compliance reports for clients. And academic researchers can export the raw CSV data for long-term subsidence studies."

### Slide 5: The Core Problem (1:30 - 2:10)
"But here is where MineGuard really differentiates itself. It's a known geotechnical fact that **horizontal** East-West sliding begins weeks before the ground visibly sinks. Yet, most conventional sensors and standard InSAR tools only measure vertical subsidence. By the time vertical settlement is noticeable, the lateral failure has already happened. MineGuard isolates this horizontal movement first—giving geotechnical teams a critical early warning window to intervene before a catastrophic landslide occurs."

### Slide 6: 3D Vector Space (2:10 - 2:45)
"Because we isolate that movement, MineGuard doesn't just give you a flat number. It maps every monitored hotspot into a true 3D vector space. Engineers can see exactly how much a point is moving horizontally on the X-axis, how much it is settling vertically on the Y-axis, and how fast it’s accelerating through time on the Z-axis. This reveals the true, multi-directional flow of the failing rock mass."

### Slide 7: The Science / 2D Decomposition (2:45 - 3:30)
"How do we achieve this? A single satellite only gives us a blended Line-of-Sight measurement. MineGuard automatically pulls data from two opposing satellite flight paths: an Ascending pass and a Descending pass. By plugging the Line-of-Sight measurements from both opposite angles into a two-by-two linear system, and solving it analytically using Cramer's Rule, we mathematically strip away the vertical bias and lock onto the true East-West lateral drift."

### Slide 8: Methodology (3:30 - 4:05)
"Under the hood, this happens across five fully-automated stages. The system queries the Copernicus API to acquire paired imagery, runs the ESA SNAP processing engine to generate interferograms, unwraps the radar phase to extract true displacement in millimetres, performs that critical 2D decomposition, and finally passes the data through dynamic geotechnical thresholds to generate a final risk classification."

### Slide 9: Workflow Overview (4:05 - 4:30)
"For the user, this massive pipeline is abstracted into just eight simple web pages. The workflow is a seamless pipeline. It steps the user from simply searching for their mine's name in a search bar, all the way through to downloading the data, processing the math, and printing the final risk report. Let me quickly walk you through the interface."

### Slide 10: Pages 1 & 2 (4:30 - 5:00)
"On Page 1, the user simply types their mine name. Our API instantly geocodes the text and pans the interactive satellite map to the location. On Page 2, the user clicks to draw a bounding box around their specific Region of Interest. This tells our backend exactly where to focus, ensuring we don't waste time or bandwidth downloading irrelevant global data."

### Slide 11: Pages 3 & 4 (5:00 - 5:30)
"On Page 3, they set their time window. The app runs a smart estimation of how large the data will be—preventing accidental 200-gigabyte downloads. Once confirmed, Page 4 takes over, launching asynchronous background workers to query the ESA servers and download the heavy Sentinel-1 raw radar files without freezing the user's browser."

### Slide 12: Pages 5 & 6 (5:30 - 6:10)
"Page 5 is the processing dashboard. Behind the scenes, Python workers are executing the heavy SNAP InSAR engine. A live dashboard updates every 3 seconds to show exactly which pairs are running or complete. Once processed, we move to Page 6, where the user clicks directly on the satellite map to drop markers—our 'hotspots'—on exact danger zones like pit walls. The app captures the GPS coordinates and passes them to the analytics engine."

### Slide 13: Pages 7 & 8 RESULTS (6:10 - 7:00)
"Finally, the payoff. Page 7 generates our interactive plots, including the isolated East-West drift and the 3D trajectory path for every hotspot. Page 8 runs our automated risk algorithm. In a real test at the Jharia Coalfield, this engine successfully diagnosed severe divergent landslides. For instance, rather than just saying a point was sinking, our system detected massive horizontal shifts—like P1 creeping 315 millimetres eastward—instantly flagging it as a Critical Risk and generating automated engineering recommendations."

### Slide 14: Conclusion (7:00 - 7:30)
"In conclusion, MineGuard takes the immense power of satellite interferometry and makes it affordable, automated, and accessible. By mathematically stripping out vertical bias to detect early horizontal sliding, we give mine engineers the tools they need to prevent disasters before they happen, right from their web browser. 

Thank you for your time, I would now welcome any questions."
