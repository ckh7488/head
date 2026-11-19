#include <Dynamixel2Arduino.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include "Calibration.h"

constexpr uint8_t trackerCount = 5;
constexpr uint8_t count = trackerCount + 1;
constexpr uint16_t model[count] = {1190, 1190, 1200, 1060, 1060, 1200};
constexpr float lowDeg[count]  = {-20, -8, 0, -60, -15, 0};
constexpr float highDeg[count] = {20, 8, 90, 60, 6, 13};
constexpr uint16_t pwm[count] = {180, 180, 200, 270, 300, 160};
constexpr uint16_t velocity[count] = {75, 60, 160, 29, 19, 95};
constexpr uint16_t acceleration[count] = {20, 16, 62, 12, 10, 40};
static_assert(sizeof(calibration)/sizeof(calibration[0]) == count, "One calibration row per axis");
constexpr uint32_t busBaud = 57600;
constexpr uint32_t busTimeoutMs = 14;
constexpr uint32_t timeoutMs = 400;
constexpr uint32_t goalPeriodMs = 60;
constexpr uint32_t reportMs = 120;
constexpr uint8_t holdTolerance = 3;
constexpr uint8_t positionTolerance = 8;

struct Register {
  uint16_t address;
  uint8_t size;
};

// Protocol 2.0 control-table addresses shared by the XL330 and XL430.
constexpr Register modelNumber{0, 2}, driveMode{10, 1}, operatingMode{11, 1};
constexpr Register torqueEnable{64, 1}, statusReturnLevel{68, 1};
constexpr Register goalPwm{100, 2}, profileAcceleration{108, 4}, profileVelocity{112, 4};
constexpr Register goalPosition{116, 4}, presentPosition{132, 4};

enum class Transfer { ok, bus, servo };

struct AxisStatus {
  int32_t model = -1;
  int32_t mode = -1;
  int32_t drive = -1;
  int32_t returnLevel = -1;
  int32_t torque = -1;
  int32_t position = -1;
};

Dynamixel2Arduino dxl(Serial1, -1);
uint8_t armed = 0;
bool faulted = false;
bool moving = false;
bool pending = false;
uint32_t lastCommand = 0;
uint32_t lastGoal = 0;
uint32_t lastReport = 0;
char line[112];
size_t length = 0;
bool overflow = false;
int32_t raw[count] = {0};
int32_t targets[count] = {0};
int32_t queued[count] = {0};

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
  return value>=0 && value<=4095 && value>=a-tolerance && value<=b+tolerance;
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

Transfer transferResult(bool complete) {
  if (dxl.getLastLibErrCode()!=DXL_LIB_OK) return Transfer::bus;
  if (dxl.getLastStatusPacketError()!=0) return Transfer::servo;
  return complete ? Transfer::ok : Transfer::bus;
}

bool retryable(Transfer result) {
  if (result==Transfer::servo) return dxl.getLastStatusPacketError()==DXL2_0_ERR_CRC_ERROR;
  switch (dxl.getLastLibErrCode()) {
    case DXL_LIB_OK:
    case DXL_LIB_ERROR_TIMEOUT:
    case DXL_LIB_ERROR_CRC:
    case DXL_LIB_ERROR_WRONG_PACKET:
    case DXL_LIB_ERROR_PORT_WRITE:
      return true;
    default:
      return false;
  }
}

void drainBusInput() {
  for (int buffered=Serial1.available();buffered>0;buffered--) Serial1.read();
}

Transfer readRegister(uint8_t id, Register reg, int32_t& value) {
  Transfer result;
  for (uint8_t attempt=0;attempt<2;attempt++) {
    uint8_t bytes[4] = {};
    drainBusInput();
    result=transferResult(dxl.read(id,reg.address,reg.size,bytes,sizeof(bytes),busTimeoutMs)==reg.size);
    if (result==Transfer::ok) {
      uint32_t decoded=0;
      for (uint8_t n=0;n<reg.size;n++) decoded|=uint32_t(bytes[n])<<(8*n);
      value=static_cast<int32_t>(decoded);
      return result;
    }
    if (!retryable(result)) break;
  }
  return result;
}

Transfer writeRegister(uint8_t id, Register reg, int32_t value, bool retry=true) {
  const uint32_t encoded=static_cast<uint32_t>(value);
  uint8_t bytes[4];
  for (uint8_t n=0;n<reg.size;n++) bytes[n]=static_cast<uint8_t>(encoded>>(8*n));
  drainBusInput();
  Transfer result=transferResult(dxl.write(id,reg.address,bytes,reg.size,busTimeoutMs));
  if (retry && result!=Transfer::ok && retryable(result)) {
    drainBusInput();
    result=transferResult(dxl.write(id,reg.address,bytes,reg.size,busTimeoutMs));
  }
  return result;
}

