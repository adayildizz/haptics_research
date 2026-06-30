# Hardware
CARRIER_FREQUENCY = 125       # Hz
PEAK_VOLTAGE = 4.0            # Vpp, before external amplification
MIN_VOLTAGE = 0.0             # V when the electroadhesion signal is off
DISABLE_OUTPUT_WHEN_OFF = True
OFFSET_V = 0
WAVE_SQUARE = "SQU"
VISA_ADDRESS = "TCPIP0::169.254.2.20::inst0::INSTR"

# Display/input calibration
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
USE_FULLSCREEN = False
FPS = 60
MONITOR_DIAGONAL_INCH = 21.5
FALLBACK_MM_TO_PX = 12.0
CALIBRATION_FILENAME = "display_calibration.json"
HAPTIC_SURFACE_CALIBRATION_FILENAME = "haptic_surface_calibration.json"
LOCK_WINDOW_TO_FRAME_SIZE = True
FRAME_ACTIVE_WIDTH_MM = 200.0
FRAME_ACTIVE_HEIGHT_MM = 100.0

# Stimulus levels (mm)
WIDTH_LEVELS = [2, 6, 10, 14]
HEIGHT_LEVELS = [2, 6, 10, 14]

# Height staircase. These are fractions of the current reference height.
DH_START = 2.0                # 200% of reference height
DH_MIN = 0.5                  # 50% of reference height
DH_STEP = 0.1                 # 10% step size

# Stopping criterion (Sun et al., 2023)
N_REVERSALS = 12
N_REVERSALS_AVERAGED = 8

# Trial rendering
INTER_BAR_GAP_MM = 40.0
MIN_SPEED_MM_S = 1.0
MAX_SIGNAL_DURATION_S = 2.0
