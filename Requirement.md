## 🧭 Directional Zone System — Updated Requirement

### Zone Layout Definition

The video frame is divided into **directional zones** based on spatial position:

```
┌─────────────────────────────────┐
│                                 │
│           NORTH ZONE            │
│                                 │
├────────┬────────────┬───────────┤
│        │            │           │
│  WEST  │   CENTER   │   EAST    │
│  ZONE  │    ZONE    │   ZONE    │
│        │            │           │
├────────┴────────────┴───────────┤
│                                 │
│           SOUTH ZONE            │
│                                 │
└─────────────────────────────────┘
```

- Zones are **auto-mapped** to the video frame dimensions on upload
- User can **fine-tune boundaries** by dragging zone borders
- Center zone is **optional** — can be enabled/disabled
- Each zone covers a defined percentage of the frame (configurable, default equal split)

---

## 📋 Updated Full Flow Requirement

### 1. Input Layer
- Accept **video file** or **image sequence**
- On upload, the system **auto-divides the frame** into North / South / East / West (+ optional Center)
- User can adjust zone boundaries via slider or drag handles
- Each directional zone is **color-coded** for visual clarity:

| Zone   | Default Color  |
| ------ | -------------- |
| North  | 🔵 Blue         |
| South  | 🟡 Yellow       |
| East   | 🟢 Green        |
| West   | 🔴 Red          |
| Center | ⚪ White / Gray |

---

### 2. People Detection & Tracking
*(Unchanged from base requirement)*
- Head/body detection per frame
- Unique Person ID assigned
- Continuous tracking across frames
- Re-entry handling

---

### 3. IN Time / OUT Time Logging — Zone-Wise

Each entry/exit event now includes the **directional zone**:

| Field      | Description                          |
| ---------- | ------------------------------------ |
| Person ID  | Unique identifier                    |
| Zone Name  | North / South / East / West / Center |
| IN Time    | When person entered this zone        |
| OUT Time   | When person exited this zone         |
| Dwell Time | Time spent in this zone              |
| Came From  | Previous zone (or "Outside")         |
| Went To    | Next zone (or "Outside")             |

- A person **moving from West → Center → East** will generate 3 separate zone-level IN/OUT records
- **Cross-zone transition events** are logged (e.g., "Person 04 moved North → East at 00:02:15")

---

### 4. Directional Zone Configuration

| Setting              | Description                                 |
| -------------------- | ------------------------------------------- |
| Zone Split Mode      | Equal split / Custom boundary               |
| North Zone Height    | % of frame height from top (default 25%)    |
| South Zone Height    | % of frame height from bottom (default 25%) |
| East Zone Width      | % of frame width from right (default 25%)   |
| West Zone Width      | % of frame width from left (default 25%)    |
| Center Zone          | Remaining middle area (optional)            |
| Enable/Disable Zones | Each zone can be individually toggled       |

---

### 5. Zone-Wise People Count — Directional

Real-time and historical count per directional zone:

| Zone   | Current Count | Peak Count | Avg Count | Dwell Avg |
| ------ | ------------- | ---------- | --------- | --------- |
| North  | 5             | 12         | 7.2       | 00:01:30  |
| South  | 3             | 8          | 4.1       | 00:00:45  |
| East   | 7             | 15         | 9.3       | 00:02:10  |
| West   | 2             | 6          | 3.0       | 00:01:05  |
| Center | 10            | 20         | 11.5      | 00:00:30  |

---

### 6. Density Threshold — Per Directional Zone

- Each directional zone has its **own configurable density threshold**
- Density = People count / Zone pixel area
- Alert when any zone breaches its threshold

| Zone  | Area (px²) | Max Density | Current Density | Status    |
| ----- | ---------- | ----------- | --------------- | --------- |
| North | 320×180    | 0.05        | 0.03            | ✅ Normal  |
| South | 320×180    | 0.05        | 0.07            | 🔴 Alert   |
| East  | 160×360    | 0.04        | 0.04            | ⚠️ Warning |
| West  | 160×360    | 0.04        | 0.01            | ✅ Normal  |

---

### 7. Average Head Velocity — Per Directional Zone

- Velocity tracked per person, averaged per directional zone
- **Directional velocity vector** also tracked — is person moving **toward** or **away** from zone center?

| Zone  | Avg Velocity (px/s) | Dominant Direction              | Status          |
| ----- | ------------------- | ------------------------------- | --------------- |
| North | 12.5                | Moving South → toward Center    | Normal          |
| South | 45.2                | Moving South → away from Center | 🔴 Running Alert |
| East  | 8.1                 | Stationary / slow               | ⚠️ Loitering     |
| West  | 20.3                | Moving East → toward Center     | Normal          |

---

