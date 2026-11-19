"""JST EHR-3 lead exits in the neutral assembly, measured in millimetres."""

EHR_LENGTH = 7.1
EHR_WIDTH = 9.5
EHR_HEIGHT = 3.8

# Each entry gives the motor, the cable exit, the pin row and the pull direction.
EHR_PORTS = {
    'ID1EH': ('Part038', (3.2, -20.70, 93.55), (1, 0, 0), (0, 1, 0)),
    'ID2EH': ('Part041', (40.35, -4.80, 142.), (0, 0, 1), (0, -1, 0)),
    'ID3EH': ('Part045', (-17.1, .80, 179.), (0, 0, 1), (0, 1, 0)),
    'ID4EH': ('Part017', (-19.65, 14.1, -62.1), (0, 1, 0), (-1, 0, 0)),
    'ID5EH': ('Part018', (11.8, 19.65, 97.9), (0, 0, -1), (0, 1, 0)),
    'ID6EH': ('Jaw_XL330_M288_Jaw', (-25.5, 5.80, 101.), (0, 0, 1), (0, 1, 0)),
}
