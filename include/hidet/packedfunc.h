#pragma once

#ifndef DLL
#define DLL extern "C" __attribute__((visibility("default")))
#endif

enum ArgType {
    INT32 = 1,
    FLOAT32 = 2,
    POINTER = 3,
};

typedef void (*PackedFunc_t)(int num_args, int *arg_types, void** args);

struct PackedFunc {
    int num_args;
    int* arg_types;
    void** func_pointer;
};

#define INT_ARG(p) (*(int*)(p))
#define FLOAT_ARG(p) (*(float*)(p))


