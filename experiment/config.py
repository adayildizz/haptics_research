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
USE_FULLSCREEN = True
FPS = 60

# The IR frame maps directly to the full 1920 x 1080 display.
IR_FRAME_WIDTH_MM = 249.0
IR_FRAME_HEIGHT_MM = 187.0
IR_FRAME_SCREEN_WIDTH_PX = 1920
IR_FRAME_SCREEN_HEIGHT_PX = 1080

# Physical touch surface placement inside the IR frame.
HAPTIC_SURFACE_WIDTH_MM = 194.0
HAPTIC_SURFACE_HEIGHT_MM = 145.0
HAPTIC_SURFACE_LEFT_PADDING_MM = 23.0
HAPTIC_SURFACE_TOP_PADDING_MM = 16.0

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
