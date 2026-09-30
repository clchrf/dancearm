"""
RobotDance — iOS Style UI + Serial 通訊 + 誇張動作版
"""

import os, time, threading, queue, tempfile, subprocess, warnings
from pathlib import Path
import numpy as np
import customtkinter as ctk
from tkinter import filedialog, messagebox
import matplotlib
matplotlib.use("TkAgg")
warnings.filterwarnings('ignore', message='.*Glyph.*missing from font.*')
matplotlib.rcParams['font.sans-serif'] = ['Helvetica Neue', 'Arial']
matplotlib.rcParams['axes.unicode_minus'] = False
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import librosa
import sounddevice as sd
import serial
import serial.tools.list_ports

# ── 座標範圍（步進數，調大讓動作誇張）────────────────────────────
X_MIN, X_MAX = -1600, 1600
Y_MIN, Y_MAX = -1600, 1600
Z_MIN, Z_MAX =     0, 2400
LERP_ALPHA   = 0.6      # 追隨速度，越大越直接
SAMPLE_RATE  = 22050
HOP_LENGTH   = 512
N_FFT        = 1024
CHUNK_SEC    = 0.05

# ── iOS 色彩 ──────────────────────────────────────────────────────
C_BG     = ("#F2F2F7", "#000000")
C_CARD   = ("#FFFFFF", "#1C1C1E")
C_INPUT  = ("#E5E5EA", "#2C2C2E")
C_PRI    = ("#000000", "#FFFFFF")
C_SEC    = ("#8E8E93", "#98989D")
C_BLUE   = ("#007AFF", "#0A84FF")
C_GREEN  = ("#34C759", "#30D158")
C_RED    = ("#FF3B30", "#FF453A")
C_ORANGE = ("#FF9500", "#FF9F0A")


# ═════════════════════════════════════════════════════════════════
class SerialManager:
    def __init__(self):
        self._s = None
        self._lock = threading.Lock()

    def connect(self, port, baud=115200):
        try:
            self._s = serial.Serial(port, baud, timeout=1)
            time.sleep(2)
            return True
        except Exception as e:
            print(f"[Serial] {e}")
            return False

    def disconnect(self):
        with self._lock:
            if self._s and self._s.is_open:
                self._s.close()

    def send(self, x, y, z):
        if not self.is_connected: return
        with self._lock:
            try:
                self._s.write(f"<{x},{y},{z}>\n".encode())
            except: pass

    @property
    def is_connected(self):
        return self._s is not None and self._s.is_open

    @staticmethod
    def list_ports():
        return [p.device for p in serial.tools.list_ports.comports()]


