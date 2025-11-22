#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

#define SDA_PIN 21
#define SCL_PIN 22

Adafruit_PWMServoDriver pca40(0x40);   // left side board
Adafruit_PWMServoDriver pca60(0x60);   // right side board

#define SERVO_MIN_US 500
#define SERVO_MAX_US 2500
#define SERVO_FREQ   50

// ====== ANGLES (you can tweak these) ======
int COXA_CENTER = 90;
int COXA_FWD    = 115;   // rotate leg forward
int COXA_BACK   = 65;    // rotate leg backward

int FEMUR_UP    = 60;    // lift leg
int FEMUR_DOWN  = 95;    // leg on ground

int TIBIA_NEUT  = 90;
int TIBIA_FWD   = 120;   // foot forward
int TIBIA_BACK  = 70;    // foot backward

// ---------- Helpers ----------
uint16_t toTicks(int angle) {
  float pulseUs = SERVO_MIN_US +
                  (SERVO_MAX_US - SERVO_MIN_US) * (angle / 180.0);
  float tickUs = 1000000.0 / (SERVO_FREQ * 4096.0);
  return pulseUs / tickUs;
}

void setJoint(uint8_t board, uint8_t ch, int angle) {
  if (board == 0x40)
    pca40.setPWM(ch, 0, toTicks(angle));
  else
    pca60.setPWM(ch, 0, toTicks(angle));
}

void centerAll() {
  for (int ch = 0; ch < 9; ch++) {
    setJoint(0x40, ch, 90);
    setJoint(0x60, ch, 90);
  }
}

// ---------- Tripod groups ----------
// { board, coxaCh, femurCh, tibiaCh }

// Group A = LF, LM, LR
int groupA[3][4] = {
  {0x40, 0, 1, 2}, // LF
  {0x40, 3, 4, 5}, // LM
  {0x40, 6, 7, 8}  // LR
};

// Group B = RF, RM, RR
int groupB[3][4] = {
  {0x60, 0, 1, 2}, // RF
  {0x60, 3, 4, 5}, // RM
  {0x60, 6, 7, 8}  // RR
};

// phase: set all 3 joints for all 3 legs in a group
void moveGroupPhase(int g[][4], int femurAngle, int tibiaAngle, int coxaAngle) {
  for (int i = 0; i < 3; i++) {
    uint8_t board = (uint8_t)g[i][0];
    uint8_t coxa  = (uint8_t)g[i][1];
    uint8_t femur = (uint8_t)g[i][2];
    uint8_t tibia = (uint8_t)g[i][3];

    setJoint(board, coxa,  coxaAngle);
    setJoint(board, femur, femurAngle);
    setJoint(board, tibia, tibiaAngle);
  }
}

// ---------- Setup & Loop ----------
void setup() {
  Serial.begin(115200);
  Wire.begin(SDA_PIN, SCL_PIN);

  pca40.begin();
  pca60.begin();
  pca40.setPWMFreq(SERVO_FREQ);
  pca60.setPWMFreq(SERVO_FREQ);

  centerAll();
  delay(1000);
}

void loop() {
  // ===== GROUP A cycle: lift -> forward -> down -> push =====
  // 1) Lift leg up
  moveGroupPhase(groupA, FEMUR_UP, TIBIA_NEUT, COXA_CENTER);
  delay(120);

  // 2) Swing forward (while lifted)
  moveGroupPhase(groupA, FEMUR_UP, TIBIA_FWD, COXA_FWD);
  delay(120);

  // 3) Put down (support)
  moveGroupPhase(groupA, FEMUR_DOWN, TIBIA_FWD, COXA_FWD);
  delay(130);

  // 4) Push backward on ground (drive body forward)
  moveGroupPhase(groupA, FEMUR_DOWN, TIBIA_BACK, COXA_BACK);
  delay(130);

  // ===== GROUP B cycle =====
  moveGroupPhase(groupB, FEMUR_UP, TIBIA_NEUT, COXA_CENTER);
  delay(120);

  moveGroupPhase(groupB, FEMUR_UP, TIBIA_FWD, COXA_FWD);
  delay(120);

  moveGroupPhase(groupB, FEMUR_DOWN, TIBIA_FWD, COXA_FWD);
  delay(130);

  moveGroupPhase(groupB, FEMUR_DOWN, TIBIA_BACK, COXA_BACK);
  delay(130);
}