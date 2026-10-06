/**
 * Video Player with Karaoke Sync.
 * Supports YouTube (iframe API) and HTML5 video.
 * Word-by-word highlighting using words_json timestamps.
 */

export class VideoPlayer {
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        this.sourceType = options.sourceType || 'html5'; // 'youtube' or 'html5'
        this.videoUrl = options.videoUrl || '';
        this.segments = options.segments || [];
        this.words = options.words || [];
        this.language = options.language || 'en';

        this.player = null;
        this.currentWordIndex = -1;
        this.currentSegmentIndex = -1;
        this.karaokeElement = null;
        this.onTimeUpdate = options.onTimeUpdate || (() => {});
        this.onSegmentEnd = options.onSegmentEnd || (() => {});
        this.onReady = options.onReady || (() => {});

        this.isPlaying = false;
        this.lastHighlightTime = 0;
    }

    async init() {
        if (this.sourceType === 'youtube') {
            await this.initYouTube();
        } else {
            this.initHTML5();
        }
    }

    initHTML5() {
        const video = document.createElement('video');
        video.src = this.videoUrl;
        video.controls = true;
        video.preload = 'metadata';
        video.crossOrigin = 'anonymous';

        this.container.innerHTML = '';
        this.container.appendChild(video);

        this.player = video;

        video.addEventListener('timeupdate', () => this.handleTimeUpdate());
        video.addEventListener('ended', () => this.handleEnded());
        video.addEventListener('loadedmetadata', () => this.onReady());
        video.addEventListener('error', (e) => console.error('Video error:', e));
    }

    async initYouTube() {
        // Load YouTube IFrame API
        if (!window.YT || !window.YT.Player) {
            await this.loadYouTubeAPI();
        }

        // Extract video ID from URL
        const videoId = this.extractYouTubeId(this.videoUrl);
        if (!videoId) throw new Error('Invalid YouTube URL');

        this.container.innerHTML = '<div id="yt-player"></div>';

        this.player = new YT.Player('yt-player', {
            videoId: videoId,
            playerVars: {
                controls: 1,
                modestbranding: 1,
                rel: 0,
                playsinline: 1
            },
            events: {
                onReady: (e) => {
                    this.onReady();
                    this.setupYTTimeUpdate();
                },
                onStateChange: (e) => {
                    if (e.data === YT.PlayerState.ENDED) this.handleEnded();
                }
            }
        });
    }

    loadYouTubeAPI() {
        return new Promise((resolve) => {
            if (window.YT && window.YT.Player) return resolve();

            // If script is already added but not ready yet, just wait for the callback
            if (window.YT && !window.YT.Player) {
                const oldCallback = window.onYouTubeIframeAPIReady;
                window.onYouTubeIframeAPIReady = () => {
                    if (oldCallback) oldCallback();
                    resolve();
                };
                return;
            }

            const tag = document.createElement('script');
            tag.src = 'https://www.youtube.com/iframe_api';
            const firstScriptTag = document.getElementsByTagName('script')[0];
            if (firstScriptTag) {
                firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);
            } else {
                document.head.appendChild(tag);
            }

            window.onYouTubeIframeAPIReady = () => resolve();
        });
    }

    extractYouTubeId(url) {
        const regExp = /^.*(youtu.be\/|v\/|u\/\w\/|embed\/|watch\?v=|&v=)([^#&?]*).*/;
        const match = url.match(regExp);
        return (match && match[2].length === 11) ? match[2] : null;
    }

    setupYTTimeUpdate() {
        // Poll current time every 100ms for YouTube
        this.ytPollInterval = setInterval(() => {
            if (this.player && this.player.getCurrentTime) {
                this.handleTimeUpdate(this.player.getCurrentTime());
            }
        }, 100);
    }

    getCurrentTime() {
        if (this.sourceType === 'youtube' && this.player && this.player.getCurrentTime) {
            return this.player.getCurrentTime();
        }
        if (this.player) return this.player.currentTime;
        return 0;
    }

    getDuration() {
        if (this.sourceType === 'youtube' && this.player && this.player.getDuration) {
            return this.player.getDuration();
        }
        if (this.player) return this.player.duration;
        return 0;
    }

    play() {
        if (this.player) {
            if (this.sourceType === 'youtube') {
                this.player.playVideo();
            } else {
                this.player.play();
            }
            this.isPlaying = true;
        }
    }

    pause() {
        if (this.player) {
            if (this.sourceType === 'youtube') {
                this.player.pauseVideo();
            } else {
                this.player.pause();
            }
            this.isPlaying = false;
        }
    }

    seekTo(seconds) {
        if (this.player) {
            if (this.sourceType === 'youtube') {
                this.player.seekTo(seconds, true);
            } else {
                this.player.currentTime = seconds;
            }
        }
    }

    playSegment(segmentIndex) {
        const segment = this.segments[segmentIndex];
        if (!segment) return;

        this.seekTo(segment.start);
        this.play();

        // Auto-pause at segment end
        if (this.checkEndInterval) {
            clearInterval(this.checkEndInterval);
        }
        
        this.checkEndInterval = setInterval(() => {
            const currentTime = this.getCurrentTime();
            if (currentTime >= segment.end) {
                this.pause();
                clearInterval(this.checkEndInterval);
                this.checkEndInterval = null;
                this.onSegmentEnd(segmentIndex);
            }
        }, 100);
    }

    handleTimeUpdate(currentTime = null) {
        const time = currentTime !== null ? currentTime : this.getCurrentTime();
        this.onTimeUpdate(time);
        this.updateKaraokeHighlight(time);
    }

    handleEnded() {
        this.isPlaying = false;
    }

    updateKaraokeHighlight(currentTime) {
        // Find current word based on time
        let wordIndex = -1;
        let segmentIndex = -1;

        for (let i = 0; i < this.words.length; i++) {
            const word = this.words[i];
            if (currentTime >= word.start && currentTime <= word.end) {
                wordIndex = i;
                segmentIndex = word.segment_id;
                break;
            }
        }

        if (wordIndex !== this.currentWordIndex) {
            this.currentWordIndex = wordIndex;
            this.highlightWord(wordIndex);
        }

        if (segmentIndex !== this.currentSegmentIndex && segmentIndex >= 0) {
            this.highlightSegment(segmentIndex);
        }
    }

    highlightWord(wordIndex) {
        if (!this.karaokeElement) return;

        const wordElements = this.karaokeElement.querySelectorAll('.karaoke-word');
        wordElements.forEach((el) => {
            const idx = parseInt(el.dataset.index);
            el.classList.toggle('active', idx === wordIndex);
            if (idx < wordIndex) {
                el.classList.add('passed');
            } else {
                el.classList.remove('passed');
            }
        });
    }

    highlightSegment(segmentIndex) {
        if (this.currentSegmentIndex !== segmentIndex) {
            this.currentSegmentIndex = segmentIndex;
            this.renderKaraokeText();
        }
    }

    setKaraokeElement(element) {
        this.karaokeElement = element;
        this.renderKaraokeText();
    }

    renderKaraokeText() {
        if (!this.karaokeElement || this.words.length === 0) return;

        let targetSegment = this.currentSegmentIndex;
        if (targetSegment < 0) targetSegment = 0; // Default to first segment
        
        let html = '';
        for (let i = 0; i < this.words.length; i++) {
            const word = this.words[i];
            if (word.segment_id === targetSegment) {
                html += `<span class="karaoke-word" data-index="${i}">${word.word}</span> `;
            }
        }
        
        // Add a nice animation class when segment changes
        this.karaokeElement.classList.remove('segment-enter');
        void this.karaokeElement.offsetWidth; // trigger reflow
        this.karaokeElement.classList.add('segment-enter');
        
        this.karaokeElement.innerHTML = html;
        this.highlightWord(this.currentWordIndex);
    }

    setSegments(segments, words) {
        this.segments = segments;
        this.words = words;
        if (this.karaokeElement) this.renderKaraokeText();
    }

    destroy() {
        if (this.ytPollInterval) clearInterval(this.ytPollInterval);
        if (this.player) {
            if (this.sourceType === 'html5') {
                this.player.pause();
                this.player.src = '';
            }
        }
    }
}