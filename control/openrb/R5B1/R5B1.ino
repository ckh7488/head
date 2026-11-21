#include <Dynamixel2Arduino.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include "Calibration.h"

constexpr uint8_t trackerCount = 5;
constexpr uint8_t count = trackerCount + 1;
constexpr uint8_t blinkAxis = 2;
constexpr uint16_t blinkTravelTicks = 1024;
constexpr uint16_t blinkFastModel = 1190;
constexpr uint16_t blinkFastPwm = 230;
constexpr float jawMaxDegrees = 5.5f;
constexpr uint8_t jawMaxTravelTicks = static_cast<uint8_t>(4096u*jawMaxDegrees/360u);
constexpr float neckPitchMaxDegrees = 4.5f;
constexpr uint8_t neckPitchMaxNegativeDegrees = 15;
constexpr uint8_t neckPitchMaxPositiveTicks = 34;
constexpr uint8_t neckPitchMaxNegativeTicks = 155;
constexpr uint16_t model[count] = {1190, 1190, 1200, 1060, 1060, 1200};
constexpr float lowDeg[count]  = {-20, -8, 0, -60, -neckPitchMaxNegativeDegrees, 0};
constexpr float highDeg[count] = {20, 8, 90, 60, neckPitchMaxDegrees, jawMaxDegrees};
constexpr uint16_t pwm[count] = {180, 180, 200, 270, 185, 160};
constexpr uint16_t velocity[count] = {75, 60, 160, 29, 19, 35};
constexpr uint16_t acceleration[count] = {20, 16, 62, 12, 10, 10};
constexpr uint16_t exhibitYawVelocity = 29;
constexpr uint16_t exhibitPitchVelocity = 15;
constexpr uint16_t returnNeckVelocity = 7;
constexpr uint16_t exhibitJawPwm = 100;
constexpr uint16_t exhibitJawRecoveryPwm = 120;
constexpr uint16_t exhibitJawVelocity = 6;
constexpr uint8_t exhibitJawStartTicks = 8;
constexpr uint8_t exhibitJawReadyTicks = 12;
constexpr uint8_t exhibitJawRecoveryTicks = 110;
constexpr uint8_t exhibitJawEntryNeckTicks = 11;
constexpr uint8_t exhibitJawTrimTicks = 11;
constexpr uint8_t exhibitJawTrimOpenTicks = 34;
constexpr uint8_t exhibitJawLagTicks = 18;
constexpr uint32_t exhibitJawTrimAfterMs = 1550;
constexpr uint32_t exhibitJawRecoveryMs = 2400;
static_assert(sizeof(calibration)/sizeof(calibration[0]) == count, "One calibration row per axis");
constexpr uint32_t busBaud = 57600;
constexpr uint32_t busTimeoutMs = 14;
constexpr uint32_t timeoutMs = 400;
constexpr uint32_t goalPeriodMs = 60;
constexpr uint32_t reportMs = 120;
constexpr uint8_t holdTolerance = 3;
constexpr uint8_t positionTolerance = 8;
constexpr uint8_t jawPositionTolerance = 11;
constexpr uint8_t eyeCalibrationTicks[] = {4096u*20u/360u-positionTolerance,
                                           4096u*8u/360u-positionTolerance};
constexpr uint16_t neckYawCalibrationTicks = 659;
constexpr uint8_t hardwareAlert = 0x80;
constexpr uint8_t neckYawAxis = 3, neckPitchAxis = 4;
constexpr uint8_t trackerMask = (1u<<trackerCount)-1;
constexpr uint8_t neckNeutralTolerance = 4096u*2u/360u;  // Direct drive, up to 2 degrees.
constexpr uint8_t jawDemoMask = (1u<<neckYawAxis)|(1u<<neckPitchAxis)|(1u<<trackerCount);
constexpr uint32_t jawDemoCenteringMs = 2*reportMs;
constexpr uint32_t jawSettlingMs = 600;
constexpr uint8_t jawFollowTolerance = 4096u*3u/360u;
constexpr uint8_t jawLagReportsRequired = 2;

