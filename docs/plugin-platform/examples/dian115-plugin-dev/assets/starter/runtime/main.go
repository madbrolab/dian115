//go:build tinygo || wasip1

package main

import (
	"example.com/dian115-plugin-sdk/pluginjson"
	"unsafe"
)

var inputBuffer, outputBuffer []byte

//go:wasmexport dian115_alloc
func allocate(size uint32) uint32 {
	if size == 0 || size > 1<<20 {
		panic("invalid invocation size")
	}
	inputBuffer = make([]byte, size)
	return uint32(uintptr(unsafe.Pointer(&inputBuffer[0])))
}

//go:wasmexport dian115_handle
func handle(ptr, length uint32) uint64 {
	if length == 0 || length > 1<<20 {
		panic("invalid invocation size")
	}
	raw := unsafe.Slice((*byte)(unsafe.Pointer(uintptr(ptr))), int(length))
	var err error
	outputBuffer, err = pluginjson.Encode(dispatch(raw))
	if err != nil {
		panic(err)
	}
	return uint64(uintptr(unsafe.Pointer(&outputBuffer[0])))<<32 | uint64(len(outputBuffer))
}

func main() {}