### 8. Anomaly Detection — Directional Zone Aware

#### 8A. Zone-Level Anomalies (Updated for Directions)

| Anomaly Type              | Trigger Condition                                              | Zone Context                                         |
| ------------------------- | -------------------------------------------------------------- | ---------------------------------------------------- |
| **Overcrowding**          | Count > density threshold                                      | Per zone: "North Zone overcrowded"                   |
| **Loitering**             | Dwell time > limit                                             | Per zone: "Person 03 loitering in West Zone"         |
| **Wrong Direction Flow**  | Movement against defined flow direction                        | e.g., moving North in a South-only corridor          |
| **Restricted Zone Entry** | Entry into restricted directional zone                         | e.g., "Person entered North Zone (restricted)"       |
| **Crowd Surge**           | Rapid count increase in a zone                                 | e.g., "East Zone surged from 2 → 14 in 10 sec"       |
| **Zone Abandonment**      | Zone count drops to 0 suddenly                                 | e.g., "South Zone emptied in 3 sec — possible panic" |
| **Cross-Zone Flooding**   | Multiple persons flow from one zone to adjacent simultaneously | e.g., mass movement North → Center                   |

#### 8B. Person-Level Anomalies (Direction Aware)

| Anomaly Type            | Trigger                                       | Direction Context                                |
| ----------------------- | --------------------------------------------- | ------------------------------------------------ |
| **Running**             | Velocity > threshold                          | In which zone: "Running detected in South Zone"  |
| **Stationary too long** | Velocity ≈ 0 for > time limit                 | "Person 07 stationary in East Zone for 3 min"    |
| **Erratic Movement**    | Random direction changes                      | "Person 02 moving erratically in Center Zone"    |
| **Re-entry**            | Same person exits and re-enters rapidly       | "Person 11 re-entered West Zone within 30 sec"   |
| **Counter Flow**        | Person moving opposite to dominant crowd flow | "Person 05 moving North while crowd flows South" |

#### 8C. Cross-Zone Transition Anomalies *(New)*

| Anomaly                     | Trigger                                                                            |
| --------------------------- | ---------------------------------------------------------------------------------- |
| **Skipped Zone**            | Person teleports from North to South without passing through Center (tracking gap) |
| **Rapid Zone Switching**    | Person switches between zones too fast (possible ID swap or occlusion error)       |
| **Blocked Zone Transition** | Crowd density blocks movement between zones (bottleneck detection)                 |

---

### 9. Output & Reporting — Directional Zone Report

**Per Session Report includes:**
- Zone-wise IN/OUT log with timestamps
- Cross-zone transition map (flow diagram: how many people moved North→East, West→Center, etc.)
- Density over time graph per zone
- Velocity heatmap per zone
- All anomaly events tagged with zone name
- **Zone Flow Diagram:**

```
        [North: 45 IN / 38 OUT]
               ↕
[West: 22] ←→ [Center: 91] ←→ [East: 67]
               ↕
        [South: 33 IN / 29 OUT]
```

---

### 10. Configuration Panel — Updated

| Setting                      | Options                                                  |
| ---------------------------- | -------------------------------------------------------- |
| Zone Mode                    | Auto Equal Split / Custom Boundary                       |
| Active Zones                 | Toggle North / South / East / West / Center individually |
| Per-Zone Max Density         | Numeric input per zone                                   |
| Per-Zone Max Dwell Time      | Time input per zone                                      |
| Per-Zone Velocity Thresholds | High (running) / Low (loitering) per zone                |
| Defined Flow Direction       | Set expected movement direction per zone                 |
| Restricted Zones             | Mark any zone as restricted                              |
| Color Coding                 | Customize zone overlay colors                            |

---

## 🔄 Updated End-to-End Flow

```
Upload Video/Image
       ↓
Auto Zone Division (North / South / East / West / Center)
User adjusts boundaries if needed
       ↓
Frame-by-Frame Processing
       ↓
Person Detection → Tracking → ID Assignment
       ↓
Zone Assignment per frame (which directional zone is person in?)
       ↓
IN Time / OUT Time logging per zone per person
Cross-Zone Transition Events logged
       ↓
Zone-Wise Count Update (N / S / E / W / Center)
       ↓
Density Calculation per Directional Zone
       ↓
Head Velocity Calculation → Zone-Wise Average Velocity
Directional velocity vector computed
       ↓
Anomaly Detection:
  → Zone-level (overcrowding, loitering, surge, abandonment)
  → Person-level (running, stationary, counter-flow, erratic)
  → Cross-zone (skipped zone, rapid switching, bottleneck)
       ↓
Alert Generation + Zone Overlay on Frame
       ↓
Session Report Export (CSV / PDF / Dashboard)
Zone Flow Diagram generated
```
