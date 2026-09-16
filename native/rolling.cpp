#ifdef _WIN32
#define EXPORT __declspec(dllexport)
extern "C" { int _fltused = 0; }
#else
#define EXPORT __attribute__((visibility("default")))
#endif
extern "C" EXPORT void rolling_mean(const double* values, double* output, int size, int window) {
    double sum = 0.0;
    for (int i = 0; i < size; ++i) {
        sum += values[i];
        if (i >= window) sum -= values[i-window];
        output[i] = i >= window-1 ? sum/window : 0.0;
    }
}
