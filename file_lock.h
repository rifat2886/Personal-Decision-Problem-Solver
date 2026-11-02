#ifndef FILE_LOCK_H
#define FILE_LOCK_H

// Shared file lock used by both the C++ console app and the C++
// dashboard server (dashboard/cpp_server.cpp, which has its own
// copy of this same protocol) so that a dashboard write and a
// console-app write to the same data file cannot interleave.
//
// Protocol: to protect "data.txt", take an exclusive flock on
// "data.txt.lock" in the same directory, hold it for the whole
// read-modify-write (or count-then-append) operation, then release
// it. The lock file itself is never a data file and is ignored by
// every module that reads the data files.
//
// This is POSIX-only (Linux/macOS). On other systems the lock is
// a no-op, and concurrent use of the console app and the dashboard
// against the same files is not safe — see dashboard/README.md.

#include <string>

#ifdef __unix__
#include <fcntl.h>
#include <sys/file.h>
#include <unistd.h>
#endif

class FileLock
{
public:
    explicit FileLock(const std::string& dataFile)
    {
#ifdef __unix__
        std::string lockPath = dataFile + ".lock";
        fd_ = open(lockPath.c_str(), O_CREAT | O_RDWR, 0644);
        if (fd_ >= 0)
            flock(fd_, LOCK_EX);
#endif
    }

    ~FileLock()
    {
#ifdef __unix__
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
#ifdef __unix__
    int fd_ = -1;
#endif
};

#endif
