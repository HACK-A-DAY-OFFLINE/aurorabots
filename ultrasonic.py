#python
#include <WiFi.h>
#include <WebSocketsServer.h>
#include <ESP32Servo.h>

//WiFi AP config
const char *apSsid = "HEHEHEHE";
const char *apPass = "pathu_!!!!";

//Websocket 
WebSocketsServer webSocket = WebSocketsServer(81);

//Ultrasonic pins 
#define TRIG_FRONT 4
#define ECHO_FRONT 15

#define TRIG_BACK 19
#define ECHO_BACK 21

#define TRIG_LEFT 22   // ultrasonic mounted on LEFT servo
#define ECHO_LEFT 23

#define TRIG_RIGHT 5   // ultrasonic mounted on RIGHT servo
#define ECHO_RIGHT 18

// ---------- Servo pins ----------
#define LEFT_SERVO_PIN 12
#define RIGHT_SERVO_PIN 13

//Servos
Servo leftServo;
Servo rightServo;

//Config
const int LEFT_SWEEP_START = 120;   // start angle for left servo
const int LEFT_SWEEP_END   = 240;   // end angle for left servo (covers front-left -> back-left)
const int RIGHT_SWEEP_START = -60;  // -60 == 300° equivalent (front-right -> back-right)
const int RIGHT_SWEEP_END   = 60;

const int SWEEP_STEP_DEG = 15;      // sample every 15 degrees
const int SERVO_SETTLE_MS = 70;     // time to wait after moving servo (tweak for your servos)

// point cloud buffer (for onboard mapping use; limited size to avoid memory issues)
struct Point { float x; float y; };
#define MAX_POINTS 1200
Point pointCloud[MAX_POINTS];
int pointCount = 0;

// robot pose for simple mapping (we keep robot origin at 0,0; you can extend to odometry)
float robotX = 0;
float robotY = 0;
float robotTheta = 0; // facing +Y (front) by convention in this code

// mapping controls
volatile bool mappingActive = true;
volatile int movementSpeed = 1; // 0..5 (used if you simulate movement)
volatile bool resetRequested = false;

// ---------- Helpers ----------
long readUltrasonicCm(int trigPin, int echoPin) {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(3);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);
  long duration = pulseIn(echoPin, HIGH, 25000); // timeout 25ms (~4m)
  long distance = duration * 0.034 / 2.0;
  if (duration == 0 || distance > 400) return -1; // invalid
  return distance;
}

// Convert polar (distance in cm, bearing in degrees) to local (x,y) (front = +Y)
void polarToXY(float distCm, float bearingDeg, float &outX, float &outY) {
  // convert so that 0° = front along +Y axis
  float rad = (bearingDeg - 90.0f) * (PI / 180.0f); // match canvas convention used earlier
  outX = distCm * cos(rad);
  outY = distCm * sin(rad);
}

void addPointToCloud(float gx, float gy) {
  if (pointCount >= MAX_POINTS) {
    // circular buffer style: overwrite oldest
    for (int i = 1; i < MAX_POINTS; ++i) pointCloud[i-1] = pointCloud[i];
    pointCount = MAX_POINTS - 1;
  }
  pointCloud[pointCount].x = gx;
  pointCloud[pointCount].y = gy;
  pointCount++;
}

// ---------- WebSocket event handler ----------
void handleWebSocketEvent(uint8_t num, WStype_t type, uint8_t * payload, size_t length) {
  if (type == WStype_TEXT) {
    String msg = String((char*)payload);
    // Simple command parsing (expect JSON like {"cmd":"start"} or {"cmd":"speed":3})
    if (msg.indexOf("\"cmd\"") >= 0) {
      if (msg.indexOf("\"start\"") >= 0) {
        mappingActive = true;
      } else if (msg.indexOf("\"stop\"") >= 0) {
        mappingActive = false;
      } else if (msg.indexOf("\"reset\"") >= 0) {
        resetRequested = true;
      }
    }
    if (msg.indexOf("\"speed\"") >= 0) {
      // extract number
      int c1 = msg.indexOf(":");
      if (c1 > 0) {
        int val = msg.substring(c1+1).toInt();
        if (val < 0) val = 0;
        if (val > 5) val = 5;
        movementSpeed = val;
      }
    }
  }
}

// ---------- Setup ----------
void setupPins() {
  pinMode(TRIG_FRONT, OUTPUT); digitalWrite(TRIG_FRONT, LOW);
  pinMode(ECHO_FRONT, INPUT);

  pinMode(TRIG_BACK, OUTPUT); digitalWrite(TRIG_BACK, LOW);
  pinMode(ECHO_BACK, INPUT);

  pinMode(TRIG_LEFT, OUTPUT); digitalWrite(TRIG_LEFT, LOW);
  pinMode(ECHO_LEFT, INPUT);

  pinMode(TRIG_RIGHT, OUTPUT); digitalWrite(TRIG_RIGHT, LOW);
  pinMode(ECHO_RIGHT, INPUT);
}

