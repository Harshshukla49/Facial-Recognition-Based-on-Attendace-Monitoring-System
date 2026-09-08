// Face Recognition Attendance System - JavaScript Frontend Controller

class AttendanceApp {
    constructor() {
        // Elements
        this.video = document.getElementById('cameraVideo');
        this.canvas = document.getElementById('cameraCanvas');
        this.regVideo = document.getElementById('regCameraVideo');
        this.regCanvas = document.getElementById('regCameraCanvas');
        
        this.ctx = this.canvas ? this.canvas.getContext('2d') : null;
        this.regCtx = this.regCanvas ? this.regCanvas.getContext('2d') : null;

        // Streams and timers
        this.stream = null;
        this.regStream = null;
        this.recognitionInterval = null;
        this.isRecognizing = false;
        this.isCapturingRegistration = false;

        // Sound Synthesizer
        this.audioCtx = null;

        // Attendance state
        this.todayAttendance = [];
        this.recentlyMarkedIds = new Set();

        this.init();
    }

    init() {
        this.initAudio();
        this.initClock();
        this.initTabs();
        this.initModals();
        this.initEventListeners();
        this.loadDashboardStats();
        this.loadTodayAttendance();
        this.loadRegisteredStudents();

        // Auto start camera if on Attendance tab
        this.startAttendanceCamera();
    }

    initAudio() {
        try {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            if (AudioContext) {
                this.audioCtx = new AudioContext();
            }
        } catch (e) {
            console.warn('AudioContext not supported', e);
        }
    }

    playChime(type = 'success') {
        if (!this.audioCtx) return;
        if (this.audioCtx.state === 'suspended') {
            this.audioCtx.resume();
        }

        const now = this.audioCtx.currentTime;
        const osc = this.audioCtx.createOscillator();
        const gain = this.audioCtx.createGain();

        osc.connect(gain);
        gain.connect(this.audioCtx.destination);

        if (type === 'success') {
            osc.frequency.setValueAtTime(587.33, now); // D5
            osc.frequency.setValueAtTime(880.00, now + 0.1); // A5
            gain.gain.setValueAtTime(0.2, now);
            gain.gain.exponentialRampToValueAtTime(0.01, now + 0.35);
            osc.start(now);
            osc.stop(now + 0.35);
        } else if (type === 'snap') {
            osc.type = 'triangle';
            osc.frequency.setValueAtTime(1200, now);
            gain.gain.setValueAtTime(0.15, now);
            gain.gain.exponentialRampToValueAtTime(0.01, now + 0.08);
            osc.start(now);
            osc.stop(now + 0.08);
        }
    }

    initClock() {
        const updateClock = () => {
            const now = new Date();
            const timeStr = now.toLocaleTimeString('en-US', { hour12: false });
            const dateStr = now.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
            
            const liveClock = document.getElementById('liveClock');
            const liveDate = document.getElementById('liveDate');
            if (liveClock) liveClock.textContent = timeStr;
            if (liveDate) liveDate.textContent = dateStr;
        };
        updateClock();
        setInterval(updateClock, 1000);
    }

