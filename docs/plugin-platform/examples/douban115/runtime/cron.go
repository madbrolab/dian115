package main

import (
	"fmt"
	"strconv"
	"strings"
	"time"
)

// ---- Cron v1 解析与匹配 ----
// 与 dian115 宿主 cron v1 规则一致：5 个数字字段（分 时 日 月 周），
// 支持 *、,、-、/ 语法；日和周不能同时受限；相邻分钟间隔不强制（插件自有调度器）。

type cronSpec struct {
	minutes  []bool // 60
	hours    []bool // 24
	doms     []bool // 31
	months   []bool // 12
	dows     []bool // 7
	domStar  bool
	dowStar  bool
	original string
}

func parseCronField(field string, min, max int) ([]bool, bool, error) {
	set := make([]bool, max-min+1)
	star := field == "*"
	for _, part := range strings.Split(field, ",") {
		part = strings.TrimSpace(part)
		if part == "" {
			return nil, false, fmt.Errorf("字段 %q 含空片段", field)
		}
		step := 1
		if i := strings.Index(part, "/"); i >= 0 {
			n, err := strconv.Atoi(part[i+1:])
			if err != nil || n < 1 {
				return nil, false, fmt.Errorf("字段 %q 的步长无效", field)
			}
			step = n
			part = part[:i]
		}
		lo, hi := min, max
		if part != "*" {
			if strings.Contains(part, "-") {
				pieces := strings.SplitN(part, "-", 2)
				var err1, err2 error
				lo, err1 = strconv.Atoi(pieces[0])
				hi, err2 = strconv.Atoi(pieces[1])
				if err1 != nil || err2 != nil {
					return nil, false, fmt.Errorf("字段 %q 的范围无效", field)
				}
			} else {
				v, err := strconv.Atoi(part)
				if err != nil {
					return nil, false, fmt.Errorf("字段 %q 含非数字内容", field)
				}
				lo, hi = v, v
			}
			if lo < min || hi > max || lo > hi {
				return nil, false, fmt.Errorf("字段 %q 超出范围 %d-%d", field, min, max)
			}
		}
		for v := lo; v <= hi; v += step {
			set[v-min] = true
		}
	}
	return set, star, nil
}

// parseCron 解析 5 字段 cron 表达式。
func parseCron(expr string) (*cronSpec, error) {
	fields := strings.Fields(strings.TrimSpace(expr))
	if len(fields) != 5 {
		return nil, fmt.Errorf("cron 需要 5 个字段（分 时 日 月 周），当前 %d 个", len(fields))
	}
	spec := &cronSpec{original: expr}
	var err error
	var domStar, dowStar bool
	if spec.minutes, _, err = parseCronField(fields[0], 0, 59); err != nil {
		return nil, err
	}
	if spec.hours, _, err = parseCronField(fields[1], 0, 23); err != nil {
		return nil, err
	}
	if spec.doms, domStar, err = parseCronField(fields[2], 1, 31); err != nil {
		return nil, err
	}
	if spec.months, _, err = parseCronField(fields[3], 1, 12); err != nil {
		return nil, err
	}
	if spec.dows, dowStar, err = parseCronField(fields[4], 0, 6); err != nil {
		return nil, err
	}
	if !domStar && !dowStar {
		return nil, fmt.Errorf("「日」和「周」不能同时受限（其中一个必须为 *）")
	}
	spec.domStar, spec.dowStar = domStar, dowStar
	return spec, nil
}

// validateCron 校验 cron 表达式，合法返回 nil。
func validateCron(expr string) error {
	_, err := parseCron(expr)
	return err
}

// matches 判断给定时间是否命中（分钟粒度）。
func (c *cronSpec) matches(t time.Time) bool {
	if !c.minutes[t.Minute()] || !c.hours[t.Hour()] || !c.months[int(t.Month())-1] {
		return false
	}
	dom := t.Day()
	dow := int(t.Weekday())
	switch {
	case c.domStar && c.dowStar:
		return true
	case c.domStar:
		return c.dows[dow]
	case c.dowStar:
		return c.doms[dom-1]
	default:
		return c.doms[dom-1] || c.dows[dow]
	}
}

// nextFire 计算 from 之后的下一次触发时间（逐分钟扫描，上限 366 天）。
func (c *cronSpec) nextFire(from time.Time) time.Time {
	t := from.Truncate(time.Minute).Add(time.Minute)
	for i := 0; i < 366*24*60; i++ {
		if c.matches(t) {
			return t
		}
		t = t.Add(time.Minute)
	}
	return time.Time{}
}
