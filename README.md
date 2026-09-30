# RobotDance 🤖🎵

讓三軸步進馬達機械手臂跟著音樂跳舞。
A three-axis stepper-motor robot arm that dances to music.

---

## 簡介

RobotDance 由兩部分組成：

- **電腦端控制程式**（`robot_dance_controller.py`）：用 Python 寫的桌面介面。可以載入本機音檔或貼上 YouTube 網址，程式會用 librosa 分析節拍（BPM）與低／中／高頻能量，把音樂即時轉換成 X、Y、Z 三軸的目標位置，透過序列埠傳給 Arduino，同時顯示即時頻譜。
- **Arduino 韌體**（`src/dancearm.ino`）：接收 `<X,Y,Z>` 格式的步數指令，驅動三顆步進馬達（底座、大臂、小臂）同步移動，並做軟體限位保護。

動作邏輯：
- **X 軸（底座）**：依中高頻左右擺動
- **Y 軸（大臂）**：跟著 BPM 上下起伏
- **Z 軸（小臂）**：隨低頻（鼓、貝斯）伸展，遇到節拍時收回

## Overview

RobotDance has two parts:

- **Desktop controller** (`robot_dance_controller.py`): a Python GUI. Load a local audio file or paste a YouTube URL; the app uses librosa to detect the tempo (BPM) and low/mid/high frequency energy, turns the music into X/Y/Z target positions in real time, streams them to the Arduino over serial, and shows a live spectrum.
- **Arduino firmware** (`src/dancearm.ino`): receives step targets in the form `<X,Y,Z>` and drives three stepper motors (base, arm, forearm) simultaneously, with software limits.

Motion mapping:
- **X (base)**: swings left/right with mid/high frequencies
- **Y (arm)**: rises and falls with the BPM
- **Z (forearm)**: extends with bass energy and snaps back on each beat

---

## 硬體接線 / Wiring

| 功能 Function | X (Base) | Y (Arm) | Z (Forearm) |
|---|---|---|---|
| STEP | D2 | D3 | D4 |
| DIR  | D5 | D6 | D7 |

- ENABLE：D8（LOW = 啟用 / enabled）
- 驅動板預設 1/16 微步 / Drivers set to 1/16 microstepping（3200 steps/rev）
- 以 Arduino Uno + CNC Shield（A4988 / DRV8825）為例 / e.g. Arduino Uno + CNC Shield

---

## 啟動步驟（中文）

### 1. 燒錄 Arduino 韌體

1. 安裝 [VS Code](https://code.visualstudio.com/) 與 **PlatformIO IDE** 擴充套件。
2. 用 VS Code 開啟本專案資料夾。
3. 用 USB 接上 Arduino Uno。
4. 點下方狀態列的 **→ (Upload)**，或在終端機執行：
   ```bash
   pio run -t upload
   ```
5. （可選）開啟序列埠監控（115200 baud）確認看到 `[RobotDance]` 開機訊息，確認後記得**關閉監控**，否則 Python 程式會連不上序列埠。

> 也可以用 Arduino IDE：把 `src/dancearm.ino` 放進同名資料夾開啟並上傳即可。

### 2. 安裝 Python 環境

需要 Python 3.9 以上。

```bash
pip install -r requirements.txt
```

若要使用 YouTube 功能，還需要安裝 [FFmpeg](https://ffmpeg.org/download.html) 並加入 PATH（`yt-dlp` 轉 mp3 會用到）。

### 3. 執行控制程式

```bash
python robot_dance_controller.py
```

### 4. 操作流程

1. **ARDUINO CONNECTION**：選擇 Arduino 的 COM 埠 → 按 **Connect**。
2. **AUDIO SOURCE**：貼上 YouTube 網址按 **Fetch YouTube**，或按 **Local File** 選擇 mp3 / wav / flac / ogg / m4a。
3. 載入完成後會顯示 BPM，按 **▶ Play** 開始播放，手臂就會跟著跳舞。
4. 按 **■ Stop** 停止。

> ⚠️ 開機前請先把手臂擺到「零點」姿勢，韌體會以開機時的位置當作 0 步。

---

## Getting Started (English)

### 1. Flash the Arduino firmware

1. Install [VS Code](https://code.visualstudio.com/) and the **PlatformIO IDE** extension.
2. Open this project folder in VS Code.
3. Connect the Arduino Uno via USB.
4. Click **→ (Upload)** in the bottom status bar, or run:
   ```bash
   pio run -t upload
   ```
5. (Optional) Open the serial monitor at 115200 baud to see the `[RobotDance]` boot message, then **close the monitor** — otherwise the Python app can't open the port.

> Arduino IDE also works: put `src/dancearm.ino` in a folder of the same name, open it and upload.

### 2. Set up Python

Python 3.9+ is required.

```bash
pip install -r requirements.txt
```

For YouTube support, also install [FFmpeg](https://ffmpeg.org/download.html) and add it to your PATH (needed by `yt-dlp` to convert to mp3).

### 3. Run the controller

```bash
python robot_dance_controller.py
```

### 4. Usage

1. **ARDUINO CONNECTION**: pick the Arduino's COM port → click **Connect**.
2. **AUDIO SOURCE**: paste a YouTube URL and click **Fetch YouTube**, or click **Local File** to choose an mp3 / wav / flac / ogg / m4a.
3. Once loaded, the BPM is shown. Click **▶ Play** and the arm starts dancing.
4. Click **■ Stop** to stop.

> ⚠️ Place the arm in its home pose before powering on — the firmware treats the power-on position as step 0.

---

## 序列協定 / Serial Protocol

- Baud rate：`115200`
- 電腦 → Arduino / PC → Arduino：`<X,Y,Z>\n`（單位為步數 / values in steps）
- Arduino → 電腦 / Arduino → PC：`OK:X,Y,Z`（限位後的實際目標 / clamped targets）

## 專案結構 / Project Structure

```
dancearm/
├── src/dancearm.ino            # Arduino 韌體 / firmware
├── robot_dance_controller.py   # Python 控制介面 / desktop controller
├── platformio.ini              # PlatformIO 設定 / config
└── requirements.txt            # Python 套件 / dependencies
```
