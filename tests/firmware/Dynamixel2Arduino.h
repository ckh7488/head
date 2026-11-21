#pragma once

#include <cstddef>
#include <cstdint>
#include <array>
#include <deque>
#include <iomanip>
#include <map>
#include <sstream>
#include <string>
#include <vector>

extern uint32_t clockMs;
inline uint32_t millis() { return clockMs; }

struct MockSerial {
    std::deque<uint8_t> input;
    std::ostringstream output;

    void begin(uint32_t) {}
    int available() const { return static_cast<int>(input.size()); }
    int read() {
        const int value = input.front();
        input.pop_front();
        return value;
    }
    template<class T> void print(T value) { output << value; }
    void print(uint8_t value) { output << unsigned(value); }
    void print(float value, int precision) {
        output << std::fixed << std::setprecision(precision) << value;
    }
    void println() { output << '\n'; }
    template<class T> void println(T value) { print(value); println(); }
};

extern MockSerial Serial, Serial1;

enum {
    DXL_LIB_OK,
    DXL_LIB_ERROR_TIMEOUT,
    DXL_LIB_ERROR_CRC,
    DXL_LIB_ERROR_WRONG_PACKET,
    DXL_LIB_ERROR_PORT_WRITE,
    DXL2_0_ERR_CRC_ERROR = 3,
    DXL_INST_READ = 2,
    DXL_INST_REBOOT = 8,
};

struct InfoToParseDXLPacket {
    uint8_t id;
    uint8_t err_idx;
    uint16_t recv_param_len;
};

struct Motor {
    std::map<uint16_t, int32_t> registers;
    bool follows = true;
};

struct Failure {
    char direction;
    uint8_t id;
    uint16_t address;
    std::string kind;
    unsigned remaining;
};

struct Exchange {
    char direction;
    uint8_t id;
    uint16_t address;
    int32_t value;
    std::string result;
    uint32_t time;
};

struct Dynamixel2Arduino {
    std::array<Motor, 6> motors;
    std::vector<Failure> failures;
    std::vector<Exchange> events;
    int libError = DXL_LIB_OK;
    uint8_t status = 0;

    Dynamixel2Arduino(MockSerial&, int) {}
    void begin(uint32_t) {}
    void setPortProtocolVersion(float) {}
    int getLastLibErrCode() const { return libError; }
    uint8_t getLastStatusPacketError() const { return status; }

    std::string exchange(char direction, uint8_t id, uint16_t address, int32_t value, uint32_t timeout) {
        libError = DXL_LIB_OK;
        status = 0;
        std::string result = "ok";
        for (auto& failure : failures) {
            if (failure.remaining && failure.direction == direction && failure.id == id &&
                failure.address == address) {
                --failure.remaining;
                result = failure.kind;
                break;
            }
        }
        if (result == "timeout" || result == "lost") libError = DXL_LIB_ERROR_TIMEOUT;
        if (result == "crc") libError = DXL_LIB_ERROR_CRC;
        if (result == "instruction_crc") status = DXL2_0_ERR_CRC_ERROR;
        if (result == "alert") status = 0x80;
        if (result == "alert_denied") status = 0x87;
        if (result == "denied") status = 7;
        events.push_back({direction, id, address, value, result, clockMs});
        if (libError == DXL_LIB_ERROR_TIMEOUT) clockMs += timeout;
        return result;
    }

    int32_t read(uint8_t id, uint16_t address, uint16_t size, uint8_t* response,
                 uint16_t capacity, uint32_t timeout) {
        if (size != registerSize(address) || capacity < size) return -1;
        const int32_t value = motors.at(id-1).registers.at(address);
        const auto result = exchange('r', id, address, value, timeout);
        if (libError != DXL_LIB_OK) return -1;
        if (result == "short") return 0;
        for (uint16_t n = 0; n < size; ++n) response[n] = uint32_t(value) >> (8*n);
        return size;
    }

    bool write(uint8_t id, uint16_t address, const uint8_t* request,
               uint16_t size, uint32_t timeout) {
        if (size != registerSize(address)) return false;
        uint32_t decoded = 0;
        for (uint16_t n = 0; n < size; ++n) decoded |= uint32_t(request[n]) << (8*n);
        const auto value = static_cast<int32_t>(decoded);
        const auto result = exchange('w', id, address, value, timeout);
        if (result == "ok" || result == "lost" || result == "alert") {
            auto& servo = motors.at(id-1);
            servo.registers.at(address) = value;
            if (address == 116 && servo.registers.at(64) != 0 && servo.follows) {
                servo.registers.at(132) = value;
            }
        }
        return libError == DXL_LIB_OK && (status == 0 || status == 0x80);
    }

protected:
    bool txInstPacket(uint8_t id, uint8_t instruction, uint8_t* parameters, uint16_t size) {
        instructionId = id;
        instructionType = instruction;
        if (instruction == DXL_INST_REBOOT) return size == 0;
        if (instruction != DXL_INST_READ || size != 4) return false;
        instructionAddress = parameters[0] | (uint16_t(parameters[1]) << 8);
        instructionLength = parameters[2] | (uint16_t(parameters[3]) << 8);
        return true;
    }

    const InfoToParseDXLPacket* rxStatusPacket(uint8_t* response, uint16_t capacity, uint32_t timeout) {
        const auto id = instructionId;
        const auto length = instructionType == DXL_INST_READ
            ? read(id, instructionAddress, instructionLength, response, capacity, timeout)
            : reboot(id, timeout);
        if (length < 0) return nullptr;
        const auto replyId = events.back().result == "wrong_id" ? uint8_t(id % 6 + 1) : id;
        reply = {replyId, status, static_cast<uint16_t>(length)};
        return &reply;
    }

private:
    uint8_t instructionId = 0;
    uint8_t instructionType = 0;
    uint16_t instructionAddress = 0;
    uint16_t instructionLength = 0;
    InfoToParseDXLPacket reply = {};

    int32_t reboot(uint8_t id, uint32_t timeout) {
        const auto result = exchange('b', id, 0, 0, timeout);
        if (result != "ok" && result != "lost" && result != "alert") {
            return libError == DXL_LIB_OK ? 0 : -1;
        }
        auto& registers = motors.at(id-1).registers;
        registers.at(64) = 0;
        registers.at(84) = 400;
        registers.at(100) = 885;
        registers.at(108) = 0;
        registers.at(112) = 0;
        registers.at(116) = registers.at(132);
        for (auto& failure : failures) {
            if (failure.id == id && failure.kind == "alert") failure.remaining = 0;
        }
        return libError == DXL_LIB_OK ? 0 : -1;
    }

    static uint16_t registerSize(uint16_t address) {
        switch (address) {
            case 0: case 84: case 100: return 2;
            case 10: case 11: case 60: case 64: case 68: return 1;
            case 108: case 112: case 116: case 132: return 4;
            default: return 0;
        }
    }
};
