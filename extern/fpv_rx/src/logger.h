#ifndef LOGGER_H
#define LOGGER_H

#include <cstdio>
#include <cstring>
#include <functional>
#include <memory>
#include <string>
#ifndef _WIN32
#include <sys/types.h>
#else
typedef unsigned int u_int;
typedef unsigned short u_short;
#endif

typedef u_int uint;
typedef u_short ushort;

#ifndef TRUE
#define TRUE 1
#endif
#ifndef FALSE
#define FALSE 0
#endif

class Logger {
public:
    using LCB = std::function<void(const std::string &, const std::string &)>;

    explicit Logger(const LCB &lcb = nullptr) : m_lcb(lcb) {}

    void error(const char *msg) {
        if (m_lcb) m_lcb("error", msg);
        fprintf(stderr, "%s\n", msg);
    }

    template <typename... Args>
    void error(const char *fmt, Args... args) {
        char buf[512];
        snprintf(buf, sizeof(buf), fmt, args...);
        if (m_lcb) m_lcb("error", buf);
        fprintf(stderr, "%s\n", buf);
    }

    void info(const char *msg) {
        if (m_lcb) m_lcb("info", msg);
        fprintf(stdout, "%s\n", msg);
    }

    template <typename... Args>
    void info(const char *fmt, Args... args) {
        char buf[512];
        snprintf(buf, sizeof(buf), fmt, args...);
        if (m_lcb) m_lcb("info", buf);
        fprintf(stdout, "%s\n", buf);
    }

    void warn(const char *msg) {
        if (m_lcb) m_lcb("warn", msg);
        fprintf(stdout, "%s\n", msg);
    }

    template <typename... Args>
    void warn(const char *fmt, Args... args) {
        char buf[512];
        snprintf(buf, sizeof(buf), fmt, args...);
        if (m_lcb) m_lcb("warn", buf);
        fprintf(stdout, "%s\n", buf);
    }

    void debug(const char *msg) {
        if (m_lcb) m_lcb("debug", msg);
        fprintf(stdout, "%s\n", msg);
    }

    template <typename... Args>
    void debug(const char *fmt, Args... args) {
        char buf[512];
        snprintf(buf, sizeof(buf), fmt, args...);
        if (m_lcb) m_lcb("debug", buf);
        fprintf(stdout, "%s\n", buf);
    }

protected:
    LCB m_lcb{};
};

using Logger_t = std::shared_ptr<Logger>;

#endif
