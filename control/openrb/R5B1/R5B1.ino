#include <Dynamixel2Arduino.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include "Calibration.h"

using namespace ControlTableItem;

constexpr uint8_t trackerCount = 5;
constexpr uint8_t count = trackerCount + 1;
constexpr uint16_t model[count] = {1190, 1190, 1200, 1060, 1060, 1200};
constexpr float lowDeg[count]  = {-20, -8, 0, -60, -15, 0};
constexpr float highDeg[count] = {20, 8, 90, 60, 6, 14};
constexpr uint16_t pwm[count] = {180, 180, 200, 270, 300, 160};
constexpr uint16_t velocity[count] = {75, 60, 125, 29, 19, 95};
constexpr uint16_t acceleration[count] = {20, 16, 35, 12, 10, 40};
static_assert(sizeof(calibration)/sizeof(calibration[0]) == count, "One calibration row per axis");
constexpr unsigned long timeoutMs = 400;
constexpr unsigned long reportMs = 90;

Dynamixel2Arduino dxl(Serial1, -1);
uint8_t armed = 0;
bool moving = false;
unsigned long lastCommand = 0;
unsigned long lastReport = 0;
char line[112];
size_t length = 0;
bool overflow = false;
int32_t raw[count] = {0};
int32_t targets[count] = {0};

bool axisEnabled(uint8_t mask, uint8_t i) {
  return (mask & (1u << i)) != 0;
}

uint8_t commandAxisCount() {
  return axisEnabled(armed, trackerCount) ? count : trackerCount;
}

float limited(float value, float lo, float hi) {
  if (value < lo) return lo;
  if (value > hi) return hi;
  return value;
}

bool validCalibration(uint8_t i) {
  const auto& c = calibration[i];
  if (c.low<0 || c.low>4095 || c.zero<0 || c.zero>4095 || c.high<0 || c.high>4095) {
    return false;
  }
  if (lowDeg[i] == 0) return c.low==c.zero && abs(c.high-c.zero)>=4;
  return (c.low<c.zero && c.zero<c.high) || (c.low>c.zero && c.zero>c.high);
}

bool inside(uint8_t i, int32_t value, uint8_t tolerance) {
  const auto& c = calibration[i];
  int32_t a = c.low<c.high ? c.low : c.high;
  int32_t b = c.low<c.high ? c.high : c.low;
  return value>=a-tolerance && value<=b+tolerance;
}

int32_t toTicks(uint8_t i, float degrees) {
  const auto& c = calibration[i];
  degrees=limited(degrees,lowDeg[i],highDeg[i]);
  if (degrees < 0) {
    return lroundf(c.zero+(c.low-c.zero)*(degrees/lowDeg[i]));
  }
  return lroundf(c.zero+(c.high-c.zero)*(degrees/highDeg[i]));
}

float toDegrees(uint8_t i,int32_t ticks) {
  const auto& c = calibration[i];
  if (ticks==c.zero) return 0;
  if (lowDeg[i]<0 && ((ticks<c.zero)==(c.low<c.zero))) {
    return limited(lowDeg[i]*(ticks-c.zero)/float(c.low-c.zero),lowDeg[i],0);
  }
  return limited(highDeg[i]*(ticks-c.zero)/float(c.high-c.zero),0,highDeg[i]);
}

bool readTick(uint8_t id,int32_t& value) {
  value=dxl.readControlTableItem(static_cast<uint8_t>(PRESENT_POSITION),id,static_cast<uint32_t>(14));
  return dxl.getLastLibErrCode()==0 && value>=0 && value<=4095;
}

void release() {
  uint8_t previous=armed;
  armed=0;
  moving=false;
  for (uint8_t i=0;i<count;i++) {
    if (axisEnabled(previous,i)) dxl.torqueOff(i+1);
  }
}

void fault(const char* reason) {
  release();
  Serial.print("ERROR ");
  Serial.println(reason);
}

bool freeze() {
  moving=false;
  for (uint8_t i=0;i<count;i++) {
    if (!axisEnabled(armed,i)) continue;
    if (!readTick(i+1,raw[i]) || !inside(i,raw[i],3) ||
        !dxl.setGoalPosition(i+1,raw[i],UNIT_RAW)) {
      fault("HOLD_BUS");
      return false;
    }
    targets[i]=raw[i];
  }
  return true;
}

void report() {
  for (uint8_t i=0;i<count;i++) {
    if (axisEnabled(armed,i) && (!readTick(i+1,raw[i]) || !inside(i,raw[i],8))) {
      fault("READ_OR_LIMIT");
      return;
    }
  }
  Serial.print("STATE ");
  Serial.print(armed);
  for (uint8_t i=0;i<commandAxisCount();i++) {
    Serial.print(' ');
    Serial.print(axisEnabled(armed,i)?toDegrees(i,raw[i]):0.0f,3);
  }
  Serial.println();
}