struct Register {
  uint16_t address;
  uint8_t size;
};

// Protocol 2.0 control-table addresses shared by the XL330 and XL430.
constexpr Register modelNumber{0, 2}, driveMode{10, 1}, operatingMode{11, 1};
constexpr Register startupConfiguration{60, 1};
constexpr Register torqueEnable{64, 1}, statusReturnLevel{68, 1};
constexpr Register goalPwm{100, 2}, profileAcceleration{108, 4}, profileVelocity{112, 4};
constexpr Register goalPosition{116, 4}, presentPosition{132, 4};

enum class Transfer { ok, bus, servo };
enum class NeckProfile { normal, exhibit, returning };
enum class ArmMode { normal, jawDemo, exhibit };

struct AxisStatus {
  int32_t model = -1;
  int32_t mode = -1;
  int32_t drive = -1;
  int32_t returnLevel = -1;
  int32_t torque = -1;
  int32_t position = -1;
};

void drainBusInput() {
  for (int buffered=Serial1.available();buffered>0;buffered--) Serial1.read();
}

class ServoBus : public Dynamixel2Arduino {
public:
  using Dynamixel2Arduino::Dynamixel2Arduino;

  bool readVerified(uint8_t id, Register reg, int32_t& value, uint8_t& status) {
    uint8_t request[] = {static_cast<uint8_t>(reg.address),
                         static_cast<uint8_t>(reg.address>>8),reg.size,0};
    uint8_t response[4] = {};
    if (!verifiedTransaction(id,DXL_INST_READ,request,sizeof(request),response,reg.size,status)) {
      return false;
    }
    uint32_t decoded=0;
    for (uint8_t n=0;n<reg.size;n++) decoded|=uint32_t(response[n])<<(8*n);
    value=static_cast<int32_t>(decoded);
    return true;
  }

  bool requestReboot(uint8_t id) {
    uint8_t status=0;
    return verifiedTransaction(id,DXL_INST_REBOOT,nullptr,0,nullptr,0,status);
  }

private:
  bool verifiedTransaction(uint8_t id, uint8_t instruction, uint8_t* request, uint8_t requestSize,
                         uint8_t* response, uint8_t responseSize, uint8_t& status) {
    // The library's high-level read and reboot methods do not check the reply's ID.
    drainBusInput();
    if (!txInstPacket(id,instruction,request,requestSize)) return false;
    const auto* reply=rxStatusPacket(response,responseSize,busTimeoutMs);
    if (!reply || reply->id!=id || reply->recv_param_len!=responseSize) return false;
    status=reply->err_idx;
    return status==0 || status==hardwareAlert;
  }
};

ServoBus dxl(Serial1, -1);
uint8_t armed = 0;
bool faulted = false;
bool moving = false;
bool pending = false;
bool jawDemoActive = false;
bool exhibitJawHold = false;
bool exhibitJawClosing = false;
bool exhibitJawTrimApplied = false;
NeckProfile appliedProfile = NeckProfile::normal;
NeckProfile queuedProfile = NeckProfile::normal;
uint32_t lastCommand = 0;
uint32_t lastGoal = 0;
uint32_t lastReport = 0;
uint32_t jawDemoCenteringSince = 0;
uint32_t jawTargetSince = 0;
uint8_t jawLagReports = 0;
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
  return !exhibitJawHold && axisEnabled(armed, trackerCount) ? count : trackerCount;
}

float limited(float value, float lo, float hi) {
  if (value < lo) return lo;
  if (value > hi) return hi;
  return value;
}

bool pitchEndpointsInRange(const Calibration& c) {
  return abs(c.low-c.zero)<=neckPitchMaxNegativeTicks && abs(c.high-c.zero)<=neckPitchMaxPositiveTicks;
}

bool eyeEndpointsInRange(uint8_t i, const Calibration& c) {
  return i>=sizeof(eyeCalibrationTicks) ||
         (abs(c.low-c.zero)<=eyeCalibrationTicks[i] && abs(c.high-c.zero)<=eyeCalibrationTicks[i]);
}

