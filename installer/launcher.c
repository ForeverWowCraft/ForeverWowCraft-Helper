/* ForeverWowCraft Helper.app's main executable, Contents/MacOS/ForeverWowCraft Helper: Python run
   in this process on the helper's fwch.py app, so that the process is the application itself and
   macOS knows it by the bundle's identifier (com.foreverwowcraft.helper). A script that started
   Resources/python-<arch>/bin/python3.14 left the process a bare Python with no bundle, and a
   macOS never placed its menu bar icon (reported on macOS 26 or later, 9 Nov 2026).

   Built by installer/build_mac.py once for each processor, against that processor's Python
   (Resources/python-arm64, Resources/python-x86_64: its lib/libpython3.14.dylib, found through
   the rpath the build gives each slice), and joined into one universal file with lipo. Extra
   arguments go after "app" (fwch.py app --identity is the build's check of the identity). */
#include <Python.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if defined(__arm64__) || defined(__aarch64__)
#define ARCH "arm64"
#else
#define ARCH "x86_64"
#endif

static int check(PyStatus status, PyConfig *config) {
    if (!PyStatus_Exception(status))
        return 0;
    PyConfig_Clear(config);
    if (PyStatus_IsExit(status))
        exit(status.exitcode);
    Py_ExitStatusException(status);
    return 1;
}

int main(int argc, char **argv) {
    char exe[PATH_MAX], contents[PATH_MAX], home[PATH_MAX], script[PATH_MAX];
    uint32_t size = sizeof exe;
    if (_NSGetExecutablePath(exe, &size) != 0 || !realpath(exe, contents)) {
        fprintf(stderr, "ForeverWowCraft Helper: cannot tell where this application is\n");
        return 1;
    }
    for (int up = 0; up < 2; up++) {                 /* .../Contents/MacOS/ForeverWowCraft Helper -> .../Contents */
        char *slash = strrchr(contents, '/');
        if (!slash) {
            fprintf(stderr, "ForeverWowCraft Helper: not inside an application bundle\n");
            return 1;
        }
        *slash = '\0';
    }
    snprintf(home, sizeof home, "%s/Resources/python-" ARCH, contents);
    snprintf(script, sizeof script, "%s/Resources/helper/fwch.py", contents);

    char **args = calloc((size_t)argc + 3, sizeof *args);
    if (!args)
        return 1;
    int n = 0;
    args[n++] = argv[0];
    args[n++] = script;
    args[n++] = "app";
    for (int i = 1; i < argc; i++)
        if (strncmp(argv[i], "-psn_", 5) != 0)       /* the process serial number an old Finder added */
            args[n++] = argv[i];

    PyConfig config;
    PyConfig_InitPythonConfig(&config);
    config.write_bytecode = 0;                       /* nothing written inside the signed bundle */
    if (check(PyConfig_SetBytesString(&config, &config.home, home), &config) ||
        check(PyConfig_SetBytesArgv(&config, n, args), &config) ||
        check(Py_InitializeFromConfig(&config), &config))
        return 1;
    PyConfig_Clear(&config);
    return Py_RunMain();
}
