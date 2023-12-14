#include <ncurses.h>

int main(int argc, void *argv[]) {
	initscr(); // initialize the library
	//cbreak();  // disable line buffering
	raw();
	keypad(stdscr, TRUE); // enable special keys
	bool b_test;
	bool b_alt;

	if (argc > 1) b_test = true;

	if (b_test) printw("Press any key\n");

	unsigned int retkey;
	unsigned int key;

	while (1) {
	b_alt = false;
	key = getch(); // get a key press;

	if (key >= KEY_MIN && key <= KEY_MAX) {
		if (b_test)
			printw("Special key pressed: %s (Key code: %d)\n", keyname(key), key);
		else
			break;
	} else {
		if (key == 27) {
			b_alt = true;
			retkey = (key << 8);
			key = getch();
			retkey |= key;
		}
		else {
			retkey = key;
		}
			if (b_test)
			printw("Key pressed: %c (ASCII code:%d  %x)\n", retkey, (int)retkey, (int)retkey);
	}

	if (! b_test) break;
	}

	refresh();
	endwin(); // cleanup

	if(! b_test) {
	if (b_alt) printf("%x", retkey >> 8);
	printf("%c", (char)(retkey & 0xFF));
	}

	if (b_alt) return 1;
	return 0;
}