bool readAxis(uint8_t i, AxisStatus& status) {
  const uint8_t id=i+1;
  if (readRegister(id,modelNumber,status.model)!=Transfer::ok) return false;
  if (status.model!=model[i]) return true;
  return readRegister(id,operatingMode,status.mode)==Transfer::ok &&
         readRegister(id,driveMode,status.drive)==Transfer::ok &&
         readRegister(id,statusReturnLevel,status.returnLevel)==Transfer::ok &&
         readRegister(id,torqueEnable,status.torque)==Transfer::ok &&
         readRegister(id,presentPosition,status.position)==Transfer::ok;
}

bool readyToArm(uint8_t i, const AxisStatus& status) {
  return status.model==model[i] && status.mode==3 && (status.drive&12)==0 &&
         status.returnLevel==2 && status.torque==0 && inside(i,status.position,0);
}

void cancelMotion() {
  pending=false;
  moving=false;
}

void release() {
  cancelMotion();
  for (uint8_t i=0;i<count;i++) {
    if (!axisEnabled(armed,i)) continue;
    int32_t torque=-1;
    writeRegister(i+1,torqueEnable,0);
    if (readRegister(i+1,torqueEnable,torque)==Transfer::ok && torque==0) {
      armed&=~(1u<<i);
    }
  }
  faulted=armed!=0;
  Serial.println(faulted ? "ERROR RELEASE_UNCONFIRMED" : "RELEASED");
}

void printAxisError(const char* reason, uint8_t id) {
  Serial.print(reason);
  Serial.print(" ID");
  Serial.println(id);
}

void latchFault(const char* reason, uint8_t id=0) {
  cancelMotion();
  faulted=true;
  Serial.print("ERROR ");
  if (id) printAxisError(reason,id);
  else Serial.println(reason);
}

bool holdAxes() {
  bool held=true;
  for (uint8_t i=0;i<count;i++) {
    if (!axisEnabled(armed,i)) continue;
    if (readRegister(i+1,presentPosition,raw[i])!=Transfer::ok || !inside(i,raw[i],holdTolerance)) {
      held=false;
      continue;
    }
    const auto& c=calibration[i];
    const int32_t lower=c.low<c.high ? c.low : c.high;
    const int32_t upper=c.low<c.high ? c.high : c.low;
    const int32_t goal=raw[i]<lower ? lower : (raw[i]>upper ? upper : raw[i]);
    if (writeRegister(i+1,goalPosition,goal)!=Transfer::ok) {
      held=false;
      continue;
    }
    targets[i]=goal;
  }
  return held;
}

void stopOnFault(const char* reason, uint8_t id) {
  latchFault(reason,id);
  if (!holdAxes()) Serial.println("ERROR HOLD_UNCONFIRMED");
}

bool freeze() {
  cancelMotion();
  if (holdAxes()) return true;
  latchFault("HOLD_UNCONFIRMED");
  return false;
}

void checkAxis(uint8_t i) {
  AxisStatus status;
  if (!readAxis(i,status)) {
    printAxisError("ERROR CHECK_BUS_OR_STATUS",i+1);
    return;
  }
  Serial.print("CHECK ");
  Serial.print(i+1);
  const bool calibrated=validCalibration(i);
  const int32_t values[] = {status.model,status.mode,status.drive,status.returnLevel,status.torque,status.position,
                            calibrated,!faulted && calibrated && readyToArm(i,status)};
  for (int32_t value : values) {
    Serial.print(' ');
    Serial.print(value);
  }
  Serial.println();
}

void emitGoals() {
  for (uint8_t i=0;i<count;i++) {
    if (!axisEnabled(armed,i) || targets[i]==queued[i]) continue;
    Transfer result=writeRegister(i+1,goalPosition,queued[i]);
    if (result!=Transfer::ok) {
      stopOnFault(result==Transfer::servo ? "WRITE_STATUS" : "WRITE_BUS",i+1);
      return;
    }
    targets[i]=queued[i];
  }
  pending=false;
}

