package main

// 注意：本包已把插件自己的状态机命名为 runtime，标准库必须走别名导入。
import goruntime "runtime"

// memFields 采样当前模块的内存占用，用于诊断常驻实例崩溃。
//
// 宿主为 WASM 实例设定了线性内存硬限（manifest runtime.memory_mb，当前 256 MiB）。
// 超限会让模块 trap、worker 退出并被监督器按 restart_policy 重启，表现为
// 「长任务跑到一半插件整体重启」。另外 WASM 没有内存回收指令，Go 的堆一旦
// 增长就不会把线性内存还给宿主，因此 Sys 是只增不减的高水位。
//
// 这里把堆占用与向宿主申请的总量写进日志，便于在真机上分辨崩溃到底是
// 内存触及硬限，还是调用超时。
func memFields(note string) map[string]any {
	var ms goruntime.MemStats
	goruntime.ReadMemStats(&ms)
	return map[string]any{
		"note":     note,
		"heap_mb":  ms.HeapAlloc >> 20,
		"sys_mb":   ms.Sys >> 20,
		"stack_mb": ms.StackSys >> 20,
		"gc":       ms.NumGC,
	}
}

// memFieldsWith 在内存采样上附带业务字段，避免为诊断多打一条日志。
func memFieldsWith(note string, extra map[string]any) map[string]any {
	fields := memFields(note)
	for k, v := range extra {
		fields[k] = v
	}
	return fields
}
