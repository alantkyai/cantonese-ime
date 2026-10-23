/* App-private, relocatable CPython launcher. The Python framework is bundled
 * in Contents/Frameworks and its search paths never come from user settings.
 */
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <mach-o/dyld.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void fail(const char *message) {
    fprintf(stderr, "Cantonese IME engine: %s\n", message);
    exit(70);
}

static void check(PyStatus status, PyConfig *config) {
    if (PyStatus_Exception(status)) {
        PyConfig_Clear(config);
        Py_ExitStatusException(status);
    }
}

static void set_string(PyConfig *config, wchar_t **field, const char *value) {
    check(PyConfig_SetBytesString(config, field, value), config);
}

static void append_path(PyConfig *config, const char *value) {
    wchar_t *wide = Py_DecodeLocale(value, NULL);
    if (!wide) fail("cannot decode the private framework path");
    PyStatus status = PyWideStringList_Append(&config->module_search_paths, wide);
    PyMem_RawFree(wide);
    check(status, config);
}

int main(int argc, char **argv) {
    char requested[PATH_MAX], executable[PATH_MAX], contents[PATH_MAX];
    char home[PATH_MAX], library[PATH_MAX], dynamic[PATH_MAX];
    uint32_t size = sizeof(requested);
    if (_NSGetExecutablePath(requested, &size) != 0 || !realpath(requested, executable))
        fail("cannot resolve the application executable");
    if (snprintf(contents, sizeof(contents), "%s", executable) >= (int)sizeof(contents))
        fail("the application path is too long");
    char *slash = strrchr(contents, '/');
    if (!slash) fail("missing executable parent");
    *slash = '\0'; /* Contents/MacOS */
    slash = strrchr(contents, '/');
    if (!slash || strcmp(slash + 1, "MacOS") != 0) fail("unexpected executable layout");
    *slash = '\0'; /* Contents */
    if (snprintf(home, sizeof(home), "%s/Frameworks/Python.framework/Versions/3.13", contents) >= (int)sizeof(home) ||
        snprintf(library, sizeof(library), "%s/lib/python3.13", home) >= (int)sizeof(library) ||
        snprintf(dynamic, sizeof(dynamic), "%s/lib-dynload", library) >= (int)sizeof(dynamic))
        fail("the private library path is too long");

    PyConfig config;
    PyConfig_InitIsolatedConfig(&config);
    config.use_environment = 0;
    config.user_site_directory = 0;
    config.site_import = 0;
    config.write_bytecode = 0;
    config.safe_path = 1;
    config.parse_argv = 1;
    config.module_search_paths_set = 1;
    set_string(&config, &config.home, home);
    set_string(&config, &config.prefix, home);
    set_string(&config, &config.exec_prefix, home);
    set_string(&config, &config.base_prefix, home);
    set_string(&config, &config.base_exec_prefix, home);
    set_string(&config, &config.executable, executable);
    set_string(&config, &config.base_executable, executable);
    set_string(&config, &config.program_name, executable);
    append_path(&config, library);
    append_path(&config, dynamic);
    check(PyConfig_SetBytesArgv(&config, argc, argv), &config);
    check(Py_InitializeFromConfig(&config), &config);
    PyConfig_Clear(&config);
    return Py_RunMain();
}