void report() {
  for (uint8_t i=0;i<count;i++) {
    if (!axisEnabled(armed,i)) continue;
    Transfer result=readRegister(i+1,presentPosition,raw[i]);
    if (result!=Transfer::ok) {
      stopOnFault(result==Transfer::servo ? "READ_STATUS" : "READ_BUS",i+1);
      return;
    }
    if (!inside(i,raw[i],positionTolerance)) {
      stopOnFault("POSITION_LIMIT",i+1);
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
  if (faulted) {
    Serial.println("LOCKED RELEASE_AFTER_FAULT");
    return;
  }
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
    }
    for (uint8_t i=0;i<count;i++) {
      if (!axisEnabled(mask,i)) continue;
      AxisStatus status;
      if (!readAxis(i,status) || !readyToArm(i,status)) {
        printAxisError("LOCKED SERVO_CHECK",i+1);
        return;
      }
    }
    for (uint8_t i=0;i<count;i++) {
      if (!axisEnabled(mask,i)) continue;
      const uint8_t id=i+1;
      int32_t confirmedPwm=-1;
      if (writeRegister(id,goalPwm,pwm[i])!=Transfer::ok ||
          readRegister(id,goalPwm,confirmedPwm)!=Transfer::ok || confirmedPwm!=pwm[i] ||
          writeRegister(id,profileVelocity,velocity[i])!=Transfer::ok ||
          writeRegister(id,profileAcceleration,acceleration[i])!=Transfer::ok) {
        printAxisError("LOCKED ARM_CONFIG",id);
        return;
      }
    }
    for (uint8_t i=0;i<count;i++) {
      if (!axisEnabled(mask,i)) continue;
      const uint8_t id=i+1;
      if (readRegister(id,presentPosition,raw[i])!=Transfer::ok ||
          !inside(i,raw[i],0) || writeRegister(id,goalPosition,raw[i])!=Transfer::ok) {
        stopOnFault("ARM_POSITION_OR_BUS",id);
        return;
      }
      // An enable may have reached the servo even if its acknowledgement is lost.
      armed|=1u<<i;
      int32_t torque=-1;
      if (writeRegister(id,torqueEnable,1,false)!=Transfer::ok ||
          readRegister(id,torqueEnable,torque)!=Transfer::ok || torque!=1) {
        stopOnFault("ARM_ENABLE_UNCONFIRMED",id);
        return;
      }
      targets[i]=raw[i];
    }
  }
  cancelMotion();
  lastGoal=static_cast<uint32_t>(millis())-goalPeriodMs;
  lastReport=millis();
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
    if (armed!=0 && !faulted) freeze();
    return;
  }
  if (!strcmp(text,"RELEASE")) {
    release();
    return;
  }
  if (!strncmp(text,"CHECK ",6)) {
    long id=0;
    if (moving) Serial.println("ERROR CHECK_DURING_MOVE");
    else if (getUnsigned(text+6,1,count,id)) checkAxis(id-1);
    else Serial.println("ERROR CHECK_ID");
    return;
  }
  if (!strncmp(text,"READ ",5)) {
    long id=0;
    int32_t value=0;
    if (getUnsigned(text+5,1,count,id) &&
        readRegister(id,presentPosition,value)==Transfer::ok && value>=0 && value<=4095) {
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
  if (armed==0 || faulted || strncmp(text,"GO ",3)) return;

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
    queued[i]=toTicks(i,goals[i]);
  }
  lastCommand=millis();
  moving=true;
  pending=true;
}

void setup() {
  Serial.begin(115200);
#if defined(BDPIN_DXL_PWR_EN)
  pinMode(BDPIN_DXL_PWR_EN,OUTPUT);
  digitalWrite(BDPIN_DXL_PWR_EN,HIGH);
#endif
  dxl.begin(busBaud);
  dxl.setPortProtocolVersion(2.0);
}

void checkCommandTimeout() {
  if (moving && static_cast<uint32_t>(millis()-lastCommand)>=timeoutMs) freeze();
}

void loop() {
  checkCommandTimeout();
  for (size_t remaining=sizeof(line);remaining>0 && Serial.available();remaining--) {
    char c=static_cast<char>(Serial.read());
    if (c=='\n') {
      if (length>0 && line[length-1]=='\r') length--;
      if (!overflow && length>0) {
        line[length]='\0';
        if (!memchr(line,'\r',length)) command(line);
      }
      length=0;
      overflow=false;
    } else if (!overflow) {
      if ((c=='\r' || (c>=' ' && c<='~')) && length+1<sizeof(line)) line[length++]=c;
      else overflow=true;
    }
  }
  checkCommandTimeout();
  if (pending && static_cast<uint32_t>(millis()-lastGoal)>=goalPeriodMs) {
    lastGoal=millis();
    emitGoals();
  }
  if (armed!=0 && !faulted && static_cast<uint32_t>(millis()-lastReport)>=reportMs) {
    lastReport=millis();
    report();
  }
}
