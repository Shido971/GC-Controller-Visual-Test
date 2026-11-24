/*
 * rename_main.h - force-included before the original Wii main.c.
 * Its main() becomes vct_main(); main_pc.c provides the real entry point.
 * A force-included header is processed after every -D on the command line,
 * so this also wins over SDL's "-Dmain=SDL_main" (MSYS2 pkg-config on Windows).
 */
#undef main
#define main vct_main
