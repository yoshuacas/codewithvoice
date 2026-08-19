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
 *
 * Finder/LaunchServices launches attach stdout/stderr to /dev/null, which
 * makes failures undiagnosable; redirect both to
 * ~/Library/Logs/CodeWithVoice.log unless a terminal is attached.
 */
#include <dlfcn.h>
#include <fcntl.h>
#include <libgen.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <pwd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

typedef int (*py_bytes_main_t)(int argc, char **argv);

#define LOG_ROTATE_BYTES (5 * 1024 * 1024)

static void redirect_logs(void) {
    if (isatty(STDOUT_FILENO) || isatty(STDERR_FILENO)) {
        return; /* terminal launch: keep output on the console */
    }
    const char *home = getenv("HOME");
    if (home == NULL || home[0] == '\0') {
        struct passwd *pw = getpwuid(getuid());
        if (pw == NULL) {
            return;
        }
        home = pw->pw_dir;
    }
    char dir[PATH_MAX];
    snprintf(dir, sizeof(dir), "%s/Library", home);
    mkdir(dir, 0755); /* usually exists already */
    snprintf(dir, sizeof(dir), "%s/Library/Logs", home);
    mkdir(dir, 0755);

    char path[PATH_MAX];
    snprintf(path, sizeof(path), "%s/CodeWithVoice.log", dir);
    struct stat st;
    if (stat(path, &st) == 0 && st.st_size > LOG_ROTATE_BYTES) {
        char old[PATH_MAX];
        snprintf(old, sizeof(old), "%s.old", path);
        rename(path, old);
    }

    /* dup2, not freopen: freopen destroys the original stream even when the
     * log file can't be opened, which would silence stderr entirely. */
    int fd = open(path, O_WRONLY | O_CREAT | O_APPEND, 0644);
    if (fd < 0) {
        return;
    }
    dup2(fd, STDOUT_FILENO);
    dup2(fd, STDERR_FILENO);
    if (fd > STDERR_FILENO) {
        close(fd);
    }
    setvbuf(stdout, NULL, _IOLBF, 0);
    setvbuf(stderr, NULL, _IONBF, 0);

    /* python block-buffers stdout when it isn't a tty; a crash would then
     * swallow the log lines leading up to it. */
    setenv("PYTHONUNBUFFERED", "1", 1);

    time_t now = time(NULL);
    char ts[32];
    strftime(ts, sizeof(ts), "%F %T", localtime(&now));
    fprintf(stderr, "launcher: %s pid %d start\n", ts, getpid());
}

int main(int argc, char **argv) {
    redirect_logs();
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
