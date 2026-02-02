"""
Yeelight Music Sync - Advanced Audio Visualization
Synchronizes your Yeelight LED Strip with system audio (YouTube, Spotify, etc.)

Features:
- Hann window for clean FFT analysis
- Spectral centroid & rolloff analysis  
- Beat detection with adaptive threshold
- Exponential smoothing for natural transitions
- HSV color space for fluid color flow
- Two automatic modes: EnergyPulse & SpectrumFlow
- WASAPI loopback for headphone support

Based on best practices from:
- cybre/yeelight-music-sync (Golang)
- yyjlincoln/Yeelight (Python)
- Leixb/yeelight (Rust)
"""
import socket
import json
import time
import numpy as np
import configparser
import os
from collections import deque

# ============ CONFIGURATION ============
# Load IP from config.ini
config = configparser.ConfigParser()
config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.ini')

if not os.path.exists(config_path):
    print("ERROR: config.ini not found!")
    print(f"Please copy config.ini.example to config.ini and set your Yeelight IP")
    print(f"Expected path: {config_path}")
    exit(1)

config.read(config_path)
LIGHT_IP = config.get('yeelight', 'light_ip', fallback='192.168.1.100')

LIGHT_PORT = 55443
MUSIC_PORT = 54321

# Audio Analysis
SAMPLE_RATE = 44100
CHUNK_SIZE = 2048
FFT_SIZE = CHUNK_SIZE

# Frequency Bands (Hz)
BASS_RANGE = (20, 250)
MID_RANGE = (250, 2000)
HIGH_RANGE = (2000, 8000)

# Beat Detection
BEAT_THRESHOLD = 1.35
MIN_BEAT_INTERVAL = 0.16  # seconds
ENERGY_HISTORY_SIZE = 48

# Smoothing (0-1, lower = smoother)
HUE_ALPHA = 0.08      # Very smooth hue transitions
SAT_ALPHA = 0.06      # Very smooth saturation
BRIGHT_ALPHA = 0.10   # Smooth brightness
BAND_ALPHA = 0.05     # Very smooth frequency bands

# Brightness Range (adjust to your preference)
MIN_BRIGHTNESS = 5
MAX_BRIGHTNESS = 25   # Set to 100 for full brightness

# =======================================

