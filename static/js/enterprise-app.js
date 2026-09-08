// Enterprise AI Facial Recognition Attendance Platform - JavaScript Client Controller

class EnterpriseAttendancePlatform {
    constructor() {
        // Video and Canvas elements
        this.video = document.getElementById('hudCameraVideo');
        this.canvas = document.getElementById('hudCameraCanvas');
        this.ctx = this.canvas ? this.canvas.getContext('2d') : null;

        this.regVideo = document.getElementById('regVideo');
        this.regCanvas = document.getElementById('regCanvas');
        this.regCtx = this.regCanvas ? this.regCanvas.getContext('2d') : null;

        // Streams and state
        this.stream = null;
        this.regStream = null;
        this.recognitionInterval = null;
        this.isRecognizing = false;
        this.audioCtx = null;
        this.selectedRecordId = null;

        // Registration Wizard State
        this.wizardState = {
            studentId: '',
            studentName: '',
            deptId: 1,
            classId: 1,
            currentAngle: 'FRONTAL',
            angles: ['FRONTAL', 'LEFT_ANGLE', 'RIGHT_ANGLE', 'EXPRESSION'],
            angleIndex: 0,
            samplesPerAngle: 12,
            capturedCount: 0,
            isCapturing: false
        };

        this.init();
    }

    init() {
        this.initAudio();
        this.initClock();
        this.initNavigation();
        this.initModals();
        this.initAIAssistant();
        this.initRegistrationWizard();
        this.loadDashboardMetrics();
        this.loadTodayAttendance();
        this.loadSessions();
        this.loadStudents();
        this.loadCameras();
        this.loadAuditLogs();

        // Auto start camera if on Live Attendance tab
        this.startLiveCamera();
    }

    initAudio() {
        try {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            if (AudioContext) {
                this.audioCtx = new AudioContext();
            }
        } catch (e) {
            console.warn('AudioContext not supported');
        }
    }

