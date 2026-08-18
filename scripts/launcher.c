/*
 * Mach-O launcher for CodeWithVoice.app.
 *
 * The main executable must be a compiled binary that KEEPS running as the
 * bundle's signed executable: a shell stub that exec()s python leaves the
 * process's code identity as "python3.12" (ad-hoc, per-binary), which no
 * longer matches the app record LaunchServices launched. The WindowServer
 * then refuses to attach the NSStatusItem scene (no menu bar icon) and TCC
 * cannot attribute the microphone request to the bundle (silent denial, no
 * prompt). Embedding python via libpython keeps the process image intact.
 *
 * With no arguments, runs `-m voicebar`. With arguments, behaves like the
 * python interpreter itself — multiprocessing re-invokes sys.executable
 * with `-c ...` for its spawn helpers, and that must not relaunch the app.
 */
#include <dlfcn.h>
#include <libgen.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef int (*py_bytes_main_t)(int argc, char **argv);

int main(int argc, char **argv) {
    char exe[PATH_MAX];
    uint32_t size = sizeof(exe);
    if (_NSGetExecutablePath(exe, &size) != 0) {
        fprintf(stderr, "launcher: executable path too long\n");
        return 1;
    }
    char resolved[PATH_MAX];
    if (realpath(exe, resolved) == NULL) {
        perror("launcher: realpath");
        return 1;
    }
    char *dir = dirname(resolved); /* Contents/MacOS */

    char pyhome[PATH_MAX];
    snprintf(pyhome, sizeof(pyhome), "%s/../Resources/python", dir);
    setenv("PYTHONHOME", pyhome, 1);
    /* Never write .pyc inside the bundle: breaks the codesign resource seal. */
    setenv("PYTHONDONTWRITEBYTECODE", "1", 1);

    char libpython[PATH_MAX];
    snprintf(libpython, sizeof(libpython), "%s/lib/libpython3.12.dylib", pyhome);
    void *handle = dlopen(libpython, RTLD_NOW | RTLD_GLOBAL);
    if (handle == NULL) {
        fprintf(stderr, "launcher: dlopen failed: %s\n", dlerror());
        return 1;
    }
    py_bytes_main_t py_main = (py_bytes_main_t)dlsym(handle, "Py_BytesMain");
    if (py_main == NULL) {
        fprintf(stderr, "launcher: dlsym failed: %s\n", dlerror());
        return 1;
    }

    if (argc > 1) {
        return py_main(argc, argv); /* interpreter passthrough */
    }
    char *py_argv[] = {argv[0], "-B", "-m", "voicebar", NULL};
    return py_main(4, py_argv);
}
