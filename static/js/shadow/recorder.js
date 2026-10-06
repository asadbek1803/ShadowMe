/**
 * Audio Recorder using MediaRecorder API.
 * Handles microphone permissions, recording, and blob generation.
 */

export class SegmentRecorder {
    constructor(options = {}) {
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.stream = null;
        this.isRecording = false;
        this.onDataAvailable = options.onDataAvailable || (() => {});
        this.onStart = options.onStart || (() => {});
        this.onStop = options.onStop || (() => {});
        this.onError = options.onError || (() => {});

        this.mimeType = this.getSupportedMimeType();
    }

    getSupportedMimeType() {
        const types = [
            'audio/webm;codecs=opus',
            'audio/webm',
            'audio/ogg;codecs=opus',
            'audio/mp4',
            'audio/wav'
        ];

        for (const type of types) {
            if (MediaRecorder.isTypeSupported(type)) {
                return type;
            }
        }
        return 'audio/webm'; // fallback
    }

    async start() {
        if (this.isRecording) return;

        try {
            // Request microphone access
            this.stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                    sampleRate: 48000
                }
            });

            this.mediaRecorder = new MediaRecorder(this.stream, {
                mimeType: this.mimeType
            });

            this.audioChunks = [];

            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.audioChunks.push(event.data);
                }
            };

            this.mediaRecorder.onstop = () => {
                const blob = new Blob(this.audioChunks, { type: this.mimeType });
                this.onDataAvailable(blob);
                this.onStop(blob);
            };

            this.mediaRecorder.onerror = (event) => {
                console.error('MediaRecorder error:', event.error);
                this.onError(event.error);
            };

            this.mediaRecorder.start(100); // Collect data every 100ms
            this.isRecording = true;
            this.onStart();

        } catch (error) {
            console.error('Recorder start error:', error);
            this.onError(error);
            throw error;
        }
    }

    stop() {
        if (this.mediaRecorder && this.isRecording) {
            this.mediaRecorder.stop();
            this.isRecording = false;

            // Stop all tracks to release microphone
            if (this.stream) {
                this.stream.getTracks().forEach(track => track.stop());
                this.stream = null;
            }
        }
    }

    pause() {
        if (this.mediaRecorder && this.isRecording && this.mediaRecorder.state === 'recording') {
            this.mediaRecorder.pause();
        }
    }

    resume() {
        if (this.mediaRecorder && this.isRecording && this.mediaRecorder.state === 'paused') {
            this.mediaRecorder.resume();
        }
    }

    getState() {
        return this.mediaRecorder ? this.mediaRecorder.state : 'inactive';
    }

    async getBlob() {
        return new Promise((resolve) => {
            if (this.audioChunks.length > 0) {
                resolve(new Blob(this.audioChunks, { type: this.mimeType }));
            } else {
                resolve(null);
            }
        });
    }

    destroy() {
        this.stop();
    }
}

/**
 * Permission helper
 */
export async function checkMicrophonePermission() {
    try {
        const permission = await navigator.permissions.query({ name: 'microphone' });
        return permission.state; // 'granted', 'denied', 'prompt'
    } catch {
        return 'prompt'; // Fallback
    }
}

export async function requestMicrophonePermission() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        stream.getTracks().forEach(track => track.stop());
        return true;
    } catch {
        return false;
    }
}