    playSound(type = 'success') {
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
            osc.frequency.setValueAtTime(523.25, now); // C5
            osc.frequency.setValueAtTime(659.25, now + 0.1); // E5
            osc.frequency.setValueAtTime(783.99, now + 0.2); // G5
            gain.gain.setValueAtTime(0.2, now);
            gain.gain.exponentialRampToValueAtTime(0.01, now + 0.4);
            osc.start(now);
            osc.stop(now + 0.4);
        } else if (type === 'spoof') {
            osc.type = 'sawtooth';
            osc.frequency.setValueAtTime(220, now);
            osc.frequency.setValueAtTime(180, now + 0.15);
            gain.gain.setValueAtTime(0.3, now);
            gain.gain.exponentialRampToValueAtTime(0.01, now + 0.35);
            osc.start(now);
            osc.stop(now + 0.35);
        } else if (type === 'shutter') {
            osc.type = 'triangle';
            osc.frequency.setValueAtTime(1200, now);
            gain.gain.setValueAtTime(0.15, now);
            gain.gain.exponentialRampToValueAtTime(0.01, now + 0.08);
            osc.start(now);
            osc.stop(now + 0.08);
        }
    }

    initClock() {
        const update = () => {
            const now = new Date();
            const timeStr = now.toLocaleTimeString('en-US', { hour12: false });
            const dateStr = now.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
            
            const liveClock = document.getElementById('liveClockDisplay');
            const liveDate = document.getElementById('liveDateDisplay');
            if (liveClock) liveClock.textContent = timeStr;
            if (liveDate) liveDate.textContent = dateStr;
        };
        update();
        setInterval(update, 1000);
    }

    initNavigation() {
        const navLinks = document.querySelectorAll('.nav-link[data-tab]');
        navLinks.forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                navLinks.forEach(l => l.classList.remove('active'));
                document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

                link.classList.add('active');
                const targetId = link.dataset.tab;
                const targetPane = document.getElementById(targetId);
                if (targetPane) targetPane.classList.add('active');

                // Camera lifecycle
                if (targetId === 'tab-live-hud') {
                    this.stopRegCamera();
                    this.startLiveCamera();
                } else if (targetId === 'tab-face-wizard') {
                    this.stopLiveCamera();
                    this.startRegCamera();
                } else {
                    this.stopLiveCamera();
                    this.stopRegCamera();
                }

                // Data refreshes
                if (targetId === 'tab-analytics') this.loadAnalyticsPage();
                if (targetId === 'tab-students-list') this.loadStudents();
                if (targetId === 'tab-cameras-grid') this.loadCameras();
                if (targetId === 'tab-audit-logs') this.loadAuditLogs();
            });
        });

        // Search in attendance table
        const searchInput = document.getElementById('searchTodayTable');
        if (searchInput) {
            searchInput.addEventListener('input', () => {
                const q = searchInput.value.toLowerCase();
                document.querySelectorAll('#todayTableBody tr').forEach(tr => {
                    tr.style.display = tr.textContent.toLowerCase().includes(q) ? '' : 'none';
                });
            });
        }
    }

    initModals() {
        // Manual Override Modal
        const modalOverride = document.getElementById('modalOverride');
        const btnCloseOverride = document.getElementById('btnCloseOverride');
        const btnCancelOverride = document.getElementById('btnCancelOverride');
        const formOverride = document.getElementById('formOverrideAttendance');

        if (btnCloseOverride) btnCloseOverride.onclick = () => modalOverride.classList.remove('active');
        if (btnCancelOverride) btnCancelOverride.onclick = () => modalOverride.classList.remove('active');

        if (formOverride) {
            formOverride.onsubmit = async (e) => {
                e.preventDefault();
                if (!this.selectedRecordId) return;

                const newStatus = document.getElementById('overrideStatus').value;
                const reason = document.getElementById('overrideReason').value.trim();

                if (!reason) {
                    this.showToast('Please enter a valid reason for manual correction', 'error');
                    return;
                }

                try {
                    const res = await fetch('/api/attendance/override', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            record_id: this.selectedRecordId,
                            new_status: newStatus,
                            reason: reason
                        })
                    });
                    const data = await res.json();
                    if (data.status === 'success') {
                        this.showToast(data.message, 'success');
                        modalOverride.classList.remove('active');
                        this.loadTodayAttendance();
                        this.loadDashboardMetrics();
                    } else {
                        this.showToast(data.message || 'Error updating record', 'error');
                    }
                } catch (err) {
                    this.showToast('Server error while saving correction', 'error');
                }
            };
        }

        // Start Session Modal
        const modalSession = document.getElementById('modalStartSession');
        const btnOpenStartSession = document.getElementById('btnOpenStartSession');
        const btnCloseSession = document.getElementById('btnCloseSession');
        const btnCancelSession = document.getElementById('btnCancelSession');
        const formSession = document.getElementById('formStartSession');

        if (btnOpenStartSession) btnOpenStartSession.onclick = () => modalSession.classList.add('active');
        if (btnCloseSession) btnCloseSession.onclick = () => modalSession.classList.remove('active');
        if (btnCancelSession) btnCancelSession.onclick = () => modalSession.classList.remove('active');

        if (formSession) {
            formSession.onsubmit = async (e) => {
                e.preventDefault();
                const subj = document.getElementById('sessionSubject').value.trim();
                const room = document.getElementById('sessionRoom').value.trim();
                const grace = document.getElementById('sessionGrace').value;
                const late = document.getElementById('sessionLateCutoff').value;

                try {
                    const res = await fetch('/api/sessions/start', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            subject_name: subj,
                            room_number: room,
                            grace_period_mins: parseInt(grace),
                            late_cutoff_mins: parseInt(late)
                        })
                    });
                    const data = await res.json();
                    if (data.status === 'success') {
                        this.showToast(data.message, 'success');
                        modalSession.classList.remove('active');
                        this.loadSessions();
                    }
                } catch (err) {
                    this.showToast('Failed to start session', 'error');
                }
            };
        }
    }

    // -------------------------------------------------------------
    // LIVE CAMERA & AI RECOGNITION HUD
    // -------------------------------------------------------------
    async startLiveCamera() {
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
            this.startHUDLoop();
        } catch (err) {
            console.error('Camera access error:', err);
            this.showToast('Camera permission required for Live Attendance HUD', 'error');
        }
    }

    stopLiveCamera() {
        this.isRecognizing = false;
        if (this.recognitionInterval) {
            clearInterval(this.recognitionInterval);
            this.recognitionInterval = null;
        }
        if (this.stream) {
            this.stream.getTracks().forEach(t => t.stop());
            this.stream = null;
        }
        if (this.video) this.video.srcObject = null;
    }

    startHUDLoop() {
        if (this.recognitionInterval) clearInterval(this.recognitionInterval);
        this.isRecognizing = true;

        this.recognitionInterval = setInterval(() => {
            if (this.isRecognizing && this.video && this.video.readyState === 4) {
                this.processHUDFrame();
            }
        }, 380);
    }

    async processHUDFrame() {
        if (!this.video || this.video.videoWidth === 0) return;

        if (this.canvas.width !== this.video.videoWidth || this.canvas.height !== this.video.videoHeight) {
            this.canvas.width = this.video.videoWidth;
            this.canvas.height = this.video.videoHeight;
        }

        const offCanvas = document.createElement('canvas');
        offCanvas.width = this.video.videoWidth;
        offCanvas.height = this.video.videoHeight;
        const offCtx = offCanvas.getContext('2d');
        offCtx.drawImage(this.video, 0, 0);

        const frameBase64 = offCanvas.toDataURL('image/jpeg', 0.85);

        try {
            const res = await fetch('/api/ai/recognize_frame', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ frame: frameBase64 })
            });
            const data = await res.json();

            this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

            if (data.status === 'success' && data.faces && data.faces.length > 0) {
                data.faces.forEach(face => {
                    const { x, y, w, h, is_matched, student_name, student_id, confidence, liveness, attendance } = face;

                    // Bounding Box Style based on recognition & liveness
                    this.ctx.lineWidth = 3;
                    if (!liveness.is_live) {
                        this.ctx.strokeStyle = '#ef4444'; // Red for spoof
                        this.playSound('spoof');
                    } else if (attendance.marked) {
                        this.ctx.strokeStyle = '#10b981'; // Green for marked
                    } else if (is_matched) {
                        this.ctx.strokeStyle = '#3b82f6'; // Blue for recognized
                    } else {
                        this.ctx.strokeStyle = '#f59e0b'; // Amber for unknown
                    }

                    // Render futuristic HUD corner brackets
                    this.drawHUDCorners(x, y, w, h);

                    // Tag background
                    const labelText = is_matched ? `${student_name} (${student_id}) • ${confidence}%` : 'Unknown Person • Review';
                    this.ctx.font = 'bold 13px Inter, sans-serif';
                    const textWidth = this.ctx.measureText(labelText).width;

                    this.ctx.fillStyle = liveness.is_live ? (is_matched ? 'rgba(59, 130, 246, 0.9)' : 'rgba(245, 158, 11, 0.9)') : 'rgba(239, 68, 68, 0.9)';
                    this.ctx.fillRect(x, Math.max(0, y - 28), textWidth + 20, 26);

                    // Tag text
                    this.ctx.fillStyle = '#ffffff';
                    this.ctx.fillText(labelText, x + 8, Math.max(18, y - 10));

                    // Liveness sub-tag
                    const livenessText = liveness.is_live ? '✓ Real Person' : '⚠ Spoof Alert';
                    this.ctx.fillStyle = liveness.is_live ? '#10b981' : '#ef4444';
                    this.ctx.fillText(livenessText, x + 4, y + h + 18);

                    // Handle attendance marked event
                    if (attendance.marked) {
                        this.playSound('success');
                        this.showToast(`Attendance marked for ${student_name}! (${attendance.status})`, 'success');
                        this.loadTodayAttendance();
                        this.loadDashboardMetrics();

                        const banner = document.getElementById('hudRecognitionBanner');
                        if (banner) {
                            banner.className = 'hud-recognition-banner verified';
                            banner.innerHTML = `✅ ${student_name} (${student_id}) • ${attendance.status} Recorded`;
                            setTimeout(() => {
                                banner.className = 'hud-recognition-banner';
                                banner.innerHTML = '● Live Face Recognition & Liveness Active';
                            }, 4000);
                        }
                    }
                });
            }
        } catch (err) {
            console.error('Frame error:', err);
        }
    }

    drawHUDCorners(x, y, w, h) {
        const lineLen = Math.min(20, w / 4);
        this.ctx.beginPath();
        // Top-left
        this.ctx.moveTo(x, y + lineLen); this.ctx.lineTo(x, y); this.ctx.lineTo(x + lineLen, y);
        // Top-right
        this.ctx.moveTo(x + w - lineLen, y); this.ctx.lineTo(x + w, y); this.ctx.lineTo(x + w, y + lineLen);
        // Bottom-left
        this.ctx.moveTo(x, y + h - lineLen); this.ctx.lineTo(x, y + h); this.ctx.lineTo(x + lineLen, y + h);
        // Bottom-right
        this.ctx.moveTo(x + w - lineLen, y + h); this.ctx.lineTo(x + w, y + h); this.ctx.lineTo(x + w, y + h - lineLen);
        this.ctx.stroke();
    }

    // -------------------------------------------------------------
    // MULTI-ANGLE FACE REGISTRATION WIZARD
    // -------------------------------------------------------------
    initRegistrationWizard() {
        const btnStartWizard = document.getElementById('btnStartRegWizard');
        if (btnStartWizard) {
            btnStartWizard.onclick = () => this.startWizardCapture();
        }
    }

    async startRegCamera() {
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
            console.error('Wizard camera error:', err);
        }
    }

    stopRegCamera() {
        this.wizardState.isCapturing = false;
        if (this.regStream) {
            this.regStream.getTracks().forEach(t => t.stop());
            this.regStream = null;
        }
        if (this.regVideo) this.regVideo.srcObject = null;
    }

    async startWizardCapture() {
        const id = document.getElementById('regWizardId').value.trim();
        const name = document.getElementById('regWizardName').value.trim();

        if (!id || !name) {
            this.showToast('Please enter both Student ID and Full Name', 'error');
            return;
        }

        this.wizardState.studentId = id;
        this.wizardState.studentName = name;
        this.wizardState.capturedCount = 0;
        this.wizardState.angleIndex = 0;
        this.wizardState.isCapturing = true;

        const btn = document.getElementById('btnStartRegWizard');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = 'Capturing Multi-Angle Biometrics...';
        }

        const progressBar = document.getElementById('wizardProgressBar');
        const statusText = document.getElementById('wizardStatusText');
        const totalTarget = this.wizardState.angles.length * this.wizardState.samplesPerAngle; // 48 samples

        const captureLoop = setInterval(async () => {
            if (!this.wizardState.isCapturing || this.wizardState.capturedCount >= totalTarget) {
                clearInterval(captureLoop);
                if (this.wizardState.capturedCount >= totalTarget) {
                    await this.finalizeEnrollment();
                }
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = 'Start Multi-Angle Capture Wizard';
                }
                return;
            }

            if (!this.regVideo || this.regVideo.readyState !== 4) return;

            const angle = this.wizardState.angles[this.wizardState.angleIndex];
            if (statusText) {
                const readableAngle = angle.replace('_', ' ');
                statusText.textContent = `Capturing [${readableAngle}]: Look towards the camera and follow instructions...`;
            }

            const off = document.createElement('canvas');
            off.width = this.regVideo.videoWidth;
            off.height = this.regVideo.videoHeight;
            const offCtx = off.getContext('2d');
            offCtx.drawImage(this.regVideo, 0, 0);

            const frame = off.toDataURL('image/jpeg', 0.85);

            try {
                const res = await fetch('/api/ai/register_sample', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        student_id: id,
                        student_name: name,
                        angle_type: angle,
                        sample_num: this.wizardState.capturedCount + 1,
                        frame: frame
                    })
                });

                const data = await res.json();
                
                if (res.status === 409 || data.status === 'duplicate_face_detected') {
                    this.wizardState.isCapturing = false;
                    clearInterval(captureLoop);
                    this.playSound('spoof');
                    if (statusText) {
                        statusText.innerHTML = `<span style="color: #ef4444; font-weight: 700;">${data.message}</span>`;
                    }
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = 'Restart Registration';
                    }
                    this.showToast(data.message, 'error');
                    return;
                }

                if (data.code === 'MULTIPLE_FACES_DETECTED') {
                    if (statusText) statusText.innerHTML = `<span style="color: #f59e0b;">⚠ Multiple faces detected. Exactly ONE person must be in view.</span>`;
                    return;
                }

                if (data.code === 'NO_FACE_DETECTED') {
                    if (statusText) statusText.innerHTML = `<span style="color: #9ca3af;">👀 Position face inside camera view...</span>`;
                    return;
                }

                if (data.status === 'success' && data.face_detected && data.quality_passed) {
                    this.wizardState.capturedCount++;
                    this.playSound('shutter');

                    const pct = Math.round((this.wizardState.capturedCount / totalTarget) * 100);
                    if (progressBar) progressBar.style.width = `${pct}%`;

                    // Move to next angle every 12 samples
                    if (this.wizardState.capturedCount % this.wizardState.samplesPerAngle === 0) {
                        this.wizardState.angleIndex = Math.min(
                            this.wizardState.angles.length - 1, 
                            this.wizardState.angleIndex + 1
                        );
                    }
                }
            } catch (err) {
                console.error('Wizard capture error:', err);
            }
        }, 220);
    }

    async finalizeEnrollment() {
        this.showToast('Generating AES-256 Encrypted Biometric Master Template...', 'info');
        try {
            const res = await fetch('/api/ai/train_biometrics', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ student_id: this.wizardState.studentId })
            });
            const data = await res.json();

            if (data.status === 'success') {
                this.playSound('success');
                this.showToast(data.message, 'success');
                const statusText = document.getElementById('wizardStatusText');
                if (statusText) statusText.textContent = `✅ Enrollment Complete: ${this.wizardState.studentName} is now active in biometric database!`;
                this.loadDashboardMetrics();
                this.loadStudents();
            }
        } catch (err) {
            this.showToast('Biometric template generation failed', 'error');
        }
    }

    // -------------------------------------------------------------
    // GROUNDED AI ATTENDANCE ASSISTANT
    // -------------------------------------------------------------
    initAIAssistant() {
        const btnOpen = document.getElementById('btnToggleAssistant');
        const btnClose = document.getElementById('btnCloseAssistant');
        const drawer = document.getElementById('aiAssistantDrawer');
        const form = document.getElementById('formAssistantChat');
        const input = document.getElementById('assistantInput');

        if (btnOpen && drawer) {
            btnOpen.onclick = () => drawer.classList.toggle('active');
        }
        if (btnClose && drawer) {
            btnClose.onclick = () => drawer.classList.remove('active');
        }

        // Quick prompt chips
        document.querySelectorAll('.prompt-chip').forEach(chip => {
            chip.onclick = () => {
                if (input) {
                    input.value = chip.dataset.prompt;
                    if (form) form.dispatchEvent(new Event('submit'));
                }
            };
        });

        if (form && input) {
            form.onsubmit = async (e) => {
                e.preventDefault();
                const text = input.value.trim();
                if (!text) return;

                this.appendChatMessage(text, 'user');
                input.value = '';

                // Show typing loader
                const loader = this.appendChatMessage('Analyzing database facts...', 'ai');

                try {
                    const res = await fetch('/api/assistant/query', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ prompt: text })
                    });
                    const data = await res.json();

                    loader.remove();
                    if (data.status === 'success') {
                        this.appendChatMessage(data.answer, 'ai', true);
                    } else {
                        this.appendChatMessage('Sorry, I encountered an issue querying the database.', 'ai');
                    }
                } catch (err) {
                    loader.remove();
                    this.appendChatMessage('Network connection error.', 'ai');
                }
            };
        }
    }

    appendChatMessage(text, sender = 'ai', isMarkdown = false) {
        const container = document.getElementById('assistantMessages');
        if (!container) return null;

        const bubble = document.createElement('div');
        bubble.className = `chat-bubble bubble-${sender}`;

        if (isMarkdown) {
            // Render basic bold and lists
            let html = text
                .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                .replace(/`(.*?)`/g, '<code style="background: rgba(255,255,255,0.1); padding: 2px 4px; border-radius: 4px;">$1</code>')
                .replace(/\n\n/g, '<br><br>')
                .replace(/- /g, '&bull; ');
            bubble.innerHTML = html;
        } else {
            bubble.textContent = text;
        }

        container.appendChild(bubble);
        container.scrollTop = container.scrollHeight;
        return bubble;
    }

    // -------------------------------------------------------------
    // DATA LOADERS & TABLES
    // -------------------------------------------------------------
    async loadDashboardMetrics() {
        try {
            const res = await fetch('/api/stats/overview');
            const data = await res.json();

            if (data.status === 'success') {
                const d = data.data;
                this.setText('kpiTotalStudents', d.total_students);
                this.setText('kpiPresentToday', d.present_today);
                this.setText('kpiLateToday', d.late_today);
                this.setText('kpiAbsentToday', d.absent_today);
                this.setText('kpiAttendanceRate', `${d.attendance_rate_percent}%`);
                this.setText('kpiLowAttendance', d.low_attendance_count);
                this.setText('kpiOnlineCameras', d.online_cameras);
                this.setText('kpiBiometrics', d.biometrics_enrolled);
            }
        } catch (err) {
            console.error('Metrics error:', err);
        }
    }

    async loadTodayAttendance() {
        try {
            const res = await fetch('/api/attendance/records');
            const data = await res.json();

            const tbody = document.getElementById('todayTableBody');
            if (!tbody) return;

            if (data.status === 'success' && data.records && data.records.length > 0) {
                tbody.innerHTML = '';
                data.records.forEach((r, idx) => {
                    const tr = document.createElement('tr');
                    const badgeClass = r.status === 'PRESENT' ? 'badge-present' : (r.status === 'LATE' ? 'badge-late' : 'badge-halfday');
                    
                    tr.innerHTML = `
                        <td><strong>${r.student_id}</strong></td>
                        <td>${r.student_name || 'Student'}</td>
                        <td>${r.class_name || 'General'}</td>
                        <td><span class="status-badge ${badgeClass}">${r.status}</span></td>
                        <td>${r.time}</td>
                        <td>${r.confidence ? r.confidence.toFixed(1) + '%' : '98.0%'}</td>
                        <td>
                            <button class="btn btn-secondary btn-sm" onclick="window.app.openOverrideModal(${r.id}, '${r.status}', '${r.student_name}')">
                                ✏️ Correct
                            </button>
                        </td>
                    `;
                    tbody.appendChild(tr);
                });
            } else {
                tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-dim); padding: 2rem;">No attendance records registered today yet.</td></tr>`;
            }
        } catch (err) {
            console.error('Attendance load error:', err);
        }
    }

    openOverrideModal(recordId, currentStatus, studentName) {
        this.selectedRecordId = recordId;
        const modal = document.getElementById('modalOverride');
        const title = document.getElementById('overrideStudentTitle');
        const statusSelect = document.getElementById('overrideStatus');
        const reasonInput = document.getElementById('overrideReason');

        if (title) title.textContent = `Manual Correction: ${studentName}`;
        if (statusSelect) statusSelect.value = currentStatus;
        if (reasonInput) reasonInput.value = '';

        if (modal) modal.classList.add('active');
    }

    async loadSessions() {
        try {
            const res = await fetch('/api/sessions');
            const data = await res.json();
            const container = document.getElementById('sessionsListContainer');
            if (!container) return;

            if (data.status === 'success' && data.sessions && data.sessions.length > 0) {
                container.innerHTML = '';
                data.sessions.forEach(s => {
                    const div = document.createElement('div');
                    div.className = 'panel-card';
                    div.style.marginBottom = '1rem';
                    div.innerHTML = `
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <h3 style="font-size: 1rem; color: #fff;">${s.subject_name}</h3>
                                <p style="font-size: 0.8rem; color: var(--text-muted);">${s.class_name || 'Classroom'} &bull; ${s.room_number}</p>
                            </div>
                            <div>
                                <span class="status-badge ${s.status === 'ACTIVE' ? 'badge-present' : 'badge-halfday'}">${s.status}</span>
                            </div>
                        </div>
                        <div style="display: flex; gap: 1.5rem; font-size: 0.8rem; color: var(--text-dim); margin-top: 0.85rem;">
                            <span>🕒 Time: ${s.scheduled_start} - ${s.scheduled_end}</span>
                            <span>⏱ Grace Period: ${s.grace_period_mins}m</span>
                            <span>⏳ Late Cutoff: ${s.late_cutoff_mins}m</span>
                        </div>
                    `;
                    container.appendChild(div);
                });
            }
        } catch (err) {
            console.error('Sessions error:', err);
        }
    }

    async loadStudents() {
        try {
            const res = await fetch('/api/students');
            const data = await res.json();
            const tbody = document.getElementById('studentsDirectoryBody');
            if (!tbody) return;

            if (data.status === 'success' && data.students) {
                tbody.innerHTML = '';
                data.students.forEach(s => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td><strong>${s.student_id}</strong></td>
                        <td>${s.full_name}</td>
                        <td>${s.department_name || 'Engineering'}</td>
                        <td>${s.class_name || 'B.Tech CSE'}</td>
                        <td><span class="status-badge ${s.has_biometrics ? 'badge-present' : 'badge-late'}">${s.has_biometrics ? '✓ Enrolled' : 'Pending'}</span></td>
                    `;
                    tbody.appendChild(tr);
                });
            }
        } catch (err) {
            console.error('Students error:', err);
        }
    }

    async loadCameras() {
        try {
            const res = await fetch('/api/cameras');
            const data = await res.json();
            const grid = document.getElementById('camerasGridContainer');
            if (!grid) return;

            if (data.status === 'success' && data.cameras) {
                grid.innerHTML = '';
                data.cameras.forEach(c => {
                    const card = document.createElement('div');
                    card.className = 'kpi-card';
                    card.innerHTML = `
                        <div>
                            <h3 style="font-size: 0.95rem; color: #fff; margin-bottom: 0.2rem;">${c.name}</h3>
                            <p style="font-size: 0.78rem; color: var(--text-dim); font-weight: normal;">${c.location}</p>
                            <span style="font-size: 0.72rem; color: var(--text-muted); display: block; margin-top: 0.5rem;">${c.ip_stream_url || 'Local Video Stream'}</span>
                        </div>
                        <div>
                            <span class="status-badge ${c.status === 'ONLINE' ? 'badge-present' : 'badge-absent'}">● ${c.status}</span>
                        </div>
                    `;
                    grid.appendChild(card);
                });
            }
        } catch (err) {
            console.error('Cameras error:', err);
        }
    }

    async loadAuditLogs() {
        try {
            const res = await fetch('/api/audit/logs');
            const data = await res.json();
            const tbody = document.getElementById('auditLogsBody');
            if (!tbody) return;

            if (data.status === 'success' && data.logs) {
                tbody.innerHTML = '';
                data.logs.forEach(l => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td><code style="color: #3b82f6;">${l.action}</code></td>
                        <td>${l.user_name || 'System'}</td>
                        <td>${l.resource_type} (#${l.resource_id})</td>
                        <td style="font-size: 0.78rem; color: var(--text-dim);">${l.new_value || '-'}</td>
                        <td>${l.timestamp}</td>
                    `;
                    tbody.appendChild(tr);
                });
            }
        } catch (err) {
            console.error('Audit error:', err);
        }
    }

    async loadAnalyticsPage() {
        try {
            const res = await fetch('/api/analytics/low_attendance');
            const data = await res.json();
            const tbody = document.getElementById('lowAttendanceTableBody');
            if (!tbody) return;

            if (data.status === 'success' && data.students) {
                tbody.innerHTML = '';
                data.students.forEach(s => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td><strong>${s.student_id}</strong></td>
                        <td>${s.name}</td>
                        <td>${s.class_name}</td>
                        <td><strong style="color: #ef4444;">${s.percentage}%</strong></td>
                        <td>${s.attended_days} / ${s.total_days} Days</td>
                        <td><span class="status-badge badge-absent">Deficit: -${s.deficit}%</span></td>
                    `;
                    tbody.appendChild(tr);
                });
            }
        } catch (err) {
            console.error('Analytics load error:', err);
        }
    }

    // -------------------------------------------------------------
    // HELPERS & TOASTS
    // -------------------------------------------------------------
    setText(id, text) {
        const el = document.getElementById(id);
        if (el) el.textContent = text;
    }

    showToast(message, type = 'info') {
        const container = document.getElementById('toastNotificationArea');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `hud-pill`;
        toast.style.cssText = `
            background: rgba(18, 23, 34, 0.95);
            border: 1px solid ${type === 'success' ? '#10b981' : (type === 'error' ? '#ef4444' : '#3b82f6')};
            padding: 0.85rem 1.25rem;
            border-radius: 12px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.6);
            margin-bottom: 0.5rem;
            display: flex;
            align-items: center;
            gap: 0.75rem;
            color: #fff;
            animation: fadeInTab 0.3s ease;
        `;

        const icon = type === 'success' ? '✅' : (type === 'error' ? '❌' : 'ℹ️');
        toast.innerHTML = `<span>${icon}</span> <span>${message}</span>`;
        container.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transition = 'opacity 0.3s';
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.app = new EnterpriseAttendancePlatform();
});
