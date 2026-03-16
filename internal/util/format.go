package util

import (
	"fmt"
	"time"
)

// FormatDuration 格式化时间duration
// 超过60秒按分计算，超过999毫秒按秒计算，否则按毫秒计算
func FormatDuration(d time.Duration) string {
	ms := d.Milliseconds()
	if ms >= 60000 {
		return fmt.Sprintf("%.1f分", float64(ms)/60000)
	}
	if ms >= 1000 {
		return fmt.Sprintf("%.2f秒", float64(ms)/1000)
	}
	return fmt.Sprintf("%d毫秒", ms)
}

// FormatMilliseconds 格式化毫秒数
// 超过60秒按分计算，超过999毫秒按秒计算，否则按毫秒计算
func FormatMilliseconds(ms int64) string {
	if ms >= 60000 {
		return fmt.Sprintf("%.1f分", float64(ms)/60000)
	}
	if ms >= 1000 {
		return fmt.Sprintf("%.2f秒", float64(ms)/1000)
	}
	return fmt.Sprintf("%d毫秒", ms)
}
