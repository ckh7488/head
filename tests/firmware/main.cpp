#include "R5B1.ino"

#include <iostream>

MockSerial Serial, Serial1;
uint32_t clockMs = 0;

int main() {
    for (uint8_t i = 0; i < count; ++i) {
        const int32_t zero = calibration[i].zero < 0 ? 2048 : calibration[i].zero;
        dxl.motors[i].registers = {
            {0, model[i]}, {10, 0}, {11, 3}, {64, 0}, {68, 2}, {100, 885},
            {108, 0}, {112, 0}, {116, zero}, {132, zero},
        };
    }
    setup();
    std::string line;
    while (std::getline(std::cin, line)) {
        std::istringstream input(line);
        std::string command;
        input >> command;
        if (command == "receive") {
            unsigned value;
            while (input >> std::hex >> value) Serial.input.push_back(value);
            loop();
        } else if (command == "tick") {
            uint32_t elapsed;
            input >> elapsed;
            clockMs += elapsed;
            loop();
        } else if (command == "fail") {
            char direction;
            unsigned id, address, remaining;
            std::string kind;
            input >> direction >> id >> address >> kind >> remaining;
            dxl.failures.push_back({direction, uint8_t(id), uint16_t(address), kind, remaining});
        } else if (command == "set") {
            unsigned id, address;
            int32_t value;
            input >> id >> address >> value;
            dxl.motors.at(id-1).registers.at(address) = value;
        } else if (command == "follow") {
            unsigned id;
            bool follows;
            input >> id >> follows;
            dxl.motors.at(id-1).follows = follows;
        } else if (command == "trace") {
            for (const auto& event : dxl.events) {
                std::cout << event.direction << ' ' << unsigned(event.id) << ' ' << event.address
                          << ' ' << event.value << ' ' << event.result << ' ' << event.time << '\n';
            }
            dxl.events.clear();
        } else if (command == "timing") {
            std::cout << busBaud << ' ' << goalPeriodMs << ' ' << reportMs << ' ' << timeoutMs << '\n';
        } else {
            return 2;
        }
        std::cout << Serial.output.str() << "@done\n" << std::flush;
        Serial.output.str("");
    }
}
