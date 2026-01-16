import sys

def clear_terminal():
    # ANSI clear screen + move cursor to top-left
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def get_next_suffix(r, suffix):
    if r == 1: return suffix
    elif r > 1: return str(int(suffix)+900) # hard implementation based on observation, might fail upon rule changes


def get_next_quarter(ts): # Given a timestamp, return the next quarter-hour timestamp.
    minute = (ts.minute // 15 + 1) * 15
    if minute == 60:
        return ts.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else:
        return ts.replace(minute=minute, second=0, microsecond=0)
