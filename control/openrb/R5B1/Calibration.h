#pragma once

struct Calibration {
  int16_t low;
  int16_t zero;
  int16_t high;
};

constexpr Calibration calibration[] = {
  {-1, -1, -1},
  {-1, -1, -1},
  {-1, -1, -1},
  {-1, -1, -1},
  {-1, -1, -1},
  {-1, -1, -1},
};
