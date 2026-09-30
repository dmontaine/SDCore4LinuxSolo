/* local-connect-test.c - call the client library's SDConnectLocal() and say what came back.
 *
 *   gcc -o local-connect-test local-connect-test.c -ldl
 *   cd HOME_DIR && ./local-connect-test HOME_DIR/bin/sdclilib.so
 *
 * Used by verify-solo-service.sh (leg S6f).  SDConnectLocal sends no password, and ruling 21
 * (every session proves the account password) means the server refuses it; the client must
 * get an ANSWER, not hang.  Measured 30 Sep 2026 before the change: the call HUNG.
 *
 * Prints one line, "SDConnectLocal -> <0|1> error='<text>'", and exits 0 when the call
 * returned at all.  The caller puts a timeout around it; a hang is a failed leg.
 * WORKING DIRECTORY: the library finds "<sysdir>/bin/sd" from the environment SD_CONFIG or
 * from where it is - run it from the tree's own directory.
 */
#include <stdio.h>
#include <dlfcn.h>

int main(int argc, char **argv) {
  void *h;
  int (*conn)(char *);
  char *(*err)(void);
  void (*disc)(void);
  int r;

  if (argc != 2) { fprintf(stderr, "usage: %s path/to/sdclilib.so\n", argv[0]); return 2; }
  h = dlopen(argv[1], RTLD_NOW);
  if (!h) { printf("dlopen: %s\n", dlerror()); return 2; }
  conn = (int (*)(char *))dlsym(h, "SDConnectLocal");
  err = (char *(*)(void))dlsym(h, "SDError");
  disc = (void (*)(void))dlsym(h, "SDDisconnect");
  if (!conn || !err) { printf("the library has no SDConnectLocal or SDError\n"); return 2; }
  r = conn("sduser");
  printf("SDConnectLocal -> %d error='%s'\n", r, err());
  if (r && disc) disc();
  return 0;
}