bool yawEndpointsInRange(const Calibration& c) {
  return abs(c.low-c.zero)<=neckYawCalibrationTicks && abs(c.high-c.zero)<=neckYawCalibrationTicks;
}

bool validCalibration(uint8_t i) {
  const auto& c = calibration[i];
  if (c.low<0 || c.low>4095 || c.zero<0 || c.zero>4095 || c.high<0 || c.high>4095) {
    return false;
  }
  if (i==blinkAxis && abs(c.high-c.zero)>blinkTravelTicks) return false;
  if (i==trackerCount && abs(c.high-c.zero)>jawMaxTravelTicks) return false;
  if (i==neckPitchAxis && !pitchEndpointsInRange(c)) return false;
  if (i==neckYawAxis && !yawEndpointsInRange(c)) return false;
  if (!eyeEndpointsInRange(i,c)) return false;
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

bool modelMatches(uint8_t i, int32_t found) {
  return found==model[i] || (i==blinkAxis && found==blinkFastModel);
}

bool readAxis(uint8_t i, AxisStatus& status) {
  const uint8_t id=i+1;
  if (readRegister(id,modelNumber,status.model)!=Transfer::ok) return false;
  if (!modelMatches(i,status.model)) return true;
  return readRegister(id,operatingMode,status.mode)==Transfer::ok &&
         readRegister(id,driveMode,status.drive)==Transfer::ok &&
         readRegister(id,statusReturnLevel,status.returnLevel)==Transfer::ok &&
         readRegister(id,torqueEnable,status.torque)==Transfer::ok &&
         readRegister(id,presentPosition,status.position)==Transfer::ok;
}

bool jawNearClosed(int32_t position) {
  return position>=0 && position<=4095 &&
         abs(position-calibration[trackerCount].zero)<=exhibitJawStartTicks;
}

int32_t jawOpening(int32_t position) {
  const auto& c=calibration[trackerCount];
  return (position-c.zero)*(c.high>c.zero ? 1 : -1);
}

bool jawCanClose(int32_t position, uint8_t closedTolerance=exhibitJawStartTicks) {
  const int32_t opening=jawOpening(position);
  return position>=0 && position<=4095 && opening>=-closedTolerance && opening<=exhibitJawRecoveryTicks;
}

bool readyToArm(uint8_t i, const AxisStatus& status, bool checkJawClosed=false) {
  return modelMatches(i,status.model) && status.mode==3 && (status.drive&12)==0 &&
         status.returnLevel==2 && status.torque==0 &&
         (checkJawClosed ? jawCanClose(status.position) : inside(i,status.position,0));
}

void cancelMotion() {
  pending=false;
  moving=false;
  queuedProfile=appliedProfile;
}

bool releaseAxis(uint8_t i) {
  int32_t torque=-1;
  writeRegister(i+1,torqueEnable,0);
  if (readRegister(i+1,torqueEnable,torque)!=Transfer::ok || torque!=0) return false;
  armed&=~(1u<<i);
  return true;
}

void release() {
  cancelMotion();
  jawDemoActive=false;
  exhibitJawHold=false;
  exhibitJawClosing=false;
  for (uint8_t i=0;i<count;i++) {
    if (!axisEnabled(armed,i)) continue;
    releaseAxis(i);
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

void resetJawFollowing() {
  jawTargetSince=millis();
  jawLagReports=0;
}

bool holdAxes(bool includeJaw=true) {
  bool held=true;
  for (uint8_t i=0;i<count;i++) {
    if (!axisEnabled(armed,i) || (!includeJaw && i==trackerCount)) continue;
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
    if (i==trackerCount) resetJawFollowing();
  }
  return held;
}

void stopOnFault(const char* reason, uint8_t id=0) {
  latchFault(reason,id);
  exhibitJawClosing=false;
  const bool releaseJaw=id==count || jawDemoActive || exhibitJawHold;
  if (releaseJaw && axisEnabled(armed,trackerCount) && !releaseAxis(trackerCount)) {
    printAxisError("ERROR JAW_RELEASE_UNCONFIRMED",count);
  }
  if (!holdAxes(!releaseJaw)) Serial.println("ERROR HOLD_UNCONFIRMED");
}

bool freeze() {
  if (exhibitJawClosing) {
    stopOnFault("EXHIBIT_JAW_CLOSE_CANCELLED",count);
    return false;
  }
  cancelMotion();
  if (holdAxes(!exhibitJawHold)) return true;
  if (jawDemoActive || exhibitJawHold) stopOnFault("HOLD_UNCONFIRMED");
  else latchFault("HOLD_UNCONFIRMED");
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

bool readNeckRegister(uint8_t id, Register reg, int32_t& value) {
  for (uint8_t attempt=0;attempt<2;attempt++) {
    uint8_t status=0;
    if (dxl.readVerified(id,reg,value,status)) return status==0;
    if (!retryable(transferResult(false))) break;
  }
  return false;
}

bool writeVerifiedRegister(uint8_t id, Register reg, int32_t value) {
  int32_t confirmed=-1;
  return writeRegister(id,reg,value)==Transfer::ok &&
         readNeckRegister(id,reg,confirmed) && confirmed==value;
}

bool neckNeutral(uint8_t i, int32_t ticks, uint8_t tolerance=neckNeutralTolerance) {
  return ticks>=0 && ticks<=4095 && abs(ticks-calibration[i].zero)<=tolerance;
}

bool checkNeckNeutral(uint8_t tolerance=neckNeutralTolerance) {
  for (uint8_t i=neckYawAxis;i<=neckPitchAxis;i++) {
    const uint8_t id=i+1;
    int32_t measuredModel=-1, position=-1;
    if (!validCalibration(i) || !readNeckRegister(id,modelNumber,measuredModel) || measuredModel!=model[i] ||
        !readNeckRegister(id,presentPosition,position) || position<0 || position>4095) {
      printAxisError("ERROR NECK_CHECK",id);
      return false;
    }
    if (!neckNeutral(i,position,tolerance)) {
      printAxisError("ERROR NECK_NOT_NEUTRAL",id);
      return false;
    }
  }
  return true;
}

bool verifyNeutralNeckAxis(uint8_t i) {
  const uint8_t id=i+1;
  int32_t torque=-1;
  if (!readNeckRegister(id,presentPosition,raw[i]) || !readNeckRegister(id,torqueEnable,torque)) {
    stopOnFault(exhibitJawClosing ? "EXHIBIT_JAW_NECK_READ" : "JAW_DEMO_NECK_READ",id);
    return false;
  }
  if (torque!=1 || !neckNeutral(i,raw[i])) {
    const char* reason=exhibitJawClosing ? "EXHIBIT_JAW_NECK_TORQUE" : "JAW_DEMO_NECK_TORQUE";
    stopOnFault(torque!=1 ? reason : "NECK_NOT_NEUTRAL",id);
    return false;
  }
  return true;
}

uint16_t neckVelocity(uint8_t axis, NeckProfile profile) {
  if (profile==NeckProfile::returning) return returnNeckVelocity;
  if (profile==NeckProfile::exhibit) return axis==neckYawAxis ? exhibitYawVelocity : exhibitPitchVelocity;
  return velocity[axis];
}

bool applyNeckProfile() {
  for (uint8_t i=neckYawAxis;i<=neckPitchAxis;i++) {
    const uint8_t id=i+1;
    const uint16_t wanted=neckVelocity(i,queuedProfile);
    int32_t confirmed=-1;
    if ((wanted!=neckVelocity(i,appliedProfile) && writeRegister(id,profileVelocity,wanted)!=Transfer::ok) ||
        !readNeckRegister(id,profileVelocity,confirmed) || confirmed!=wanted) {
      stopOnFault("NECK_PROFILE",id);
      return false;
    }
  }
  appliedProfile=queuedProfile;
  return true;
}

void emitGoals() {
  const bool profileChanged=queuedProfile!=appliedProfile;
  if (profileChanged) {
    if (!applyNeckProfile()) return;
    if (moving && static_cast<uint32_t>(millis()-lastCommand)>=timeoutMs) {
      freeze();
      return;
    }
  }
  for (uint8_t i=0;i<count;i++) {
    const bool refreshNeck=profileChanged && (i==neckYawAxis || i==neckPitchAxis);
    if (!axisEnabled(armed,i) || (targets[i]==queued[i] && !refreshNeck)) continue;
    if (jawDemoActive && i==trackerCount) {
      if (static_cast<uint32_t>(millis()-jawDemoCenteringSince)<jawDemoCenteringMs) return;
      if (!verifyNeutralNeckAxis(neckYawAxis) || !verifyNeutralNeckAxis(neckPitchAxis)) return;
    }
    Transfer result=writeRegister(i+1,goalPosition,queued[i]);
    if (result!=Transfer::ok) {
      stopOnFault(result==Transfer::servo ? "WRITE_STATUS" : "WRITE_BUS",i+1);
      return;
    }
    targets[i]=queued[i];
    if (i==trackerCount) resetJawFollowing();
  }
  pending=false;
}

void report() {
  for (uint8_t i=0;i<count;i++) {
    if (!axisEnabled(armed,i)) continue;
    if ((jawDemoActive || exhibitJawClosing) && (i==neckYawAxis || i==neckPitchAxis)) {
      if (!verifyNeutralNeckAxis(i)) return;
    } else {
      Transfer result=readRegister(i+1,presentPosition,raw[i]);
      if (result!=Transfer::ok) {
        stopOnFault(result==Transfer::servo ? "READ_STATUS" : "READ_BUS",i+1);
        return;
      }
    }
    const bool closing=i==trackerCount && exhibitJawClosing;
    const uint8_t closedTolerance=exhibitJawTrimApplied ? exhibitJawTrimTicks : exhibitJawStartTicks;
    if (!(closing ? jawCanClose(raw[i],closedTolerance) :
          inside(i,raw[i],i==trackerCount ? jawPositionTolerance : positionTolerance))) {
      stopOnFault("POSITION_LIMIT",i+1);
      return;
    }
    if (i==trackerCount) {
      const bool settling=static_cast<uint32_t>(millis()-jawTargetSince)<jawSettlingMs;
      const uint8_t tolerance=exhibitJawHold ? exhibitJawLagTicks : jawFollowTolerance;
      if (closing) {
        int32_t torque=-1;
        if (!readNeckRegister(i+1,torqueEnable,torque) || torque!=1) {
          stopOnFault("EXHIBIT_JAW_TORQUE",i+1);
          return;
        }
        const int32_t opening=jawOpening(raw[i]);
        const uint32_t elapsed=static_cast<uint32_t>(millis()-jawTargetSince);
        if (abs(opening)<=exhibitJawReadyTicks) {
          const int32_t zero=calibration[i].zero;
          if (targets[i]!=zero && !writeVerifiedRegister(i+1,goalPosition,zero)) {
            stopOnFault("EXHIBIT_JAW_TARGET",i+1);
            return;
          }
          targets[i]=queued[i]=zero;
          if (!writeVerifiedRegister(i+1,goalPwm,exhibitJawPwm)) {
            stopOnFault("EXHIBIT_JAW_PWM",i+1);
            return;
          }
          exhibitJawClosing=false;
          resetJawFollowing();
          Serial.println("ARMED_EXHIBIT 31");
        } else if (elapsed>=exhibitJawRecoveryMs) {
          stopOnFault("EXHIBIT_JAW_CLOSE_TIMEOUT",i+1);
          return;
        } else if (!exhibitJawTrimApplied && elapsed>=exhibitJawTrimAfterMs && opening<=exhibitJawTrimOpenTicks) {
          // Closing startup only. The signed trim stays inside the measured tooth clearance.
          exhibitJawTrimApplied=true;
          const auto& c=calibration[i];
          const int32_t aim=c.zero+(c.high>c.zero ? -exhibitJawTrimTicks : exhibitJawTrimTicks);
          if (aim>=0 && aim<=4095) {
            if (!writeVerifiedRegister(i+1,goalPosition,aim)) {
              stopOnFault("EXHIBIT_JAW_TARGET",i+1);
              return;
            }
            targets[i]=aim;
          }
        }
      }
      if (closing || settling || abs(raw[i]-targets[i])<=tolerance) {
        jawLagReports=0;
      } else if (++jawLagReports>=jawLagReportsRequired) {
        stopOnFault("JAW_FOLLOW_TIMEOUT",i+1);
        return;
      }
    }
  }
  Serial.print("STATE ");
  Serial.print(exhibitJawHold ? trackerMask : armed);
  for (uint8_t i=0;i<commandAxisCount();i++) {
    Serial.print(' ');
    Serial.print(axisEnabled(armed,i)?toDegrees(i,raw[i]):0.0f,3);
  }
  Serial.println();
}

void arm(uint8_t mask, ArmMode mode=ArmMode::normal) {
  const bool startJawDemo=mode==ArmMode::jawDemo;
  const bool startExhibit=mode==ArmMode::exhibit;
  const auto& jaw=calibration[trackerCount];
  if (startExhibit && jaw.low==-1 && jaw.zero==-1 && jaw.high==-1) mask=trackerMask;
  const bool armExhibitJaw=startExhibit && axisEnabled(mask,trackerCount);
  if (faulted) {
    Serial.println("LOCKED RELEASE_AFTER_FAULT");
    return;
  }
  if (jawDemoActive || (startJawDemo && armed!=0)) {
    Serial.println("ERROR RELEASE_BEFORE_JAW_DEMO_CHANGE");
    return;
  }
  if (exhibitJawHold || (startExhibit && armed!=0)) {
    Serial.println("ERROR RELEASE_BEFORE_EXHIBIT_CHANGE");
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
        const auto& c=calibration[i];
        const char* error="LOCKED CALIBRATE";
        if (i==blinkAxis && c.low>=0 && c.zero>=0 && c.high>=0 && abs(c.high-c.zero)>blinkTravelTicks)
          error="LOCKED BLINK_CALIBRATION_RANGE";
        if (i==trackerCount && abs(c.high-c.zero)>jawMaxTravelTicks) error="LOCKED JAW_CALIBRATION_RANGE";
        if (i==neckPitchAxis && !pitchEndpointsInRange(c)) error="LOCKED PITCH_CALIBRATION_RANGE";
        if (i==neckYawAxis && c.low>=0 && c.zero>=0 && c.high>=0 && !yawEndpointsInRange(c))
          error="LOCKED YAW_CALIBRATION_RANGE";
        if (c.low>=0 && c.zero>=0 && c.high>=0 && !eyeEndpointsInRange(i,c))
          error="LOCKED EYE_CALIBRATION_RANGE";
        printAxisError(error,i+1);
        return;
      }
    }
    if (startJawDemo && !checkNeckNeutral()) return;
    bool fastBlink=false;
    for (uint8_t i=0;i<count;i++) {
      if (!axisEnabled(mask,i)) continue;
      AxisStatus status;
      const bool closedJaw=armExhibitJaw && i==trackerCount;
      const bool read=readAxis(i,status);
      if (!read || !readyToArm(i,status,closedJaw)) {
        const bool jawOpen=closedJaw && read && status.position>=0 && !jawCanClose(status.position);
        printAxisError(jawOpen ? "LOCKED EXHIBIT_JAW_RANGE" : "LOCKED SERVO_CHECK",i+1);
        return;
      }
      if (closedJaw && !jawNearClosed(status.position) && !checkNeckNeutral(exhibitJawEntryNeckTicks)) return;
      if (i==blinkAxis) fastBlink=status.model==blinkFastModel;
    }
    for (uint8_t i=0;i<count;i++) {
      if (!axisEnabled(mask,i)) continue;
      const uint8_t id=i+1;
      const bool closedJaw=armExhibitJaw && i==trackerCount;
      const uint16_t wantedPwm=closedJaw ? exhibitJawPwm : i==blinkAxis && fastBlink ? blinkFastPwm : pwm[i];
      const uint16_t wantedVelocity=closedJaw ? exhibitJawVelocity : velocity[i];
      if (!writeVerifiedRegister(id,goalPwm,wantedPwm) || writeRegister(id,profileVelocity,wantedVelocity)!=Transfer::ok ||
          writeRegister(id,profileAcceleration,acceleration[i])!=Transfer::ok) {
        printAxisError("LOCKED ARM_CONFIG",id);
        return;
      }
      if (closedJaw) {
        int32_t confirmed=-1;
        if (!readNeckRegister(id,profileVelocity,confirmed) || confirmed!=wantedVelocity ||
            !readNeckRegister(id,profileAcceleration,confirmed) || confirmed!=acceleration[i]) {
          printAxisError("LOCKED ARM_CONFIG",id);
          return;
        }
      }
    }
    exhibitJawHold=armExhibitJaw;
    for (uint8_t i=0;i<count;i++) {
      if (!axisEnabled(mask,i)) continue;
      const uint8_t id=i+1;
      const bool demoNeck=startJawDemo && (i==neckYawAxis || i==neckPitchAxis);
      const bool closedJaw=armExhibitJaw && i==trackerCount;
      const bool positionRead=demoNeck ? readNeckRegister(id,presentPosition,raw[i])
                                      : readRegister(id,presentPosition,raw[i])==Transfer::ok;
      const int32_t goal=closedJaw ? calibration[i].zero : raw[i];
      const bool recoverJaw=closedJaw && positionRead && !jawNearClosed(raw[i]);
      if (recoverJaw && !checkNeckNeutral(exhibitJawEntryNeckTicks)) {
        stopOnFault("EXHIBIT_JAW_CLOSE_CANCELLED",i+1);
        return;
      }
      const bool positionAllowed=closedJaw ? jawCanClose(raw[i]) : inside(i,raw[i],0);
      if (!positionRead || (demoNeck && !neckNeutral(i,raw[i])) || !positionAllowed ||
          (recoverJaw && !writeVerifiedRegister(id,goalPwm,exhibitJawRecoveryPwm)) ||
          (closedJaw ? !writeVerifiedRegister(id,goalPosition,goal)
                     : writeRegister(id,goalPosition,goal)!=Transfer::ok)) {
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
      targets[i]=queued[i]=goal;
      if (recoverJaw) {
        exhibitJawClosing=true;
        exhibitJawTrimApplied=false;
      }
    }
    appliedProfile=NeckProfile::normal;
  }
  cancelMotion();
  jawDemoActive=startJawDemo;
  if (jawDemoActive) {
    for (uint8_t i=0;i<count;i++) queued[i]=targets[i];
    queued[neckYawAxis]=calibration[neckYawAxis].zero;
    queued[neckPitchAxis]=calibration[neckPitchAxis].zero;
    emitGoals();
    if (faulted) return;
    jawDemoCenteringSince=millis();
  }
  lastGoal=static_cast<uint32_t>(millis())-goalPeriodMs;
  lastReport=millis();
  resetJawFollowing();
  if (!exhibitJawClosing) {
    Serial.print(startJawDemo ? "ARMED_JAW_DEMO " : startExhibit ? "ARMED_EXHIBIT " : "ARMED ");
    Serial.println(startExhibit ? trackerMask : mask);
  }
  if (startExhibit && !armExhibitJaw) Serial.println("EXHIBIT_JAW_UNCALIBRATED");
  report();
}

void rebootAxis(uint8_t i) {
  const uint8_t id=i+1;
  const bool targetArmed=axisEnabled(armed,i);
  if (targetArmed && !faulted) {
    printAxisError("ERROR REBOOT_WHILE_ARMED",id);
    return;
  }
  int32_t value=0;
  uint8_t status=0;
  if (!dxl.readVerified(id,modelNumber,value,status) || !modelMatches(i,value) ||
      !dxl.readVerified(id,startupConfiguration,value,status)) {
    printAxisError("ERROR REBOOT_CHECK",id);
    return;
  }
  if (value!=0) {
    printAxisError("ERROR REBOOT_STARTUP_CONFIG",id);
    return;
  }
  if (!dxl.readVerified(id,torqueEnable,value,status)) {
    printAxisError("ERROR REBOOT_CHECK",id);
    return;
  }
  if (targetArmed && status!=hardwareAlert) {
    printAxisError("ERROR REBOOT_WHILE_ARMED",id);
    return;
  }
  if (value!=0) {
    printAxisError("ERROR REBOOT_TORQUE_ON",id);
    return;
  }
  if (!dxl.requestReboot(id)) {
    printAxisError("ERROR REBOOT",id);
    return;
  }
  Serial.print("REBOOTED ");
  Serial.println(id);
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
  if (!strcmp(text,"EXHIBIT?")) {
    Serial.println("R5B1_EXHIBIT 1");
    return;
  }
  if (!strcmp(text,"EXHIBIT_HOLD?")) {
    Serial.println("R5B1_EXHIBIT_HOLD 1");
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
  if (!strcmp(text,"CHECK_NECK")) {
    if (moving) Serial.println("ERROR CHECK_DURING_MOVE");
    else if (checkNeckNeutral()) Serial.println("NECK_NEUTRAL");
    return;
  }
  if (!strncmp(text,"CHECK ",6)) {
    long id=0;
    if (moving) Serial.println("ERROR CHECK_DURING_MOVE");
    else if (getUnsigned(text+6,1,count,id)) checkAxis(id-1);
    else Serial.println("ERROR CHECK_ID");
    return;
  }
  if (!strncmp(text,"REBOOT ",7)) {
    long id=0;
    if (moving) Serial.println("ERROR REBOOT_DURING_MOVE");
    else if (getUnsigned(text+7,1,count,id)) rebootAxis(id-1);
    else Serial.println("ERROR REBOOT_ID");
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
  if (!strcmp(text,"ARM_JAW_DEMO")) {
    arm(jawDemoMask,ArmMode::jawDemo);
    return;
  }
  if (!strcmp(text,"ARM_EXHIBIT")) {
    arm((1u<<count)-1,ArmMode::exhibit);
    return;
  }
  if (armed==0 || faulted) return;
  if (exhibitJawClosing) {
    Serial.println("ERROR EXHIBIT_JAW_CLOSING");
    return;
  }

  NeckProfile profile=NeckProfile::normal;
  const char* next=nullptr;
  if (!strncmp(text,"GO ",3)) next=text+3;
  else if (!strncmp(text,"GO_EXHIBIT ",11)) {
    profile=NeckProfile::exhibit;
    next=text+11;
  } else if (!strncmp(text,"GO_RETURN ",10)) {
    profile=NeckProfile::returning;
    next=text+10;
  } else return;
  if (profile!=NeckProfile::normal && armed!=trackerMask && !exhibitJawHold) {
    Serial.println("ERROR EXHIBIT_MASK");
    return;
  }
  if (profile==NeckProfile::normal && exhibitJawHold) {
    Serial.println("ERROR EXHIBIT_PROFILE");
    return;
  }

  float goals[count];
  uint8_t active = commandAxisCount();
  for (uint8_t i=0;i<active;i++) {
    char* end=nullptr;
    goals[i]=strtof(next,&end);
    if (end==next || !isfinite(goals[i])) return;
    if (i+1<active && *end!=' ') return;
    next=end;
  }
  while (*next==' ') next++;
  if (*next!='\0') return;
  if (active==count && (goals[trackerCount]<0 || goals[trackerCount]>jawMaxDegrees)) {
    printAxisError("ERROR JAW_GOAL_RANGE",count);
    return;
  }
  if (jawDemoActive && (goals[neckYawAxis]!=0 || goals[neckPitchAxis]!=0)) {
    stopOnFault("JAW_DEMO_NECK_GOAL");
    return;
  }

  for (uint8_t i=0;i<active;i++) {
    if (!axisEnabled(armed,i)) continue;
    queued[i]=toTicks(i,goals[i]);
  }
  queuedProfile=profile;
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
