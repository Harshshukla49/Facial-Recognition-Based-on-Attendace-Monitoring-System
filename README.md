# Face Recognition Based Attendance Monitoring System

A modern, dual-mode (Web + GUI) attendance system using OpenCV face recognition (LBPH Face Recognizer) and Haar Cascades.

---

## 🚀 Quick Start (Run on Localhost)

To launch the modern web application on your local machine:

### 1. Activate Virtual Environment & Install Dependencies
```bash
# In Windows PowerShell:
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Run on Localhost
```bash
python run_localhost.py
# Or directly with Flask:
python app.py
```
Open your web browser at: **[http://127.0.0.1:5000](http://127.0.0.1:5000)** or **[http://localhost:5000](http://localhost:5000)**.

---

## 🌟 Key Features

1. **Live Attendance Kiosk**:
   - Real-time webcam face detection and recognition using OpenCV LBPH.
   - Dynamic today's attendance table updating instantly without page reload.
   - Built-in sound feedback and duplicate prevention cooldown.
   - One-click CSV export.

2. **Student Enrollment**:
   - Register new students with ID and Name.
   - Interactive live webcam face sample capture (50 samples with real-time progress bar).

3. **LBPH Model Training**:
   - Password-protected model training (`Trainner.yml`) directly from the browser.
   - Default password: `shukla` (can be changed anytime via the Settings modal).

4. **Attendance History & Analytics**:
   - Filter attendance by any past date.
   - Search by student ID or Name.
   - Export full attendance logs to CSV.

5. **Desktop Mode (Tkinter GUI)**:
   - You can also run the original desktop GUI by executing:
     ```bash
     python main.py
     ```

---

## 🛠️ Technology Stack
- **Backend**: Python 3, Flask, OpenCV (`cv2.face.LBPHFaceRecognizer`), NumPy, Pandas, Pillow
- **Frontend**: HTML5, Modern Glassmorphic CSS3, Vanilla JavaScript (WebRTC Camera Stream, Web Audio API)
- **Data Storage**: CSV (`StudentDetails/`, `Attendance/`), YAML (`TrainingImageLabel/Trainner.yml`)

