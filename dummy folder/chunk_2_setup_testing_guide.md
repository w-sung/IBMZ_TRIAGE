# TRIAGE — Chunk 2: Greater Manchester Hospitals & Road Routing Guide

Awesome job getting Chunk 1 running and pushed to `arno-dev-branch`! Now let's wire up **Chunk 2** so our ambulances have the 8 Greater Manchester hospitals, a road network, dynamic time-of-day traffic, and C-speed Dijkstra routing.

---

## Step 1: Exact Folder & File Structure for Chunk 2

Look at the left Explorer sidebar in VS Code. We are adding **4 new files** (and two empty `__init__.py` package markers so Python can import `routing` and `sim`):

```text
IBMZ_TRIAGE/
├── backend/
│   └── app/
│       ├── __init__.py
│       ├── main.py
│       ├── routing/              <-- NEW FOLDER inside backend/app
│       │   ├── __init__.py       <-- NEW empty file
│       │   └── graph.py          <-- File 3: CSR matrix + backwards Dijkstra
│       └── sim/                  <-- NEW FOLDER inside backend/app
│           ├── __init__.py       <-- NEW empty file
│           └── traffic.py        <-- File 4: Dynamic time-of-day traffic & roadblocks
├── data/
│   ├── conditions.json
│   ├── patients.json
│   ├── hospitals.json            <-- File 1: The 8 Greater Manchester hospitals
│   ├── nodes.csv                 (auto-generated when you run build_graph.py)
│   └── edges.csv                 (auto-generated when you run build_graph.py)
└── scripts/
    ├── make_patients.py
    └── build_graph.py            <-- File 2: Generates Manchester road network CSVs
```

---

## Step 2: Visual Step-by-Step Guide in VS Code

1. **Create `data/hospitals.json`:**
   - In the left Explorer panel, click on your **`data`** folder.
   - Click the **New File** icon (page with `+`), type `hospitals.json`, and press `Enter`.
   - Paste the code from **`data/hospitals.json`** and press `Ctrl + S` to save.

2. **Create `scripts/build_graph.py`:**
   - Click on your **`Scripts`** (or `scripts`) folder in the left Explorer panel.
   - Click the **New File** icon, type `build_graph.py`, and press `Enter`.
   - Paste the code from **`scripts/build_graph.py`** and press `Ctrl + S` to save.

3. **Create `backend/app/routing/graph.py`:**
   - Click on **`backend/app`** in the left Explorer panel.
   - Click the **New Folder** icon (folder with `+`), type `routing`, and press `Enter`.
   - Inside `routing`, click **New File**, type `__init__.py`, and press `Enter` (leave it empty).
   - Inside `routing`, click **New File** again, type `graph.py`, and press `Enter`.
   - Paste the code from **`backend/app/routing/graph.py`** and press `Ctrl + S` to save.

4. **Create `backend/app/sim/traffic.py`:**
   - Click on **`backend/app`** again in the left Explorer panel (make sure you click `app`, not `routing`!).
   - Click the **New Folder** icon, type `sim`, and press `Enter`.
   - Inside `sim`, click **New File**, type `__init__.py`, and press `Enter` (leave it empty).
   - Inside `sim`, click **New File** again, type `traffic.py`, and press `Enter`.
   - Paste the code from **`backend/app/sim/traffic.py`** and press `Ctrl + S` to save.

---

## Step 3: Exact Terminal Commands to Install & Test Chunk 2

In your VS Code bottom **Terminal** (`PS C:\ibm\IBMZ_TRIAGE>`), run these three commands one by one:

### 1. Install `networkx`, `scipy`, and `numpy`
```powershell
pip install networkx scipy numpy
```

### 2. Run `scripts/build_graph.py` to generate `data/nodes.csv` and `data/edges.csv`
```powershell
python scripts/build_graph.py
```
You will see a summary showing **8 hospitals linked**, **425 road nodes**, **~2,200 directed road edges**, and **`Strongly connected: True`**.

### 3. Run the Routing & Traffic Self-Tests
```powershell
python -m backend.app.sim.traffic
python -m backend.app.routing.graph
```
You will see:
- Parallel road edges automatically deduplicated to their minimum travel time.
- All 8 hospitals' backwards Dijkstra travel times computed in **under 5 milliseconds** (well below the 100 ms target in `CONTEXT.md`).
- A live comparison of drive times from a sample ambulance node to all 8 Manchester hospitals at **8:22 PM (Off-Peak)** vs **Rush Hour**!

---

## Step 4: Save & Push Chunk 2 to Your Git Branch (`arno-dev-branch`)

Once those tests print out cleanly, run these 3 Git commands in your terminal to back up your work to GitHub:

```powershell
git add .
git commit -m "Complete Chunk 2: Manchester hospitals, road graph generator, CSR Dijkstra routing, and dynamic traffic"
git push origin arno-dev-branch
```