    initTabs() {
        const tabBtns = document.querySelectorAll('.tab-btn');
        tabBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                tabBtns.forEach(b => b.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

                btn.classList.add('active');
                const targetTab = document.getElementById(btn.dataset.tab);
                if (targetTab) targetTab.classList.add('active');

                // Handle Camera Streams when switching tabs
                if (btn.dataset.tab === 'tab-attendance') {
                    this.stopRegistrationCamera();
                    this.startAttendanceCamera();
                } else if (btn.dataset.tab === 'tab-register') {
                    this.stopAttendanceCamera();
                    this.startRegistrationCamera();
                } else {
                    this.stopAttendanceCamera();
                    this.stopRegistrationCamera();
                }

                if (btn.dataset.tab === 'tab-students') {
                    this.loadRegisteredStudents();
                }
            });
        });
    }

    initModals() {
        // Train Modal
        const btnTrain = document.getElementById('btnOpenTrainModal');
        const modalTrain = document.getElementById('modalTrain');
        const btnCloseTrain = document.getElementById('btnCloseTrain');
        const btnCancelTrain = document.getElementById('btnCancelTrain');
        const formTrain = document.getElementById('formTrainModel');

        if (btnTrain) btnTrain.onclick = () => modalTrain.classList.add('active');
        if (btnCloseTrain) btnCloseTrain.onclick = () => modalTrain.classList.remove('active');
        if (btnCancelTrain) btnCancelTrain.onclick = () => modalTrain.classList.remove('active');

        if (formTrain) {
            formTrain.onsubmit = async (e) => {
                e.preventDefault();
                const password = document.getElementById('trainPassword').value;
                await this.trainModel(password);
                modalTrain.classList.remove('active');
                document.getElementById('trainPassword').value = '';
            };
        }

        // Change Password Modal
        const btnPassword = document.getElementById('btnOpenPasswordModal');
        const modalPassword = document.getElementById('modalPassword');
        const btnClosePassword = document.getElementById('btnClosePassword');
        const btnCancelPassword = document.getElementById('btnCancelPassword');
        const formPassword = document.getElementById('formChangePassword');

        if (btnPassword) btnPassword.onclick = () => modalPassword.classList.add('active');
        if (btnClosePassword) btnClosePassword.onclick = () => modalPassword.classList.remove('active');
        if (btnCancelPassword) btnCancelPassword.onclick = () => modalPassword.classList.remove('active');

        if (formPassword) {
            formPassword.onsubmit = async (e) => {
                e.preventDefault();
                const oldPass = document.getElementById('oldPassword').value;
                const newPass = document.getElementById('newPassword').value;
                const confirmPass = document.getElementById('confirmPassword').value;

                if (newPass !== confirmPass) {
                    this.showToast('New passwords do not match!', 'error');
                    return;
                }

                await this.changePassword(oldPass, newPass);
                modalPassword.classList.remove('active');
                formPassword.reset();
            };
        }
    }

    initEventListeners() {
        // Attendance Camera Controls
        const btnToggleRecognition = document.getElementById('btnToggleRecognition');
        if (btnToggleRecognition) {
            btnToggleRecognition.onclick = () => {
                if (this.isRecognizing) {
                    this.pauseRecognition();
                    btnToggleRecognition.innerHTML = '<span class="icon">▶</span> Start Recognition';
                    btnToggleRecognition.className = 'btn btn-primary';
                } else {
                    this.startRecognitionLoop();
                    btnToggleRecognition.innerHTML = '<span class="icon">⏸</span> Pause Recognition';
                    btnToggleRecognition.className = 'btn btn-secondary';
                }
            };
        }

        // Registration form submit
        const formRegister = document.getElementById('formRegisterStudent');
        if (formRegister) {
            formRegister.onsubmit = (e) => {
                e.preventDefault();
                this.startRegistrationCapture();
            };
        }

        // History Date Picker
        const historyDateInput = document.getElementById('historyDate');
        if (historyDateInput) {
            // Set default date to today YYYY-MM-DD
            const today = new Date().toISOString().split('T')[0];
            historyDateInput.value = today;
            historyDateInput.onchange = () => this.loadHistoryAttendance(historyDateInput.value);
            const btnFetchHistory = document.getElementById('btnFetchHistory');
            if (btnFetchHistory) {
                btnFetchHistory.onclick = () => this.loadHistoryAttendance(historyDateInput.value);
            }
        }

        // Export Today CSV button
        const btnExportToday = document.getElementById('btnExportToday');
        if (btnExportToday) {
            btnExportToday.onclick = () => {
                window.open('/api/attendance/export/today', '_blank');
            };
        }

        // Export History CSV button
        const btnExportHistory = document.getElementById('btnExportHistory');
        if (btnExportHistory) {
            btnExportHistory.onclick = () => {
                const dateVal = document.getElementById('historyDate').value;
                if (!dateVal) return;
                // convert YYYY-MM-DD to DD-MM-YYYY
                const parts = dateVal.split('-');
                const formatted = `${parts[2]}-${parts[1]}-${parts[0]}`;
                window.open(`/api/attendance/export/${formatted}`, '_blank');
            };
        }

        // Attendance Table Search
        const searchInput = document.getElementById('searchAttendance');
        if (searchInput) {
            searchInput.oninput = () => {
                const query = searchInput.value.toLowerCase();
                const rows = document.querySelectorAll('#todayAttendanceBody tr');
                rows.forEach(row => {
                    const text = row.textContent.toLowerCase();
                    row.style.display = text.includes(query) ? '' : 'none';
                });
            };
        }
    }

    // Camera Management
    async startAttendanceCamera() {
        try {
            if (!this.stream) {
                this.stream = await navigator.mediaDevices.getUserMedia({
                    video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' }
                });
                if (this.video) {
                    this.video.srcObject = this.stream;
                    await this.video.play();
                }
            }
            this.startRecognitionLoop();
        } catch (err) {
            console.error('Camera error:', err);
            this.showToast('Unable to access webcam. Please allow camera permissions.', 'error');
            const statusEl = document.getElementById('cameraStatus');
            if (statusEl) statusEl.textContent = 'Camera Disconnected';
        }
    }

    stopAttendanceCamera() {
        this.pauseRecognition();
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
            this.stream = null;
        }
        if (this.video) {
            this.video.srcObject = null;
        }
    }

    async startRegistrationCamera() {
        try {
            if (!this.regStream) {
                this.regStream = await navigator.mediaDevices.getUserMedia({
                    video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' }
                });
                if (this.regVideo) {
                    this.regVideo.srcObject = this.regStream;
                    await this.regVideo.play();
                }
            }
        } catch (err) {
            console.error('Reg camera error:', err);
            this.showToast('Unable to access webcam for registration.', 'error');
        }
    }

    stopRegistrationCamera() {
        this.isCapturingRegistration = false;
        if (this.regStream) {
            this.regStream.getTracks().forEach(track => track.stop());
            this.regStream = null;
        }
        if (this.regVideo) {
            this.regVideo.srcObject = null;
        }
    }

    // Recognition Loop
    startRecognitionLoop() {
        if (this.recognitionInterval) clearInterval(this.recognitionInterval);
        this.isRecognizing = true;
        const banner = document.getElementById('recognitionBanner');
        if (banner) {
            banner.className = 'recognition-banner';
            banner.innerHTML = '<span class="live-indicator"></span> Live Face Recognition Active';
        }

        // Process a frame every 400ms
        this.recognitionInterval = setInterval(() => {
            if (this.isRecognizing && this.video && this.video.readyState === 4) {
                this.processAttendanceFrame();
            }
        }, 400);
    }

    pauseRecognition() {
        this.isRecognizing = false;
        if (this.recognitionInterval) {
            clearInterval(this.recognitionInterval);
            this.recognitionInterval = null;
        }
        if (this.ctx && this.canvas) {
            this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        }
        const banner = document.getElementById('recognitionBanner');
        if (banner) {
            banner.className = 'recognition-banner warning';
            banner.innerHTML = '⏸ Recognition Paused';
        }
    }

    async processAttendanceFrame() {
        if (!this.video || this.video.videoWidth === 0) return;

        // Match canvas dimensions to video
        if (this.canvas.width !== this.video.videoWidth || this.canvas.height !== this.video.videoHeight) {
            this.canvas.width = this.video.videoWidth;
            this.canvas.height = this.video.videoHeight;
        }

        // Capture frame to temporary offscreen canvas
        const tempCanvas = document.createElement('canvas');
        tempCanvas.width = this.video.videoWidth;
        tempCanvas.height = this.video.videoHeight;
        const tempCtx = tempCanvas.getContext('2d');
        tempCtx.drawImage(this.video, 0, 0, tempCanvas.width, tempCanvas.height);

        const frameBase64 = tempCanvas.toDataURL('image/jpeg', 0.85);

        try {
            const res = await fetch('/api/recognize_frame', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ frame: frameBase64 })
            });
            const data = await res.json();

            // Clear previous overlays
            this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

            if (data.status === 'success' && data.faces && data.faces.length > 0) {
                data.faces.forEach(face => {
                    const { x, y, w, h, name, id, recognized, marked, message } = face;

                    // Draw bounding box
                    this.ctx.lineWidth = 3;
                    if (marked) {
                        this.ctx.strokeStyle = '#2ea043'; // Green for marked
                    } else if (recognized) {
                        this.ctx.strokeStyle = '#58a6ff'; // Blue for recognized
                    } else {
                        this.ctx.strokeStyle = '#d29922'; // Yellow/Orange for unknown
                    }
                    this.ctx.strokeRect(x, y, w, h);

                    // Draw tag background
                    this.ctx.fillStyle = marked ? 'rgba(46, 160, 67, 0.85)' : (recognized ? 'rgba(88, 166, 255, 0.85)' : 'rgba(210, 153, 34, 0.85)');
                    const text = recognized ? `${name} (${id})` : 'Unknown Face';
                    this.ctx.font = 'bold 14px Inter, sans-serif';
                    const textWidth = this.ctx.measureText(text).width;
                    this.ctx.fillRect(x, Math.max(0, y - 24), textWidth + 16, 24);

                    // Draw tag text
                    this.ctx.fillStyle = '#ffffff';
                    this.ctx.fillText(text, x + 8, Math.max(16, y - 7));

                    // Handle attendance logging event
                    if (marked) {
                        this.playChime('success');
                        this.showToast(`Attendance marked for ${name} (${id})!`, 'success');
                        this.loadTodayAttendance();
                        this.loadDashboardStats();

                        const banner = document.getElementById('recognitionBanner');
                        if (banner) {
                            banner.className = 'recognition-banner success';
                            banner.innerHTML = `✅ Attendance Marked: ${name} (${id})`;
                            setTimeout(() => {
                                if (this.isRecognizing) {
                                    banner.className = 'recognition-banner';
                                    banner.innerHTML = '<span class="live-indicator"></span> Live Face Recognition Active';
                                }
                            }, 3500);
                        }
                    }
                });
            }
        } catch (err) {
            console.error('Frame recognition error:', err);
        }
    }

    // Student Registration Capture Sequence
    async startRegistrationCapture() {
        const id = document.getElementById('regStudentId').value.trim();
        const name = document.getElementById('regStudentName').value.trim();

        if (!id || !name) {
            this.showToast('Please enter both Student ID and Name', 'error');
            return;
        }

        if (!this.regVideo || !this.regStream) {
            this.showToast('Webcam is not available for registration. Starting camera...', 'info');
            await this.startRegistrationCamera();
        }

        this.isCapturingRegistration = true;
        const btnStart = document.getElementById('btnStartCapture');
        if (btnStart) {
            btnStart.disabled = true;
            btnStart.innerHTML = '<span class="spinner"></span> Capturing Samples...';
        }

        const progressBar = document.getElementById('regProgressBar');
        const progressCount = document.getElementById('regProgressCount');
        const guideText = document.getElementById('regGuideText');

        let samplesCollected = 0;
        const totalSamples = 50;

        if (guideText) guideText.textContent = 'Please look at the camera and slightly tilt your face for varied angles...';

        const captureInterval = setInterval(async () => {
            if (!this.isCapturingRegistration || samplesCollected >= totalSamples) {
                clearInterval(captureInterval);
                if (btnStart) {
                    btnStart.disabled = false;
                    btnStart.innerHTML = 'Capture Faces & Register';
                }
                return;
            }

            if (!this.regVideo || this.regVideo.readyState !== 4) return;

            // Capture frame
            const tempCanvas = document.createElement('canvas');
            tempCanvas.width = this.regVideo.videoWidth;
            tempCanvas.height = this.regVideo.videoHeight;
            const tempCtx = tempCanvas.getContext('2d');
            tempCtx.drawImage(this.regVideo, 0, 0, tempCanvas.width, tempCanvas.height);

            const frameBase64 = tempCanvas.toDataURL('image/jpeg', 0.85);

            try {
                const res = await fetch('/api/register_frame', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        student_id: id,
                        student_name: name,
                        sample_num: samplesCollected + 1,
                        total_samples: totalSamples,
                        frame: frameBase64
                    })
                });

                const data = await res.json();
                if (data.status === 'success' && data.face_detected) {
                    samplesCollected++;
                    this.playChime('snap');

                    const pct = Math.round((samplesCollected / totalSamples) * 100);
                    if (progressBar) progressBar.style.width = `${pct}%`;
                    if (progressCount) progressCount.textContent = `${samplesCollected} / ${totalSamples} samples (${pct}%)`;

                    if (samplesCollected >= totalSamples) {
                        this.isCapturingRegistration = false;
                        clearInterval(captureInterval);
                        if (guideText) guideText.textContent = '✅ All 50 face samples captured successfully! Click "Save Profile / Train Model" to finalize.';
                        this.showToast(`Registration completed for ${name}! Please train model now.`, 'success');
                        this.loadDashboardStats();
                        this.loadRegisteredStudents();
                        
                        // Switch to train prompt
                        setTimeout(() => {
                            const modalTrain = document.getElementById('modalTrain');
                            if (modalTrain) modalTrain.classList.add('active');
                        }, 1000);
                    }
                }
            } catch (err) {
                console.error('Registration sample capture error:', err);
            }
        }, 180);
    }

    // Train Model
    async trainModel(password) {
        this.showToast('Training LBPH Face Recognizer model... Please wait.', 'info');
        const trainBtn = document.getElementById('btnOpenTrainModal');
        if (trainBtn) trainBtn.disabled = true;

        try {
            const res = await fetch('/api/train', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password })
            });
            const data = await res.json();

            if (data.status === 'success') {
                this.showToast(data.message || 'Model trained and profile saved successfully!', 'success');
                this.playChime('success');
                this.loadDashboardStats();
            } else {
                this.showToast(data.message || 'Failed to train model.', 'error');
            }
        } catch (err) {
            console.error('Train error:', err);
            this.showToast('Server error while training model.', 'error');
        } finally {
            if (trainBtn) trainBtn.disabled = false;
        }
    }

    // Change Password
    async changePassword(oldPassword, newPassword) {
        try {
            const res = await fetch('/api/change-password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ old_password: oldPassword, new_password: newPassword })
            });
            const data = await res.json();

            if (data.status === 'success') {
                this.showToast('Password changed successfully!', 'success');
            } else {
                this.showToast(data.message || 'Error changing password', 'error');
            }
        } catch (err) {
            console.error('Password change error:', err);
            this.showToast('Failed to connect to server.', 'error');
        }
    }

    // Load Dashboard Stats
    async loadDashboardStats() {
        try {
            const res = await fetch('/api/stats');
            const data = await res.json();

            if (data.status === 'success') {
                const elReg = document.getElementById('statTotalRegistered');
                const elToday = document.getElementById('statAttendanceToday');
                const elModel = document.getElementById('statModelStatus');
                const elModelBadge = document.getElementById('modelStatusBadge');

                if (elReg) elReg.textContent = data.total_registered;
                if (elToday) elToday.textContent = data.total_today_attendance;
                if (elModel) elModel.textContent = data.model_trained ? 'Trained & Ready' : 'Untrained';
                if (elModelBadge) {
                    elModelBadge.className = data.model_trained ? 'badge badge-success' : 'badge badge-warning';
                    elModelBadge.textContent = data.model_trained ? '● Model Ready' : '● Needs Training';
                }
            }
        } catch (err) {
            console.error('Stats error:', err);
        }
    }

    // Load Today's Attendance Table
    async loadTodayAttendance() {
        try {
            const res = await fetch('/api/attendance/today');
            const data = await res.json();

            const tbody = document.getElementById('todayAttendanceBody');
            if (!tbody) return;

            if (data.status === 'success' && data.attendance && data.attendance.length > 0) {
                tbody.innerHTML = '';
                data.attendance.slice().reverse().forEach((row, idx) => {
                    const tr = document.createElement('tr');
                    if (idx === 0) tr.classList.add('new-row');
                    tr.innerHTML = `
                        <td><strong>${row.id || row.Id || '-'}</strong></td>
                        <td>${row.name || row.Name || '-'}</td>
                        <td>${row.date || row.Date || '-'}</td>
                        <td><span class="badge badge-blue">${row.time || row.Time || '-'}</span></td>
                    `;
                    tbody.appendChild(tr);
                });
            } else {
                tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-secondary); padding: 2rem;">No attendance recorded for today yet.</td></tr>`;
            }
        } catch (err) {
            console.error('Today attendance load error:', err);
        }
    }

    // Load History Attendance
    async loadHistoryAttendance(dateVal) {
        if (!dateVal) return;
        const parts = dateVal.split('-');
        const formattedDate = `${parts[2]}-${parts[1]}-${parts[0]}`;

        try {
            const res = await fetch(`/api/attendance/history?date=${formattedDate}`);
            const data = await res.json();

            const tbody = document.getElementById('historyAttendanceBody');
            const historyTitle = document.getElementById('historyDateDisplay');
            if (historyTitle) historyTitle.textContent = `Date: ${formattedDate}`;

            if (!tbody) return;

            if (data.status === 'success' && data.attendance && data.attendance.length > 0) {
                tbody.innerHTML = '';
                data.attendance.forEach(row => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td><strong>${row.id || row.Id || '-'}</strong></td>
                        <td>${row.name || row.Name || '-'}</td>
                        <td>${row.date || row.Date || '-'}</td>
                        <td><span class="badge badge-blue">${row.time || row.Time || '-'}</span></td>
                    `;
                    tbody.appendChild(tr);
                });
            } else {
                tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-secondary); padding: 2rem;">No attendance logs found for ${formattedDate}.</td></tr>`;
            }
        } catch (err) {
            console.error('History load error:', err);
        }
    }

    // Load Registered Students
    async loadRegisteredStudents() {
        try {
            const res = await fetch('/api/students');
            const data = await res.json();

            const tbody = document.getElementById('studentsListBody');
            if (!tbody) return;

            if (data.status === 'success' && data.students && data.students.length > 0) {
                tbody.innerHTML = '';
                data.students.forEach(s => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td>#${s.serial}</td>
                        <td><strong>${s.id}</strong></td>
                        <td>${s.name}</td>
                        <td><span class="badge badge-success">Enrolled</span></td>
                    `;
                    tbody.appendChild(tr);
                });
            } else {
                tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-secondary); padding: 2rem;">No students registered yet.</td></tr>`;
            }
        } catch (err) {
            console.error('Students load error:', err);
        }
    }

    // Toast Notifications
    showToast(message, type = 'info') {
        const container = document.getElementById('toastContainer');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        
        let icon = 'ℹ️';
        if (type === 'success') icon = '✅';
        if (type === 'error') icon = '❌';

        toast.innerHTML = `<span>${icon}</span> <span>${message}</span>`;
        container.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100%)';
            toast.style.transition = 'all 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, 3500);
    }
}

// Instantiate on DOM load
document.addEventListener('DOMContentLoaded', () => {
    window.app = new AttendanceApp();
});