void arm(uint8_t mask) {
  if (armed!=0 && armed!=mask) {
    Serial.println("ERROR RELEASE_BEFORE_MASK_CHANGE");
    return;
  }
  if (armed==mask) {
    if (!freeze()) return;
  } else {
    for (uint8_t i=0;i<count;i++) {
      if (!axisEnabled(mask,i)) continue;
      if (!validCalibration(i)) {
        Serial.print("LOCKED CALIBRATE ID");
        Serial.println(i+1);
        return;
      }
      const uint8_t id=i+1;
      if (!dxl.ping(id) || dxl.getModelNumber(id)!=model[i] ||
          dxl.readControlTableItem(OPERATING_MODE,id)!=3 ||
          (dxl.readControlTableItem(DRIVE_MODE,id)&4)!=0 ||
          !readTick(id,raw[i]) || !inside(i,raw[i],0)) {
        Serial.print("LOCKED MODEL_MODE_OR_POSITION ID");
        Serial.println(id);
        return;
      }
    }
    armed=mask;
    for (uint8_t i=0;i<count;i++) {
      if (!axisEnabled(mask,i)) continue;
      const uint8_t id=i+1;
      if (!dxl.torqueOff(id) ||
          !dxl.writeControlTableItem(GOAL_PWM,id,pwm[i]) ||
          !dxl.writeControlTableItem(PROFILE_VELOCITY,id,velocity[i]) ||
          !dxl.writeControlTableItem(PROFILE_ACCELERATION,id,acceleration[i]) ||
          !dxl.setGoalPosition(id,raw[i],UNIT_RAW) ||
          !dxl.torqueOn(id)) {
        fault("ARM_BUS");
        return;
      }
      targets[i]=raw[i];
    }
  }
  moving=false;
  Serial.print("ARMED ");
  Serial.println(mask);
  report();
}

bool getUnsigned(const char* text,long lo,long hi,long& value) {
  char* end=nullptr;
  value=strtol(text,&end,10);
  return end!=text && *end=='\0' && value>=lo && value<=hi;
}

void command(char* text) {
  if (!strcmp(text,"PING")) {
    Serial.println("R5B1 1");
    return;
  }
  if (!strcmp(text,"HOLD")) {
    if (armed!=0) freeze();
    return;
  }
  if (!strcmp(text,"RELEASE")) {
    release();
    Serial.println("RELEASED");
    return;
  }
  if (!strncmp(text,"READ ",5)) {
    long id=0;
    int32_t value=0;
    if (getUnsigned(text+5,1,count,id) && dxl.ping(id) && readTick(id,value)) {
      Serial.print("RAW ");
      Serial.print(id);
      Serial.print(' ');
      Serial.println(value);
    } else {
      Serial.println("ERROR READ");
    }
    return;
  }
  if (!strncmp(text,"ARM ",4)) {
    long mask=0;
    if (getUnsigned(text+4,1,(1u << count)-1,mask)) arm(mask);
    return;
  }
  if (armed==0 || strncmp(text,"GO ",3)) return;

  float goals[count];
  uint8_t active = commandAxisCount();
  char* next=text+3;
  for (uint8_t i=0;i<active;i++) {
    char* end=nullptr;
    goals[i]=strtof(next,&end);
    if (end==next || !isfinite(goals[i])) return;
    if (i+1<active && *end!=' ') return;
    next=end;
  }
  while (*next==' ') next++;
  if (*next!='\0') return;

  for (uint8_t i=0;i<active;i++) {
    if (!axisEnabled(armed,i)) continue;
    int32_t goal=toTicks(i,goals[i]);
    if (targets[i]==goal) continue;
    if (!dxl.setGoalPosition(i+1,goal,UNIT_RAW)) {
      fault("WRITE_BUS");
      return;
    }
    targets[i]=goal;
  }
  lastCommand=millis();
  moving=true;
}

void setup() {
  Serial.begin(115200);
#if defined(BDPIN_DXL_PWR_EN)
  pinMode(BDPIN_DXL_PWR_EN,OUTPUT);
  digitalWrite(BDPIN_DXL_PWR_EN,HIGH);
#endif
  dxl.begin(57600);
  dxl.setPortProtocolVersion(2.0);
}

void loop() {
  if (moving && millis()-lastCommand>=timeoutMs) freeze();
  while (Serial.available()) {
    char c=static_cast<char>(Serial.read());
    if (c=='\r') continue;
    if (c=='\n') {
      if (!overflow && length>0) {
        line[length]='\0';
        command(line);
      }
      length=0;
      overflow=false;
    } else if (!overflow) {
      if (length+1<sizeof(line)) line[length++]=c;
      else overflow=true;
    }
  }
  if (armed!=0 && millis()-lastReport>=reportMs) {
    lastReport=millis();
    report();
  }
}
