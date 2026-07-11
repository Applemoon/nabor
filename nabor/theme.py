"""Gruvbox dark palette."""

BG = "#282828"
BG1 = "#3c3836"
BG2 = "#504945"
FG = "#ebdbb2"       # typed text
GRAY = "#7c6f64"     # text not typed yet
DIM = "#665c54"      # ¶ marks and other furniture
ORANGE = "#fe8019"   # cursor
RED = "#cc241d"      # background of the error tail
YELLOW = "#fabd2f"   # chapter title
GREEN = "#b8bb26"
AQUA = "#8ec07c"
BLUE = "#83a598"

TYPED = FG
UNTYPED = GRAY
CURSOR_BLOCK = f"{BG} on {ORANGE}"
CURSOR_LINE = f"{ORANGE} underline"
MISTAKE = f"{FG} on {RED}"
