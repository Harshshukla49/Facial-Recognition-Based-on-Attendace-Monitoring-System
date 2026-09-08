// Autonomous Fullscreen Attendance Kiosk Controller

class AutonomousKioskController {
    constructor() {
        this.video = document.getElementById('kioskVideo');
        this.canvas = document.getElementById('kioskCanvas');
        this.ctx = this.canvas ? this.canvas.getContext('2d') : null;

        this.stream = null;
        this.scanInterval = null;
        this.audioCtx = null;
        this.lastFeedbackState = 'idle';
        this.resetTimer = null;

        this.init();
    }

    init() {
        this.initAudio();
        this.initClock();
        this.startKioskCamera();
        this.loadTickerEvents();
        setInterval(() => this.loadTickerEvents(), 5000);
    }

    initAudio() {
        try {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            if (AudioContext) this.audioCtx = new AudioContext();
        } catch (e) {
            console.warn('AudioContext not available');
        }
    }

    playSound(type = 'success') {
        if (!this.audioCtx) return;
        if (this.audioCtx.state === 'suspended') this.audioCtx.resume();

        const now = this.audioCtx.currentTime;
        const osc = this.audioCtx.createOscillator();
        const gain = this.audioCtx.createGain();
        osc.connect(gain);
        gain.connect(this.audioCtx.destination);

        if (type === 'success') {
            // Pleasant double chime
            osc.frequency.setValueAtTime(523.25, now); // C5
            osc.frequency.setValueAtTime(659.25, now + 0.12); // E5
            osc.frequency.setValueAtTime(783.99, now + 0.24); // G5
            gain.gain.setValueAtTime(0.25, now);
            gain.gain.exponentialRampToValueAtTime(0.01, now + 0.45);
            osc.start(now);
            osc.stop(now + 0.45);
        } else if (type === 'already') {
            // Soft notification tone
            osc.frequency.setValueAtTime(440, now);
            osc.frequency.setValueAtTime(554.37, now + 0.1);
            gain.gain.setValueAtTime(0.2, now);
            gain.gain.exponentialRampToValueAtTime(0.01, now + 0.3);
            osc.start(now);
            osc.stop(now + 0.3);
        } else if (type === 'error') {
            // Buzz warning
            osc.type = 'sawtooth';
            osc.frequency.setValueAtTime(200, now);
            osc.frequency.setValueAtTime(160, now + 0.15);
            gain.gain.setValueAtTime(0.3, now);
            gain.gain.exponentialRampToValueAtTime(0.01, now + 0.35);
            osc.start(now);
            osc.stop(now + 0.35);
        }
    }

