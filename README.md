<div align="center">
  
# 🚨 TRIAGE
**Time-critical Routing & Intelligent Ambulance Guidance Engine**

[![IBM Z / LinuxONE](https://img.shields.io/badge/IBM_Z_/_LinuxONE-Ready-006699?style=for-the-badge&logo=ibm)](https://www.ibm.com/it-infrastructure/z)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)]()
[![Scikit-Learn](https://img.shields.io/badge/Scikit_Learn-F7931E?style=for-the-badge&logo=scikit-learn&logoColor=white)]()

*Built for the 2026 IBM Z Datathon • Theme: Real-Time AI for Critical Decisions*

</div>

---

## 💔 The Problem: The "Hospital Stampede"
In the UK, over **44,000 patients suffer severe harm every year** due to ambulance handover delays exceeding 30 minutes outside overcrowded Emergency Departments (EDs). 

Currently, standard navigation systems route 999 ambulances to the absolute *closest* hospital. But in an emergency surge, if 5 ambulances all head to the exact same "closest" hospital, it creates a lethal bottleneck—a **Hospital Stampede**. Patients end up waiting hours in the parking lot, while a hospital just 5 minutes further away might have empty beds and zero queue.

## 💡 The Solution: TRIAGE
**TRIAGE** is a real-time, AI-powered dispatch simulation running on **IBM LinuxONE (s390x)**. It replaces naive "closest-distance" routing with a joint-optimization engine that balances patient severity, live traffic, and hospital queues simultaneously across Greater Manchester.

### How It Works (The 3 Pillars)
1. 🧠 **PREDICT (Predictive AI):** As soon as an ambulance picks up a patient, our `HistGradientBoostingRegressor` (trained on LinuxONE) analyzes their vitals (SpO2, HR, BP) to predict their Starting Severity ($S_0$) and live Deterioration Rate.
2. 🗺️ **DECIDE (Joint AI Routing):** Instead of routing ambulances independently, TRIAGE uses the **Hungarian Algorithm** to evaluate the entire fleet at once. It automatically diverts less-critical patients to slightly further hospitals to save the closest beds for the most critical patients, eliminating stampedes.
3. 💬 **COMMUNICATE (Generative AI):** As the ambulance approaches, TRIAGE uses **DeepSeek via OpenRouter** to synthesize a crisp, 40-word clinical pre-alert note for the reception team, ensuring doctors are prepared before the doors even open.

---

## 🚀 Key Features
*   **Uber-Like Live Map:** A high-performance Leaflet.js frontend featuring smooth 60FPS ambulance tracking, live route polylines, and interactive hospital stress monitoring.
*   **Dynamic Time-of-Day Traffic:** Instantly recalculates 7,100+ Manchester street segments based on Rush Hour vs. Off-Peak traffic curves.
*   **Interactive Roadblocks:** Click anywhere on the map to drop a live roadblock and watch the AI instantaneously detour ambulances through surrounding streets.
*   **44,000 Impact Calculator:** At the end of every simulation, TRIAGE calculates exactly how many minutes of waiting time were saved and projects the reduction in annual severe harm cases compared to the national baseline.

---

## 🛠️ Technical Architecture

TRIAGE is a server-authoritative simulation designed specifically for the **s390x (Big Endian)** architecture of IBM LinuxONE.

*   **Backend / Engine:** Python 3.12, FastAPI, Uvicorn.
*   **AI / Machine Learning:** `scikit-learn` (HistGradientBoostingRegressor) trained natively on the mainframe to avoid cross-endian pickle corruption.
*   **Routing Math:** `scipy.sparse.csgraph.dijkstra` running Backwards Dijkstra over a CSR sparse matrix of Greater Manchester for sub-15ms route recalculations.
*   **Assignment Solver:** `scipy.optimize.linear_sum_assignment`.
*   **Generative AI:** `httpx` async calls to DeepSeek-V3, featuring strict numeric hallucination guards and instant deterministic template fallbacks.
*   **Frontend:** Pure HTML/CSS/JS, Leaflet.js (CartoDB/OSM Tiles), completely decoupled from the backend via WebSockets (5Hz tick rate).

---

## 💻 How to Run Locally (or on LinuxONE)

TRIAGE is containerized and ready to deploy on both `x86_64` (Windows/Mac) and `s390x` (IBM LinuxONE).

### 1. Clone the Repository
```bash
git clone -b main https://github.com/w-sung/IBMZ_TRIAGE.git
cd IBMZ_TRIAGE
```

### 2. Setup Environment Variables
Create a `.env` file in the root directory for the Generative AI features:
```bash
echo "OPENROUTER_API_KEY=your_api_key_here" > .env
echo "LLM_MODEL=deepseek/deepseek-chat" >> .env
```
*(Note: If no API key is provided, the app will gracefully fallback to deterministic local templates without crashing).*

### 3. Run the Server
We recommend running via standard Python for the easiest setup:
```bash
pip install -r requirements.txt
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

### 4. Open the App
Navigate to **`http://localhost:8000`** in your web browser. 
*(If running on a remote IBM LinuxONE instance, set up an SSH tunnel: `ssh -L 8000:localhost:8000 user@linuxone_ip` first).*

---

# 🌟 Open Source Resources & Credits

As per the IBM Z Datathon 2026 submission guidelines, the **TRIAGE (Time-critical Routing and Intelligent Ambulance Guidance Engine)** project proudly leverages the following open-source technologies, libraries, and datasets:

### 🐍 Python Backend & AI Engine
*   **FastAPI:** High-performance web framework used to build our backend API and serve our WebSockets. 
    *   Link: [https://fastapi.tiangolo.com/](https://fastapi.tiangolo.com/)
*   **Uvicorn:** ASGI web server implementation for Python.
    *   Link: [https://www.uvicorn.org/](https://www.uvicorn.org/)
*   **Scikit-Learn:** Machine learning library used for our `HistGradientBoostingRegressor` to predict patient deterioration severity.
    *   Link: [https://scikit-learn.org/](https://scikit-learn.org/)
*   **SciPy:** Scientific computing library. We used `scipy.optimize.linear_sum_assignment` (Hungarian Algorithm) for joint routing, and `scipy.sparse.csgraph.dijkstra` for ultra-fast backwards routing graphs.
    *   Link: [https://scipy.org/](https://scipy.org/)
*   **NumPy:** Used for high-performance numerical array computations.
    *   Link: [https://numpy.org/](https://numpy.org/)
*   **HTTPX:** Async HTTP client used to fetch our Generative AI handover notes.
    *   Link: [https://www.python-httpx.org/](https://www.python-httpx.org/)
*   **NetworkX:** Used strictly in our data-generation script to calculate geographic nodes and edges for the street graph.
    *   Link: [https://networkx.org/](https://networkx.org/)

### 🗺️ Frontend UI & Mapping
*   **Leaflet.js (v1.9.4):** Open-source JavaScript library used for mobile-friendly, interactive 2D maps and rendering our animated ambulances.
    *   Link: [https://leafletjs.com/](https://leafletjs.com/)
*   **Google Fonts:** Used for the "Inter" and "JetBrains Mono" typefaces in our UI.
    *   Link: [https://fonts.google.com/](https://fonts.google.com/)

### 📊 Datasets & Third-Party APIs
*   **OpenStreetMap (OSM):** Map tile imagery and underlying geographic road network data. 
    *   *Attribution:* "Map data © OpenStreetMap contributors". Data is available under the Open Database License.
    *   Link: [https://www.openstreetmap.org/copyright](https://www.openstreetmap.org/copyright)
*   **DeepSeek-V3 via OpenRouter:** The Generative AI model used to synthesize 40-word clinical handover reception notes.
    *   Link: [https://openrouter.ai/models/deepseek/deepseek-chat](https://openrouter.ai/models/deepseek/deepseek-chat)