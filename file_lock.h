#ifndef FILE_LOCK_H
#define FILE_LOCK_H

// Shared file lock used by both the C++ console app and the C++
// dashboard server (dashboard/cpp_server.cpp, which uses the same
// protocol: lock "<datafile>.lock" in the same directory) so that
// a dashboard write and a console-app write to the same data file
// cannot interleave.
//
// Cross-platform:
// - Linux/macOS: POSIX flock() on the lock file.
// - Windows 11: LockFileEx() on a HANDLE opened with no sharing.
//   (MinGW-w64 and MSVC both provide windows.h for this.)
//
// Protocol: to protect "data.txt", take an exclusive lock on
// "data.txt.lock" in the same directory, hold it for the whole
// read-modify-write (or count-then-append) operation, then release
// it. The lock file itself is never a data file and is ignored by
// every module that reads the data files.
//
// If the lock file cannot be opened, the operation proceeds
// unprotected (same fail-open behaviour on both platforms, so a
// read-only directory does not make the whole app unusable). That
// case is documented in dashboard/README.md, not hidden.

#include <string>

#ifdef _WIN32
#include <windows.h>
#else
#include <fcntl.h>
#include <sys/file.h>
#include <unistd.h>
#endif

class FileLock
{
public:
    explicit FileLock(const std::string& dataFile)
    {
#ifdef _WIN32
        std::string lockPath = dataFile + ".lock";
        handle_ = CreateFileA(lockPath.c_str(), GENERIC_READ | GENERIC_WRITE,
                              0, NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
        if (handle_ != INVALID_HANDLE_VALUE)
        {
            OVERLAPPED overlapped = {};
            LockFileEx(handle_, LOCKFILE_EXCLUSIVE_LOCK, 0,
                       MAXDWORD, MAXDWORD, &overlapped);
        }
#else
        std::string lockPath = dataFile + ".lock";
        fd_ = open(lockPath.c_str(), O_CREAT | O_RDWR, 0644);
        if (fd_ >= 0)
            flock(fd_, LOCK_EX);
#endif
    }

    ~FileLock()
    {
#ifdef _WIN32
        if (handle_ != INVALID_HANDLE_VALUE)
        {
            OVERLAPPED overlapped = {};
            UnlockFileEx(handle_, 0, MAXDWORD, MAXDWORD, &overlapped);
            CloseHandle(handle_);
        }
#else
        if (fd_ >= 0)
        {
            flock(fd_, LOCK_UN);
            close(fd_);
        }
#endif
    }

    FileLock(const FileLock&) = delete;
    FileLock& operator=(const FileLock&) = delete;

private:
#ifdef _WIN32
    HANDLE handle_ = INVALID_HANDLE_VALUE;
#else
    int fd_ = -1;
#endif
};

#endif