    initClock() {
        const update = () => {
            const now = new Date();
            const timeStr = now.toLocaleTimeString('en-US', { hour12: true });
            const dateStr = now.toLocaleDateString('en-GB', { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' });
            
            const timeEl = document.getElementById('kioskClock');
            const dateEl = document.getElementById('kioskDate');
            if (timeEl) timeEl.textContent = timeStr;
            if (dateEl) dateEl.textContent = dateStr;
        };
        update();
        setInterval(update, 1000);
    }

    async startKioskCamera() {
        try {
            this.stream = await navigator.mediaDevices.getUserMedia({
                video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' }
            });
            if (this.video) {
                this.video.srcObject = this.stream;
                await this.video.play();
            }
            this.startScanningLoop();
        } catch (err) {
            console.error('Kiosk camera error:', err);
            this.setFeedbackCard('error', 'Camera Error', 'Please enable camera permissions on this kiosk.', '🚫 NO CAMERA');
        }
    }

    startScanningLoop() {
        if (this.scanInterval) clearInterval(this.scanInterval);
        this.scanInterval = setInterval(() => {
            if (this.video && this.video.readyState === 4) {
                this.processKioskFrame();
            }
        }, 360);
    }

    async processKioskFrame() {
        if (!this.video || this.video.videoWidth === 0) return;

        if (this.canvas.width !== this.video.videoWidth || this.canvas.height !== this.video.videoHeight) {
            this.canvas.width = this.video.videoWidth;
            this.canvas.height = this.video.videoHeight;
        }

        const off = document.createElement('canvas');
        off.width = this.video.videoWidth;
        off.height = this.video.videoHeight;
        const offCtx = off.getContext('2d');
        offCtx.drawImage(this.video, 0, 0);

        const frameBase64 = off.toDataURL('image/jpeg', 0.85);

        try {
            const res = await fetch('/api/ai/recognize_frame', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ frame: frameBase64, kiosk_id: 1 })
            });
            const data = await res.json();

            this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

            if (data.status === 'success' && data.faces && data.faces.length > 0) {
                const face = data.faces[0];
                const { x, y, w, h, is_matched, student_name, student_id, confidence, liveness, attendance } = face;

                // Draw HUD Bracket
                this.ctx.lineWidth = 4;
                if (!liveness.is_live) {
                    this.ctx.strokeStyle = '#ef4444';
                    this.setFeedbackCard('spoof', 'Liveness Verification Failed', 'Potential photo or digital screen spoof detected. Real person required.', '🚫 SPOOF DETECTED');
                    this.playSound('error');
                } else if (attendance.marked) {
                    this.ctx.strokeStyle = '#10b981';
                    this.setFeedbackCard('success', `Welcome, ${student_name} 👋`, `Student ID: ${student_id} • Marked at ${attendance.time || 'Now'}`, `✓ ${attendance.attendance_status || 'PRESENT'} RECORDED`);
                    this.playSound('success');
                    this.loadTickerEvents();
                } else if (attendance.status === 'already_marked') {
                    this.ctx.strokeStyle = '#3b82f6';
                    this.setFeedbackCard('already', `${student_name}`, `Attendance Already Marked (${attendance.attendance_status || 'PRESENT'}) for this session.`, 'ℹ️ ALREADY MARKED');
                    this.playSound('already');
                } else if (attendance.status === 'low_confidence') {
                    this.ctx.strokeStyle = '#f59e0b';
                    this.setFeedbackCard('low', 'Verification Required', `Confidence (${confidence}%) below 85% requirement. Please face the camera directly.`, '⚠ LOW CONFIDENCE');
                    this.playSound('error');
                } else if (!is_matched) {
                    this.ctx.strokeStyle = '#ef4444';
                    this.setFeedbackCard('unknown', 'Unknown Person', 'Face not recognized in institutional student database.', '❓ UNRECOGNIZED');
                }

                this.ctx.strokeRect(x, y, w, h);
            }
        } catch (err) {
            console.error('Kiosk scan error:', err);
        }
    }

    setFeedbackCard(type, title, subtitle, badgeText) {
        const card = document.getElementById('kioskFeedbackCard');
        const iconEl = document.getElementById('feedbackIcon');
        const titleEl = document.getElementById('feedbackTitle');
        const subEl = document.getElementById('feedbackSubtitle');
        const badgeEl = document.getElementById('feedbackBadge');

        if (!card) return;

        card.className = `feedback-card state-${type}`;
        if (titleEl) titleEl.textContent = title;
        if (subEl) subEl.textContent = subtitle;
        if (badgeEl) {
            badgeEl.textContent = badgeText;
            badgeEl.className = `feedback-badge badge-${type === 'success' ? 'success' : (type === 'already' ? 'already' : (type === 'low' ? 'amber' : 'danger'))}-kiosk`;
        }

        let icon = '👀';
        if (type === 'success') icon = '🎉';
        if (type === 'already') icon = '✅';
        if (type === 'low') icon = '⚠️';
        if (type === 'spoof') icon = '🚫';
        if (type === 'unknown') icon = '❓';
        if (iconEl) iconEl.textContent = icon;

        // Auto reset to idle after 4.5 seconds
        if (this.resetTimer) clearTimeout(this.resetTimer);
        this.resetTimer = setTimeout(() => {
            this.setIdleState();
        }, 4500);
    }

    setIdleState() {
        const card = document.getElementById('kioskFeedbackCard');
        const iconEl = document.getElementById('feedbackIcon');
        const titleEl = document.getElementById('feedbackTitle');
        const subEl = document.getElementById('feedbackSubtitle');
        const badgeEl = document.getElementById('feedbackBadge');

        if (!card) return;
        card.className = 'feedback-card state-idle';
        if (iconEl) iconEl.textContent = '👀';
        if (titleEl) titleEl.textContent = 'LOOK AT THE CAMERA';
        if (subEl) subEl.textContent = 'Stand within the scanning frame for automatic attendance.';
        if (badgeEl) {
            badgeEl.textContent = '● SYSTEM READY';
            badgeEl.className = 'feedback-badge badge-already-kiosk';
        }
    }

    async loadTickerEvents() {
        try {
            const res = await fetch('/api/recognition_events');
            const data = await res.json();
            const ticker = document.getElementById('kioskTickerContainer');
            if (!ticker) return;

            if (data.status === 'success' && data.events && data.events.length > 0) {
                ticker.innerHTML = '';
                data.events.slice(0, 6).forEach(ev => {
                    const span = document.createElement('span');
                    span.className = 'ticker-chip';
                    const timeStr = ev.timestamp ? ev.timestamp.split(' ')[1] : '';
                    span.innerHTML = `<strong>${ev.student_name || 'Visitor'}</strong>: ${ev.result} (${timeStr})`;
                    ticker.appendChild(span);
                });
            }
        } catch (err) {
            console.error('Ticker error:', err);
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.kiosk = new AutonomousKioskController();
});
