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
    uint32_t readWait = 0;

    void begin(uint32_t) {}
    int available() const { return static_cast<int>(input.size()); }
    int read() {
        if (input.empty()) {
            if (readWait) {
                --readWait;
                ++clockMs;
            }
            return -1;
        }
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

enum DXLLibErrorCode_t {
    DXL_LIB_OK,
    DXL_LIB_ERROR_TIMEOUT,
    DXL_LIB_ERROR_CRC,
    DXL_LIB_ERROR_WRONG_PACKET,
    DXL_LIB_ERROR_PORT_WRITE,
    DXL_LIB_ERROR_BUFFER_OVERFLOW,
    DXL_LIB_ERROR_LENGTH,
    DXL_LIB_ERROR_INVAILD_ID,
    DXL_LIB_PROCEEDING,
};

enum {
    DXL2_0_ERR_CRC_ERROR = 3,
    DXL_INST_READ = 2,
    DXL_INST_WRITE = 3,
    DXL_INST_REBOOT = 8,
    DXL_INST_STATUS = 0x55,
};

struct InfoToParseDXLPacket_t {
    uint8_t header[4];
    uint8_t header_cnt;
    uint8_t reserved;
    uint8_t inst_idx;
    uint8_t id;
    uint8_t err_idx;
    uint16_t recv_param_len;
    uint8_t* parameters;
    uint16_t capacity;
    uint8_t field;
    uint8_t length;
};

inline DXLLibErrorCode_t begin_parse_dxl_packet(InfoToParseDXLPacket_t* packet, uint8_t,
                                               uint8_t* parameters, uint16_t capacity) {
    packet->parameters = parameters;
    packet->capacity = capacity;
    return DXL_LIB_OK;
}

inline DXLLibErrorCode_t parse_dxl_packet(InfoToParseDXLPacket_t* packet, uint8_t byte) {
    // The simulator frames decoded fields. The board build uses the vendor wire parser.
    switch (packet->field) {
        case 0: packet->id = byte; break;
        case 1: packet->err_idx = byte; break;
        case 2: packet->length = byte; break;
        default:
            if (packet->recv_param_len == packet->length) {
                packet->inst_idx = byte;
                return byte == DXL_INST_STATUS ? DXL_LIB_OK : DXL_LIB_ERROR_CRC;
            }
            if (packet->recv_param_len > packet->capacity) return DXL_LIB_ERROR_BUFFER_OVERFLOW;
            packet->parameters[packet->recv_param_len++] = byte;
            break;
    }
    ++packet->field;
    return DXL_LIB_PROCEEDING;
}

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
    DXLLibErrorCode_t libError = DXL_LIB_OK;
    uint8_t status = 0;

    Dynamixel2Arduino(MockSerial& serial, int) : serial(serial) {}
    void begin(uint32_t) {}
    void setPortProtocolVersion(float) {}
    DXLLibErrorCode_t getLastLibErrCode() const { return libError; }

    std::string exchange(char direction, uint8_t id, uint16_t address, int32_t value) {
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
        if (result == "alert_denied" || result == "wrong_id_alert") status = 0x87;
        if (result == "denied" || result == "wrong_id_denied") status = 7;
        events.push_back({direction, id, address, value, result, clockMs});
        return result;
    }

protected:
    void setLastLibErrCode(DXLLibErrorCode_t error) { libError = error; }

    bool txInstPacket(uint8_t id, uint8_t instruction, uint8_t* parameters, uint16_t size) {
        if (instruction == DXL_INST_REBOOT && size == 0) {
            frame(id, reboot(id), 0, 0);
            return true;
        }
        if (size < 2) return false;
        const uint16_t address = parameters[0] | (uint16_t(parameters[1]) << 8);
        auto& servo = motors.at(id-1);
        if (instruction == DXL_INST_READ && size == 4) {
            const uint16_t width = parameters[2] | (uint16_t(parameters[3]) << 8);
            if (width != registerSize(address)) return false;
            const int32_t value = servo.registers.at(address);
            const auto result = exchange('r', id, address, value);
            const bool noData = result == "short" || (status & 0x7f);
            frame(id, result, noData ? 0 : width, value);
            return true;
        }
        if (instruction != DXL_INST_WRITE || size != registerSize(address) + 2) return false;
        uint32_t decoded = 0;
        for (uint16_t n = 2; n < size; ++n) decoded |= uint32_t(parameters[n]) << (8*(n-2));
        const int32_t value = static_cast<int32_t>(decoded);
        const auto result = exchange('w', id, address, value);
        if (result == "ok" || result == "lost" || result == "alert") {
            servo.registers.at(address) = value;
            if (address == 116 && servo.registers.at(64) != 0 && servo.follows) servo.registers.at(132) = value;
        }
        frame(id, result, result == "extra" ? 1 : 0, 0);
        return true;
    }

private:
    MockSerial& serial;

    void frame(uint8_t id, const std::string& result, uint8_t length, int32_t value) {
        serial.readWait = 0;
        if (result == "timeout" || result == "lost") {
            serial.readWait = 14;
            return;
        }
        serial.input.push_back(result.rfind("wrong_id", 0) == 0 ? id % 6 + 1 : id);
        serial.input.push_back(status);
        serial.input.push_back(length);
        for (uint8_t n = 0; n < length; ++n) serial.input.push_back(uint32_t(value) >> (8*n));
        if (result == "truncated") serial.readWait = 14;
        else serial.input.push_back(result == "crc" ? 0xfe : DXL_INST_STATUS);
    }

    std::string reboot(uint8_t id) {
        const auto result = exchange('b', id, 0, 0);
        if (result != "ok" && result != "lost" && result != "alert") return result;
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
        return result;
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