# ═════════════════════════════════════════════════════════════════
class AudioAnalyzer:
    def __init__(self, coord_queue, spectrum_cb=None):
        self.coord_queue  = coord_queue
        self.spectrum_cb  = spectrum_cb
        self.is_playing   = False
        self._stop        = threading.Event()
        self._audio       = None
        self._sr          = SAMPLE_RATE
        self._bpm         = 120.0
        self._beats       = None

    def load_file(self, path):
        try:
            y, sr = librosa.load(path, sr=SAMPLE_RATE, mono=True)
            self._audio = y; self._sr = sr
            tempo, beats = librosa.beat.beat_track(y=y, sr=sr, hop_length=HOP_LENGTH)
            self._bpm = float(tempo); self._beats = beats
            print(f"[Audio] BPM={self._bpm:.1f}")
            return True
        except Exception as e:
            print(f"[Audio] {e}"); return False

    def load_youtube(self, url, progress_cb=None):
        try:
            tmp = tempfile.mkdtemp()
            cmd = ["yt-dlp", "-x", "--audio-format", "mp3",
                   "--user-agent", "Mozilla/5.0",
                   "-o", os.path.join(tmp, "%(title)s.%(ext)s"),
                   "--no-playlist", url]
            if progress_cb: progress_cb("Downloading...")
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0: return False
            mp3 = list(Path(tmp).glob("*.mp3"))
            if not mp3: return False
            if progress_cb: progress_cb("Analyzing...")
            return self.load_file(str(mp3[0]))
        except Exception as e:
            print(f"[YT] {e}"); return False

    def play(self):
        if self._audio is None: return
        self._stop.clear(); self.is_playing = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._stop.set(); self.is_playing = False; sd.stop()

    def _loop(self):
        y, sr   = self._audio, self._sr
        chunk_n = int(sr * CHUNK_SEC)
        beats   = set(self._beats) if self._beats is not None else set()
        hist    = []
        sd.play(y, sr)

        for i in range(len(y) // chunk_n):
            if self._stop.is_set(): break
            chunk    = y[i*chunk_n:(i+1)*chunk_n]
            spec     = np.abs(librosa.stft(chunk, n_fft=N_FFT, hop_length=HOP_LENGTH))
            freqs    = librosa.fft_frequencies(sr=sr, n_fft=N_FFT)

            low_e  = float(np.mean(spec[freqs < 250]))
            mid_e  = float(np.mean(spec[(freqs >= 250) & (freqs < 4000)]))
            high_e = float(np.mean(spec[freqs >= 4000]))

            hist.append(low_e + mid_e + high_e)
            if len(hist) > 20: hist.pop(0)
            avg = max(np.mean(hist), 1e-6)

            def n(v): return float(np.tanh(v / avg * 1.5))

            nl, nm, nh = n(low_e), n(mid_e), n(high_e)
            fp      = librosa.time_to_frames(i*CHUNK_SEC, sr=sr, hop_length=HOP_LENGTH)
            on_beat = any(abs(fp - b) <= 2 for b in beats)

            # X：中高頻左右搖擺，方向交替
            x = X_MIN + (X_MAX-X_MIN) * (0.5 + 0.5*(nm*0.7+nh*0.3)*np.sign(np.sin(i*0.3)))
            # Y：高頻 × BPM 相位波
            ph = np.sin(2*np.pi*i*CHUNK_SEC*(self._bpm/60.0))
            yc = Y_MIN + (Y_MAX-Y_MIN) * (0.5 + 0.5*ph*max(nh, nm))
            # Z：節拍打底，非節拍跟低頻
            zc = Z_MIN if on_beat else (Z_MIN + (Z_MAX-Z_MIN)*nl)

            try:
                self.coord_queue.put_nowait((int(np.clip(x,X_MIN,X_MAX)),
                                            int(np.clip(yc,Y_MIN,Y_MAX)),
                                            int(np.clip(zc,Z_MIN,Z_MAX))))
            except queue.Full: pass

            if self.spectrum_cb:
                self.spectrum_cb(np.mean(spec, axis=1))

            time.sleep(max(0, CHUNK_SEC - 0.008))
        self.is_playing = False

    @property
    def bpm(self): return self._bpm


# ═════════════════════════════════════════════════════════════════
class RobotDanceApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("RobotDance")
        self.geometry("1200x800"); self.minsize(1000, 650)
        ctk.set_appearance_mode("light")
        self.configure(fg_color=C_BG)

        self.coord_queue = queue.Queue(maxsize=200)
        self.serial_mgr  = SerialManager()
        self.analyzer    = AudioAnalyzer(self.coord_queue, self._on_spectrum)
        self._smooth     = [0.0, 0.0, 0.0]

        self.grid_columnconfigure(0, weight=1, uniform="h")
        self.grid_columnconfigure(1, weight=1, uniform="h")
        self.grid_rowconfigure(0, weight=1)

        self._build_left()
        self._build_right()
        self._refresh_ports()
        threading.Thread(target=self._dispatch, daemon=True).start()

    # ── 工具 ──────────────────────────────────────────────────────
    def _card(self, parent, title):
        f = ctk.CTkFrame(parent, fg_color=C_CARD, corner_radius=16)
        f.pack(fill="x", pady=(0, 18))
        inner = ctk.CTkFrame(f, fg_color="transparent")
        inner.pack(fill="both", padx=20, pady=18)
        ctk.CTkLabel(inner, text=title, font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_SEC).pack(anchor="w", pady=(0, 12))
        return inner

    def _btn(self, parent, text, color, cmd, tc="white", **kw):
        return ctk.CTkButton(parent, text=text, fg_color=color, hover_color=color,
                             height=44, corner_radius=12, text_color=tc,
                             font=ctk.CTkFont(size=15, weight="bold"), command=cmd, **kw)

    # ── 左欄 ──────────────────────────────────────────────────────
    def _build_left(self):
        p = ctk.CTkFrame(self, fg_color="transparent")
        p.grid(row=0, column=0, sticky="nsew", padx=(36,18), pady=36)

        # 標題
        h = ctk.CTkFrame(p, fg_color="transparent")
        h.pack(fill="x", pady=(8, 26))
        ctk.CTkLabel(h, text="RobotDance",
                     font=ctk.CTkFont(size=40, weight="bold"), text_color=C_PRI).pack(anchor="w")
        ctk.CTkLabel(h, text="Kinetic Audio Sync Terminal",
                     font=ctk.CTkFont(size=15), text_color=C_SEC).pack(anchor="w", pady=(4,0))

        # 音訊來源
        src = self._card(p, "AUDIO SOURCE")
        self.url_entry = ctk.CTkEntry(src, placeholder_text="Paste YouTube URL...",
                                      height=42, fg_color=C_INPUT, border_width=0,
                                      corner_radius=10, text_color=C_PRI)
        self.url_entry.pack(fill="x", pady=(0,10))
        row = ctk.CTkFrame(src, fg_color="transparent"); row.pack(fill="x")
        self.btn_yt = self._btn(row, "Fetch YouTube", C_BLUE, self._yt)
        self.btn_yt.pack(side="left", expand=True, fill="x", padx=(0,8))
        self.btn_lo = self._btn(row, "Local File", C_INPUT, self._local, tc=C_PRI)
        self.btn_lo.pack(side="right", expand=True, fill="x")

        # Arduino 連線
        conn = self._card(p, "ARDUINO CONNECTION")
        self._port_menu = ctk.CTkOptionMenu(conn, values=[""],
                                            font=ctk.CTkFont(size=13), height=40,
                                            corner_radius=10, fg_color=C_INPUT,
                                            button_color=C_INPUT, text_color=C_PRI,
                                            dropdown_fg_color=C_CARD)
        self._port_menu.pack(fill="x", pady=(0,10))
        cr = ctk.CTkFrame(conn, fg_color="transparent"); cr.pack(fill="x")
        self.btn_conn = self._btn(cr, "Connect", C_GREEN, self._toggle_conn)
        self.btn_conn.pack(side="left", expand=True, fill="x", padx=(0,8))
        self._btn(cr, "Refresh", C_INPUT, self._refresh_ports, tc=C_SEC).pack(side="right", expand=True, fill="x")
        self._conn_lbl = ctk.CTkLabel(conn, text="Not connected",
                                      font=ctk.CTkFont(size=12), text_color=C_SEC)
        self._conn_lbl.pack(anchor="w", pady=(8,0))

        # 播放控制
        ctrl = self._card(p, "TRANSPORT")
        self.btn_play = self._btn(ctrl, "▶  Play", C_GREEN, self._play, state="disabled")
        self.btn_play.pack(fill="x", pady=(0,10))
        self.btn_stop = self._btn(ctrl, "■  Stop", C_RED, self._stop, state="disabled")
        self.btn_stop.pack(fill="x")

        # 外觀
        ap = self._card(p, "APPEARANCE")
        seg = ctk.CTkSegmentedButton(ap, values=["Dark","Light"],
                                     selected_color=C_BLUE, height=36,
                                     command=lambda m: ctk.set_appearance_mode(m))
        seg.set("Light"); seg.pack(fill="x")

    # ── 右欄 ──────────────────────────────────────────────────────
    def _build_right(self):
        p = ctk.CTkFrame(self, fg_color="transparent")
        p.grid(row=0, column=1, sticky="nsew", padx=(18,36), pady=36)

        g = ctk.CTkFrame(p, fg_color="transparent")
        g.pack(fill="x", pady=(0,18))
        g.grid_columnconfigure(0, weight=1, uniform="w")
        g.grid_columnconfigure(1, weight=1, uniform="w")

        self._wgt = {}
        for name, r, c, color in [("BPM",0,0,C_ORANGE),("X AXIS",0,1,C_BLUE),
                                   ("Y AXIS",1,0,C_GREEN),("Z AXIS",1,1,C_RED)]:
            box = ctk.CTkFrame(g, fg_color=C_CARD, corner_radius=20, height=110)
            box.grid(row=r, column=c, sticky="nsew", padx=7, pady=7)
            box.grid_propagate(False)
            ctk.CTkLabel(box, text=name, font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=C_SEC).place(x=14, y=14)
            lbl = ctk.CTkLabel(box, text="--",
                               font=ctk.CTkFont(size=32, weight="bold"), text_color=color)
            lbl.place(relx=0.5, rely=0.58, anchor="center")
            self._wgt[name] = lbl

        # 頻譜
        sc = ctk.CTkFrame(p, fg_color=C_CARD, corner_radius=22)
        sc.pack(fill="both", expand=True, padx=7)
        ctk.CTkLabel(sc, text="LIVE SPECTRUM",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=C_SEC).pack(anchor="w", padx=22, pady=(18,0))

        self._fig = Figure(figsize=(5,3), facecolor="#FFFFFF")
        self._ax  = self._fig.add_subplot(111)
        self._ax.set_facecolor("#FFFFFF"); self._ax.axis("off")
        self._fig.subplots_adjust(left=0.02, right=0.98, top=0.98, bottom=0.02)

        self.canvas = FigureCanvasTkAgg(self._fig, master=sc)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=18, pady=(0,18))

        n = 48
        self.bars = self._ax.bar(np.arange(n), np.zeros(n), color="#007AFF", width=0.7, edgecolor="none")
        self.num_bars = n

    # ── 事件 ──────────────────────────────────────────────────────
    def _refresh_ports(self):
        ports = SerialManager.list_ports()
        if ports:
            self._port_menu.configure(values=ports); self._port_menu.set(ports[0])
        else:
            self._port_menu.configure(values=["No ports"]); self._port_menu.set("No ports")

    def _toggle_conn(self):
        if self.serial_mgr.is_connected:
            self.serial_mgr.disconnect()
            self.btn_conn.configure(text="Connect", fg_color=C_GREEN)
            self._conn_lbl.configure(text="Disconnected", text_color=C_SEC)
        else:
            port = self._port_menu.get()
            if "No ports" in port: messagebox.showwarning("No Port","Select a COM port first."); return
            if self.serial_mgr.connect(port):
                self.btn_conn.configure(text="Disconnect", fg_color=C_RED)
                self._conn_lbl.configure(text=f"Connected  ·  {port}", text_color=C_GREEN)
            else:
                messagebox.showerror("Failed", f"Cannot open {port}")

    def _local(self):
        path = filedialog.askopenfilename(filetypes=[("Audio","*.mp3 *.wav *.flac *.ogg *.m4a")])
        if not path: return
        self.btn_lo.configure(text="Loading...")
        def w():
            ok = self.analyzer.load_file(path)
            self.after(0, lambda: self._done(ok, is_yt=False))
        threading.Thread(target=w, daemon=True).start()

    def _yt(self):
        url = self.url_entry.get().strip()
        if not url: return
        self.btn_yt.configure(state="disabled", text="Fetching...", fg_color=C_BLUE)
        def w():
            def upd(m): self.after(0, lambda: self.btn_yt.configure(text=m))
            ok = self.analyzer.load_youtube(url, upd)
            self.after(0, lambda: self._done(ok, is_yt=True))
        threading.Thread(target=w, daemon=True).start()

    def _done(self, ok, is_yt):
        if ok:
            self.btn_play.configure(state="normal")
            self.btn_stop.configure(state="normal")
            self._wgt["BPM"].configure(text=f"{self.analyzer.bpm:.0f}")
            if is_yt: self.btn_yt.configure(state="normal", text="✓ Loaded", fg_color=C_GREEN)
            else:     self.btn_lo.configure(text="✓ Loaded")
        else:
            if is_yt: self.btn_yt.configure(state="normal", text="✗ Failed", fg_color=C_RED)
            else:     self.btn_lo.configure(text="✗ Failed")
            messagebox.showerror("Error", "Failed to load audio.")

    def _play(self):
        if self.analyzer.is_playing: return
        self.analyzer.play()
        self.btn_play.configure(state="disabled")
        self.btn_stop.configure(state="normal")

    def _stop(self):
        self.analyzer.stop()
        self.btn_play.configure(state="normal")
        self.btn_stop.configure(state="disabled")

    # ── 座標分發 ─────────────────────────────────────────────────
    def _dispatch(self):
        while True:
            try:
                tx, ty, tz = self.coord_queue.get(timeout=0.1)
                self._smooth[0] += LERP_ALPHA * (tx - self._smooth[0])
                self._smooth[1] += LERP_ALPHA * (ty - self._smooth[1])
                self._smooth[2] += LERP_ALPHA * (tz - self._smooth[2])
                sx, sy, sz = int(self._smooth[0]), int(self._smooth[1]), int(self._smooth[2])
                if self.serial_mgr.is_connected:
                    self.serial_mgr.send(sx, sy, sz)
                self.after(0, lambda a=sx,b=sy,c=sz: (
                    self._wgt["X AXIS"].configure(text=str(a)),
                    self._wgt["Y AXIS"].configure(text=str(b)),
                    self._wgt["Z AXIS"].configure(text=str(c))
                ))
            except queue.Empty: pass

    # ── 頻譜 ─────────────────────────────────────────────────────
    def _on_spectrum(self, mag):
        n = self.num_bars
        chunk = max(len(mag)//n, 1)
        vals = np.log1p(np.mean(mag[:chunk*n].reshape(n,chunk), axis=1)) * 12
        def upd():
            for i, bar in enumerate(self.bars): bar.set_height(vals[i])
            self._ax.set_ylim(0, max(float(vals.max()), 1))
            self.canvas.draw_idle()
        self.after(0, upd)

    def on_closing(self):
        self.analyzer.stop(); self.serial_mgr.disconnect(); self.destroy()


if __name__ == "__main__":
    app = RobotDanceApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()