def get_local_ip():
    """Get local IP address for music server"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    finally:
        s.close()
    return ip

def hann_window(n):
    """Generate Hann window for FFT to reduce spectral leakage"""
    return 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(n) / (n - 1))

def clamp(value, min_val, max_val):
    """Clamp value between min and max"""
    return max(min_val, min(max_val, value))

def ema(prev, value, alpha):
    """Exponential Moving Average for smooth transitions"""
    return prev + alpha * (value - prev)

def smooth_hue(current, target, alpha):
    """Smooth hue transitions across 360 degree boundary"""
    delta = ((target - current + 540) % 360) - 180
    return (current + alpha * delta + 360) % 360

def spectral_balance(a, b):
    """Calculate balance between two frequency bands (-1 to 1)"""
    total = a + b
    if total < 1e-9:
        return 0
    return clamp((a - b) / total, -1, 1)


class AudioFeatures:
    """DSP feature extraction from audio frames"""
    
    def __init__(self, sample_rate, frame_size):
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self.window = hann_window(frame_size)
        self.freqs = np.fft.rfftfreq(frame_size, 1/sample_rate)
        self.band_width = sample_rate / frame_size
        
        # Precompute band indices for efficiency
        self.bass_mask = (self.freqs >= BASS_RANGE[0]) & (self.freqs < BASS_RANGE[1])
        self.mid_mask = (self.freqs >= MID_RANGE[0]) & (self.freqs < MID_RANGE[1])
        self.high_mask = (self.freqs >= HIGH_RANGE[0]) & (self.freqs < HIGH_RANGE[1])
    
    def process(self, audio):
        """Extract audio features from frame"""
        if len(audio) != self.frame_size:
            return None
        
        # Apply Hann window before FFT
        windowed = audio * self.window
        
        # FFT
        spectrum = np.fft.rfft(windowed)
        magnitudes = np.abs(spectrum)
        
        # RMS (root mean square) for volume
        rms = np.sqrt(np.mean(audio ** 2))
        
        # Band energies
        bass = np.sum(magnitudes[self.bass_mask] ** 2)
        mid = np.sum(magnitudes[self.mid_mask] ** 2)
        high = np.sum(magnitudes[self.high_mask] ** 2)
        total_energy = bass + mid + high + 1e-9
        
        # Normalized band energies (0-1)
        bass_norm = clamp(bass / total_energy, 0, 1)
        mid_norm = clamp(mid / total_energy, 0, 1)
        high_norm = clamp(high / total_energy, 0, 1)
        
        # Spectral centroid (indicates "brightness" of sound)
        mag_sum = np.sum(magnitudes) + 1e-9
        centroid = np.sum(self.freqs * magnitudes) / mag_sum
        centroid_norm = clamp(centroid / (self.sample_rate / 2), 0, 1)
        
        # Spectral rolloff (frequency below which 85% of energy exists)
        cumsum = np.cumsum(magnitudes ** 2)
        rolloff_idx = np.searchsorted(cumsum, 0.85 * total_energy)
        rolloff = self.freqs[min(rolloff_idx, len(self.freqs) - 1)]
        rolloff_norm = clamp(rolloff / (self.sample_rate / 2), 0, 1)
        
        # Peak frequency
        peak_idx = np.argmax(magnitudes)
        peak_freq = self.freqs[peak_idx]
        
        return {
            'rms': rms,
            'total_energy': total_energy,
            'bass': bass_norm,
            'mid': mid_norm,
            'high': high_norm,
            'centroid': centroid_norm,
            'rolloff': rolloff_norm,
            'peak_freq': peak_freq
        }


class BeatDetector:
    """Beat detection using energy comparison with adaptive threshold"""
    
    def __init__(self):
        self.energy_history = deque(maxlen=ENERGY_HISTORY_SIZE)
        self.last_beat_time = 0
        self.peak_energy = 0.01
        self.noise_floor = 0.001
    
    def detect(self, rms):
        """Detect beat in current frame. Returns (is_beat, beat_strength)"""
        now = time.time()
        
        # Update noise floor and peak (adaptive)
        self.noise_floor = ema(self.noise_floor, rms, 0.01)
        if rms > self.peak_energy:
            self.peak_energy = ema(self.peak_energy, rms, 0.34)
        else:
            self.peak_energy = ema(self.peak_energy, rms, 0.02)
        
        min_peak = self.noise_floor * 1.5
        if self.peak_energy < min_peak:
            self.peak_energy = min_peak
        
        # Add to history
        self.energy_history.append(rms)
        
        # Need enough history for comparison
        if len(self.energy_history) < ENERGY_HISTORY_SIZE // 2:
            return False, 0
        
        avg_energy = np.mean(self.energy_history)
        
        # Check beat conditions
        if now - self.last_beat_time < MIN_BEAT_INTERVAL:
            return False, 0
        
        threshold = BEAT_THRESHOLD * avg_energy
        if rms > threshold:
            self.last_beat_time = now
            overdrive = clamp((rms - threshold) / (self.peak_energy - threshold + 1e-9), 0, 1)
            return True, overdrive
        
        return False, 0


class PatternMode:
    """Lighting pattern modes"""
    ENERGY_PULSE = 0  # Beat-driven, high energy, reactive
    SPECTRUM_FLOW = 1  # Smooth color flow, ambient


class PatternAnalyzer:
    """Determine lighting mode based on audio characteristics"""
    
    def __init__(self):
        self.mode = PatternMode.ENERGY_PULSE
        self.last_mode_switch = 0
        self.intensity = 0
        self.beat_times = deque(maxlen=20)
        self.mode_hold_time = 2.5  # seconds before mode can switch
    
    def process(self, features, is_beat, beat_strength):
        """Analyze features and return pattern state"""
        now = time.time()
        
        if is_beat:
            self.beat_times.append(now)
        
        # Prune old beats
        cutoff = now - 2.0
        while self.beat_times and self.beat_times[0] < cutoff:
            self.beat_times.popleft()
        
        # Beat density (beats per second / 4, normalized 0-1)
        beat_density = clamp(len(self.beat_times) / 8.0, 0, 1)
        
        # Overall intensity/excitement level
        energy_norm = clamp(features['rms'] * 50, 0, 1)
        instant_intensity = clamp(
            0.65 * energy_norm + 
            0.25 * beat_density + 
            0.1 * features['centroid'],
            0, 1
        )
        self.intensity = ema(self.intensity, instant_intensity, 0.18)
        
        # Automatic mode switching based on audio characteristics
        if now - self.last_mode_switch > self.mode_hold_time:
            if self.mode == PatternMode.ENERGY_PULSE:
                # Switch to flow mode for high energy, bright sounds
                if energy_norm > 0.6 and features['centroid'] > 0.45:
                    self.mode = PatternMode.SPECTRUM_FLOW
                    self.last_mode_switch = now
            else:
                # Switch back to pulse mode for lower energy
                if energy_norm < 0.35 or features['centroid'] < 0.3:
                    self.mode = PatternMode.ENERGY_PULSE
                    self.last_mode_switch = now
        
        return {
            'mode': self.mode,
            'intensity': self.intensity,
            'beat_density': beat_density,
            'energy_norm': energy_norm
        }


class LEDController:
    """Drive Yeelight using analyzed audio features"""
    
    def __init__(self):
        self.hue = 0
        self.saturation = 50
        self.brightness = 50
        self.beat_pulse = 0
        
        # Smoothed band values
        self.bass = 0
        self.mid = 0
        self.high = 0
        self.centroid = 0
        self.rolloff = 0
        
        # Last sent values (avoid redundant commands)
        self.last_hsv = None
    
    def update(self, features, pattern, is_beat, beat_strength):
        """Calculate HSV values from audio features"""
        
        # Update beat pulse (decays over time)
        if is_beat:
            self.beat_pulse = clamp(beat_strength * 1.2, 0, 1)
        else:
            self.beat_pulse *= 0.88
        
        # Smooth band values using EMA
        self.bass = ema(self.bass, features['bass'], BAND_ALPHA)
        self.mid = ema(self.mid, features['mid'], BAND_ALPHA)
        self.high = ema(self.high, features['high'], BAND_ALPHA)
        self.centroid = ema(self.centroid, features['centroid'], 0.12)
        self.rolloff = ema(self.rolloff, features['rolloff'], 0.1)
        
        # Spectral balance for color decisions
        low_mid_balance = spectral_balance(self.bass, self.mid)
        mid_hi_balance = spectral_balance(self.mid, self.high)
        
        # Calculate target HSV based on current mode
        if pattern['mode'] == PatternMode.SPECTRUM_FLOW:
            target_hue = self._spectrum_flow_hue(mid_hi_balance)
            target_sat = self._spectrum_flow_sat(pattern['intensity'])
            target_bright = self._spectrum_flow_bright(pattern['intensity'])
        else:
            target_hue = self._energy_pulse_hue(low_mid_balance)
            target_sat = self._energy_pulse_sat(pattern)
            target_bright = self._energy_pulse_bright(pattern['intensity'])
        
        # Smooth transitions
        self.hue = smooth_hue(self.hue, target_hue, HUE_ALPHA)
        self.saturation = ema(self.saturation, target_sat, SAT_ALPHA)
        self.brightness = ema(self.brightness, target_bright, BRIGHT_ALPHA)
        
        return int(self.hue) % 360, int(self.saturation), int(self.brightness)
    
    def _energy_pulse_hue(self, low_mid_balance):
        """Hue for energy pulse mode - bass=warm, treble=cool"""
        base = 40 + 180 * self.centroid - 100 * self.bass + 60 * self.high
        pulse_shift = 20 * self.beat_pulse * (0.5 - low_mid_balance)
        return clamp(base + pulse_shift, 0, 359)
    
    def _energy_pulse_sat(self, pattern):
        """Saturation for energy pulse mode"""
        return clamp(38 + 42 * self.mid + 25 * self.high + 
                     20 * self.beat_pulse + 16 * pattern['beat_density'], 25, 100)
    
    def _energy_pulse_bright(self, intensity):
        """Brightness for energy pulse mode"""
        base = 28 + 62 * intensity
        pulse = 32 * self.beat_pulse
        sparkle = 26 * self.high
        return clamp(base + pulse + sparkle, MIN_BRIGHTNESS, MAX_BRIGHTNESS)
    
    def _spectrum_flow_hue(self, mid_hi_balance):
        """Hue for spectrum flow mode - smooth color transitions"""
        return clamp(210 * self.centroid + 40 * (self.rolloff - 0.5) + 
                     90 * (mid_hi_balance - 0.5) + 40, 0, 359)
    
    def _spectrum_flow_sat(self, intensity):
        """Saturation for spectrum flow mode"""
        return clamp(42 + 50 * self.mid + 18 * self.high + 12 * intensity, 28, 98)
    
    def _spectrum_flow_bright(self, intensity):
        """Brightness for spectrum flow mode"""
        return clamp(34 + 56 * intensity + 22 * self.high + 
                     12 * self.beat_pulse, MIN_BRIGHTNESS, MAX_BRIGHTNESS)


class YeelightMusicSync:
    """Main synchronization controller"""
    
    def __init__(self):
        self.local_ip = get_local_ip()
        self.running = False
        self.music_conn = None
        self.cmd_id = 1
        self.server = None
        self.last_command = 0
        self.min_command_interval = 0.06  # 60ms for smooth transitions
        
        # Components
        self.features = AudioFeatures(SAMPLE_RATE, CHUNK_SIZE)
        self.beat_detector = BeatDetector()
        self.pattern = PatternAnalyzer()
        self.led = LEDController()
        
    def enable_music_mode(self):
        """Start music server and tell light to connect"""
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(('0.0.0.0', MUSIC_PORT))
        self.server.listen(1)
        self.server.settimeout(30)
        
        print(f"Music server started on {self.local_ip}:{MUSIC_PORT}", flush=True)
        
        # Send set_music command to light
        cmd = json.dumps({'id': 1, 'method': 'set_music', 'params': [1, self.local_ip, MUSIC_PORT]})
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((LIGHT_IP, LIGHT_PORT))
        sock.send((cmd + '\r\n').encode())
        response = sock.recv(1024).decode()
        sock.close()
        
        if 'ok' not in response:
            print(f"Failed to enable music mode: {response}", flush=True)
            return False
        
        print("Waiting for light to connect...", flush=True)
        try:
            self.music_conn, addr = self.server.accept()
            print(f"Light connected from {addr}!", flush=True)
            return True
        except socket.timeout:
            print("Light did not connect (timeout)", flush=True)
            print("Check firewall settings - port 54321 TCP must be open", flush=True)
            return False
    
    def disable_music_mode(self):
        """Disable music mode and cleanup"""
        try:
            if self.music_conn:
                self.music_conn.close()
            if self.server:
                self.server.close()
        except:
            pass
        
        try:
            cmd = json.dumps({'id': 1, 'method': 'set_music', 'params': [0]})
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            sock.connect((LIGHT_IP, LIGHT_PORT))
            sock.send((cmd + '\r\n').encode())
            sock.recv(1024)
            sock.close()
        except:
            pass
        
        print("Music mode disabled", flush=True)
    
    def send_hsv(self, hue, sat, bright):
        """Send HSV command via music mode connection"""
        if not self.music_conn:
            return
        
        now = time.time()
        if now - self.last_command < self.min_command_interval:
            return
        
        try:
            # Use smooth transitions for natural flow
            cmd = json.dumps({
                'id': self.cmd_id,
                'method': 'set_hsv',
                'params': [hue, sat, 'smooth', 50]
            })
            self.music_conn.send((cmd + '\r\n').encode())
            self.cmd_id += 1
            
            cmd = json.dumps({
                'id': self.cmd_id,
                'method': 'set_bright',
                'params': [bright, 'smooth', 50]
            })
            self.music_conn.send((cmd + '\r\n').encode())
            self.cmd_id += 1
            
            self.last_command = now
        except Exception as e:
            print(f"Send error: {e}", flush=True)
            self.running = False
    
    def process_audio(self, audio_data):
        """Process audio frame and update light"""
        # Convert to mono float
        audio = np.frombuffer(audio_data, dtype=np.float32)
        
        # If stereo, convert to mono
        if len(audio) == CHUNK_SIZE * 2:
            audio = audio.reshape(-1, 2).mean(axis=1)
        
        if len(audio) < CHUNK_SIZE:
            return
        
        audio = audio[:CHUNK_SIZE]
        
        # Extract features
        feat = self.features.process(audio)
        if feat is None:
            return
        
        # Beat detection
        is_beat, beat_strength = self.beat_detector.detect(feat['rms'])
        
        # Pattern analysis
        pattern_state = self.pattern.process(feat, is_beat, beat_strength)
        
        # LED control
        hue, sat, bright = self.led.update(feat, pattern_state, is_beat, beat_strength)
        
        # Send to light
        self.send_hsv(hue, sat, bright)
        
        # Debug output on beats
        if int(time.time() * 2) % 2 == 0 and is_beat:
            mode_name = "SpectrumFlow" if pattern_state['mode'] == PatternMode.SPECTRUM_FLOW else "EnergyPulse"
            print(f"[{mode_name}] H:{hue:3d} S:{sat:3d} B:{bright:3d} | "
                  f"Bass:{feat['bass']:.2f} Mid:{feat['mid']:.2f} Hi:{feat['high']:.2f} | "
                  f"Beat! {beat_strength:.2f}", flush=True)
    
    def run(self):
        """Main run loop using PyAudioWPatch for WASAPI loopback"""
        try:
            import pyaudiowpatch as pyaudio
        except ImportError:
            print("ERROR: pyaudiowpatch not installed!", flush=True)
            print("Install it with: pip install pyaudiowpatch", flush=True)
            return
        
        print("=" * 60, flush=True)
        print("  YEELIGHT MUSIC SYNC - Advanced Audio Visualization", flush=True)
        print("=" * 60, flush=True)
        print(f"Light IP: {LIGHT_IP}", flush=True)
        print(f"Local IP: {self.local_ip}", flush=True)
        print(flush=True)
        
        p = pyaudio.PyAudio()
        
        # Find WASAPI loopback device (captures system audio including headphones)
        try:
            wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
        except Exception as e:
            print(f"ERROR: Could not find WASAPI device: {e}", flush=True)
            p.terminate()
            return
        
        print(f"Default output: {default_speakers['name']}", flush=True)
        
        # Find loopback device for the default output
        loopback_device = None
        for i in range(p.get_device_count()):
            dev = p.get_device_info_by_index(i)
            if dev.get('isLoopbackDevice', False):
                if default_speakers['name'] in dev['name']:
                    loopback_device = dev
                    break
        
        if not loopback_device:
            # Try to find any loopback device
            for i in range(p.get_device_count()):
                dev = p.get_device_info_by_index(i)
                if dev.get('isLoopbackDevice', False):
                    loopback_device = dev
                    break
        
        if not loopback_device:
            print("ERROR: No loopback device found!", flush=True)
            print("Make sure you have audio output active.", flush=True)
            p.terminate()
            return
        
        print(f"Loopback: {loopback_device['name']}", flush=True)
        print(flush=True)
        
        if not self.enable_music_mode():
            p.terminate()
            return
        
        self.running = True
        
        print(flush=True)
        print("[*] Advanced audio analysis active...", flush=True)
        print("    Features: Beat detection, Spectral analysis, Pattern modes", flush=True)
        print("    Press Ctrl+C to stop", flush=True)
        print(flush=True)
        
        # Update sample rate from device
        global SAMPLE_RATE
        SAMPLE_RATE = int(loopback_device['defaultSampleRate'])
        self.features = AudioFeatures(SAMPLE_RATE, CHUNK_SIZE)
        
        channels = min(2, loopback_device['maxInputChannels'])
        
        try:
            stream = p.open(
                format=pyaudio.paFloat32,
                channels=channels,
                rate=SAMPLE_RATE,
                input=True,
                input_device_index=loopback_device['index'],
                frames_per_buffer=CHUNK_SIZE
            )
            
            while self.running:
                try:
                    data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
                    self.process_audio(data)
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    print(f"Audio error: {e}", flush=True)
                    time.sleep(0.1)
            
            stream.stop_stream()
            stream.close()
            
        except KeyboardInterrupt:
            print("\nStopping...", flush=True)
        except Exception as e:
            print(f"Error: {e}", flush=True)
        finally:
            self.running = False
            p.terminate()
            self.disable_music_mode()


if __name__ == '__main__':
    sync = YeelightMusicSync()
    sync.run()

