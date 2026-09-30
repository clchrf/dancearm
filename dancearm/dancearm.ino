/*
 ╔═══════════════════════════════════════════════════════════════╗
 ║  Robot Dance — Arduino 韌體 v2                                ║
 ║  腳位配置符合原版接線：                                        ║
 ║    STEP: Pin 2(X), 3(Y), 4(Z)                                 ║
 ║    DIR:  Pin 5(X), 6(Y), 7(Z)                                 ║
 ║    ENABLE: Pin 8 (LOW = 啟用)                                  ║
 ║  協定：Serial 115200，接收 <X,Y,Z>\n                           ║
 ╚═══════════════════════════════════════════════════════════════╝
*/

#include <math.h>

// ── 腳位定義（符合你的原版接線）────────────────────────────────
const int stepPins[] = {2, 3, 4};   // X(Base), Y(Arm), Z(Forearm)
const int dirPins[]  = {5, 6, 7};
const int enablePin  = 8;

// ── 微步設定（1/16 微步）────────────────────────────────────────
const float MICROSTEPS       = 16.0;
const float STEPS_PER_REV   = 200.0 * MICROSTEPS;   // 3200 steps/rev
const float STEPS_PER_DEGREE = STEPS_PER_REV / 360.0;

// ── 速度設定 ─────────────────────────────────────────────────────
const int STEP_DELAY = 600;   // microseconds，調大→慢但穩，調小→快但可能失步

// ── 安全限位（角度，根據實際機構調整）──────────────────────────
const float X_MIN_DEG = -180.0, X_MAX_DEG = 180.0;
const float Y_MIN_DEG =    0.0, Y_MAX_DEG = 180.0;
const float Z_MIN_DEG =    0.0, Z_MAX_DEG = 180.0;

// ── 狀態變數 ─────────────────────────────────────────────────────
long currentSteps[3] = {0, 0, 0};
long targetSteps[3]  = {0, 0, 0};

// 序列緩衝
String inputString = "";
bool   inPacket    = false;

// ═════════════════════════════════════════════════════════════════
void setup() {
  Serial.begin(115200);

  // Enable 腳位：LOW = 啟用驅動器
  pinMode(enablePin, OUTPUT);
  digitalWrite(enablePin, LOW);

  for (int i = 0; i < 3; i++) {
    pinMode(stepPins[i], OUTPUT);
    pinMode(dirPins[i],  OUTPUT);
    digitalWrite(stepPins[i], LOW);
  }

  Serial.println(F("[RobotDance] 韌體啟動 v2"));
  Serial.println(F("[RobotDance] 等待座標指令 <X,Y,Z>..."));
}

// ═════════════════════════════════════════════════════════════════
void loop() {
  // ── ① 非阻塞序列讀取，解析 <X,Y,Z> 格式 ──────────────────────
  while (Serial.available() > 0) {
    char c = (char)Serial.read();

    if (c == '<') {
      inputString = "";
      inPacket    = true;
    } else if (c == '>' && inPacket) {
      inPacket = false;
      parsePacket(inputString);
      inputString = "";
    } else if (inPacket) {
      inputString += c;
    }
  }

  // ── ② 多軸同步步進（非阻塞）──────────────────────────────────
  bool isMoving = false;
  for (int i = 0; i < 3; i++) {
    if (currentSteps[i] != targetSteps[i]) {
      bool goForward = (currentSteps[i] < targetSteps[i]);
      digitalWrite(dirPins[i], goForward ? HIGH : LOW);
      currentSteps[i] += goForward ? 1 : -1;
      digitalWrite(stepPins[i], HIGH);
      isMoving = true;
    }
  }

  if (isMoving) {
    delayMicroseconds(STEP_DELAY);
    for (int i = 0; i < 3; i++) digitalWrite(stepPins[i], LOW);
    delayMicroseconds(STEP_DELAY);
  }
}

// ═════════════════════════════════════════════════════════════════
// 解析 "X,Y,Z" 字串（已去掉 < > 符號）
// Python 傳來的是步進數，直接轉角度再換算
// ═════════════════════════════════════════════════════════════════
void parsePacket(String data) {
  int c1 = data.indexOf(',');
  int c2 = data.indexOf(',', c1 + 1);
  if (c1 < 0 || c2 < 0) return;

  // Python 傳來的是步進數（steps），直接當目標
  long tx = data.substring(0, c1).toInt();
  long ty = data.substring(c1 + 1, c2).toInt();
  long tz = data.substring(c2 + 1).toInt();

  // 套用限位（步進數換算）
  targetSteps[0] = constrain(tx, (long)(X_MIN_DEG * STEPS_PER_DEGREE), (long)(X_MAX_DEG * STEPS_PER_DEGREE));
  targetSteps[1] = constrain(ty, (long)(Y_MIN_DEG * STEPS_PER_DEGREE), (long)(Y_MAX_DEG * STEPS_PER_DEGREE));
  targetSteps[2] = constrain(tz, (long)(Z_MIN_DEG * STEPS_PER_DEGREE), (long)(Z_MAX_DEG * STEPS_PER_DEGREE));

  // 偵錯回傳
  Serial.print(F("OK:"));
  Serial.print(targetSteps[0]); Serial.print(',');
  Serial.print(targetSteps[1]); Serial.print(',');
  Serial.println(targetSteps[2]);
}