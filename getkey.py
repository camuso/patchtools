# getkey.py

import curses

def main(stdscr):
    stdscr.clear()

    key = stdscr.getch()

    # Check if the alt-key was pressed
    if key == 27:
        b_alt = True
        retkey = "0x1b"
        key = stdscr.getch()
        key = hex(key)
        retkey += str(key)
    else:
        key = hex(key)
        retkey = f"{key}"

    stdscr.addstr(2, 0, f"{retkey}")
    stdscr.refresh()
    print(f"{retkey}")
curses.wrapper(main)