void setupWiFiAP() {
  WiFi.softAP(apSsid, apPass);
  Serial.print("AP started. SSID: ");
  Serial.println(apSsid);
  Serial.print("IP: ");
  Serial.println(WiFi.softAPIP()); // usually 192.168.4.1
}

void setup() {
  Serial.begin(115200);
  delay(100);

  setupPins();

  // init servos
  leftServo.setPeriodHertz(50); // 50 Hz
  rightServo.setPeriodHertz(50);
  leftServo.attach(LEFT_SERVO_PIN);
  rightServo.attach(RIGHT_SERVO_PIN);

  // center servos to safe positions
  leftServo.write(180);  // put left servo near one side (we will move)
  rightServo.write(0);

  setupWiFiAP();

  webSocket.begin();
  webSocket.onEvent(handleWebSocketEvent);

  Serial.println("WebSocket server started on port 81");
}

//Main loop 
unsigned long lastBroadcast = 0;
const unsigned long BROADCAST_INTERVAL_MS = 120; // ~8 updates per sec

void loop() {
  webSocket.loop();

  if (resetRequested) {
    // reset map and pose
    pointCount = 0;
    robotX = 0; robotY = 0; robotTheta = 0;
    resetRequested = false;
    Serial.println("Map reset requested.");
  }

  // if mapping paused, still serve websocket, but skip scanning
  if (!mappingActive) {
    delay(50);
    return;
  }

  // 1) Read static sensors
  long frontDist = readUltrasonicCm(TRIG_FRONT, ECHO_FRONT);
  delay(20);
  long backDist = readUltrasonicCm(TRIG_BACK, ECHO_BACK);
  delay(20);

  // 2) Sweep left servo across LEFT_SWEEP_START -> LEFT_SWEEP_END and sample distances
  long bestLeft = -1;
  for (int a = LEFT_SWEEP_START; a <= LEFT_SWEEP_END; a += SWEEP_STEP_DEG) {
    leftServo.write(a % 180); // ESP32Servo expects 0-180
    delay(SERVO_SETTLE_MS);
    long d = readUltrasonicCm(TRIG_LEFT, ECHO_LEFT);
    delay(8);

    if (d > 0) {
      // compute global point (bearing = a degrees)
      float lx, ly;
      polarToXY((float)d, (float)a, lx, ly);
      addPointToCloud(lx + robotX, ly + robotY);

      if (bestLeft < 0 || d < bestLeft) bestLeft = d;
    }
  }

  // 3) Sweep right servo (we map -60..60 as 300..360 & 0..60)
  long bestRight = -1;
  // Normalize handling: we map angles <0 to +360
  for (int a = RIGHT_SWEEP_START; a <= RIGHT_SWEEP_END; a += SWEEP_STEP_DEG) {
    int angleToWrite = a;
    if (angleToWrite < 0) angleToWrite += 360;
    // Convert 0..359 to 0..180 servo domain: we remap so center front=90, right=0, back=180 etc.
    // For simplicity we map 300..360 => 300-360 mapped to 300..360-360=-60..0 => convert to 300..360 -> map to 0..60 for servo
    int servoAngle;
    if (angleToWrite <= 180) {
      servoAngle = angleToWrite; // 0..180
    } else {
      servoAngle = angleToWrite - 180; // 181..359 -> 1..179 (some mapping)
    }
    // Bound servo angle 0..180
    if (servoAngle < 0) servoAngle = 0;
    if (servoAngle > 180) servoAngle = 180;

    rightServo.write(servoAngle);
    delay(SERVO_SETTLE_MS);
    long d = readUltrasonicCm(TRIG_RIGHT, ECHO_RIGHT);
    delay(8);

    int globalAngle = a;
    if (globalAngle < 0) globalAngle += 360; // normalize

    if (d > 0) {
      float rx, ry;
      polarToXY((float)d, (float)globalAngle, rx, ry);
      addPointToCloud(rx + robotX, ry + robotY);
      if (bestRight < 0 || d < bestRight) bestRight = d;
    }
  }

  // 4) If both sweeps done, optionally move robot a bit (simulation), depends on movementSpeed
  // (Here we simulate small forward translation so mappings change; if you have odometry, replace with actual pose updates)
  if (movementSpeed > 0) {
    float stepCm = (float)movementSpeed * 2.0; // tune factor (2 cm per speed unit)
    // move forward in robot's heading (+Y)
    robotY += stepCm;
  }

  // 5) Prepare summary JSON to satisfy webpage format
  // If any side had no reading, try fallback - prefer large value
  long leftSummary = bestLeft >= 0 ? bestLeft : -1;
  long rightSummary = bestRight >= 0 ? bestRight : -1;

  // broadcast summary at a regular interval
  unsigned long now = millis();
  if (now - lastBroadcast >= BROADCAST_INTERVAL_MS) {
    lastBroadcast = now;
    // Compose JSON string
    String data = "{\"front\":" + String(frontDist) +
                  ",\"right\":" + String(rightSummary) +
                  ",\"back\":"  + String(backDist) +
                  ",\"left\":"  + String(leftSummary) + "}";
    webSocket.broadcastTXT(data);
    Serial.println(data);
  }

  // small loop delay to prevent hogging CPU
  delay(15);
}