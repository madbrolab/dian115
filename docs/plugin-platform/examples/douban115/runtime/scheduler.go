package main

import (
	"fmt"
	"time"
)

// ---- 常驻调度 ----
// manifest 声明 runtime.resident=true 后，宿主用第二个模块实例发起一次不限时的
// resident 调用，插件在这里运行自己的调度循环。同步间隔（Cron）由用户在页面配置，
// 通过 Host Storage 持久化，常驻实例每 30 秒重新加载配置并检查是否到点。

// anyRankEnabled 判断是否有任意榜单启用。
func anyRankEnabled(cfg *Config) bool {
	for _, rc := range cfg.RankConfigs {
		if rc.Enabled {
			return true
		}
	}
	return false
}

// saveRunState 直接落盘运行状态。
func (r *runtime) saveRunState(s RunState) {
	_ = r.storagePut(storageRunState, s)
}

// residentLoop 常驻调度主循环。返回错误视为崩溃（宿主按 restart_policy 重启），
// 因此内部所有异常都被就地消化。
const (
	// idleTick 空闲时的调度间隔。
	idleTick = 30 * time.Second
	// busyTick 有任务未跑完时的调度间隔：尽快回到断点继续，而不是等满 30 秒。
	busyTick = 2 * time.Second
)

func (r *runtime) residentLoop() (any, error) {
	r.log("info", "常驻同步调度已启动", memFields("resident-start"))
	r.runDueSchedules()
	started := time.Now()
	for {
		delay := idleTick
		if r.activeJobKind() != "" {
			delay = busyTick
		}
		time.Sleep(delay)
		func() {
			defer func() {
				if rec := recover(); rec != nil {
					r.log("error", "定时调度执行异常", map[string]any{"reason": fmt.Sprint(rec)})
				}
			}()
			// 心跳带运行时长与内存高水位：常驻实例若被宿主超时或内存硬限杀死，
			// 最后一条心跳即可区分是「跑够时长被回收」还是「内存触及上限」。
			uptime := int64(time.Since(started).Seconds())
			r.log("info", "常驻心跳", memFieldsWith("tick", map[string]any{"uptime_s": uptime}))
			r.runDueSchedules()
		}()
	}
}

// runDueSchedules 检查「立即运行」请求队列与三个同步任务的 cron，到点则执行。
// 先把触发分钟落盘再执行，避免崩溃/重启后同一分钟内重复触发。
func (r *runtime) runDueSchedules() {
	r.loadConfig() // 每轮重新从 Host Storage 读配置，页面改动即时生效
	cfg := r.currentConfig()
	now := time.Now()
	minute := now.Truncate(time.Minute).Format("2006-01-02T15:04")
	rs := r.loadRunState()

	// 1. 续跑上次未完成的同步（最高优先级）。
	// 实例被回收后 job state 仍在 Host Storage 里，下一轮从断点继续，
	// 而不是从头重来（Emby/榜单这类长任务尤其依赖这一点）。
	if kind := r.activeJobKind(); kind != "" {
		r.log("info", "继续上次未完成的同步", map[string]any{"kind": kind})
		r.runJobLoop(kind, false)
		return
	}

	// 2. UI 触发的「立即运行」请求
	if r.drainRunRequests() {
		// 手动任务刚跑过，本轮跳过 cron 检查，避免重复执行。
		return
	}

	dueRank, dueWish, dueEmby := false, false, false
	if spec, err := parseCron(cfg.RankCron); err == nil && spec.matches(now) && rs.LastRankCronMin != minute && anyRankEnabled(cfg) {
		dueRank = true
		rs.LastRankCronMin = minute
	}
	if spec, err := parseCron(cfg.WishCron); err == nil && spec.matches(now) && rs.LastWishCronMin != minute && cfg.WishEnabled {
		dueWish = true
		rs.LastWishCronMin = minute
	}
	if spec, err := parseCron(cfg.EmbyCron); err == nil && spec.matches(now) && rs.LastEmbyCronMin != minute && cfg.EmbyEnabled {
		dueEmby = true
		rs.LastEmbyCronMin = minute
	}
	if !dueRank && !dueWish && !dueEmby {
		return
	}
	r.saveRunState(rs)

	if dueRank {
		r.log("info", "定时榜单订阅触发", nil)
		r.runTask("rank")
	}
	if dueWish {
		r.log("info", "定时想看订阅触发", nil)
		r.runTask("wish")
	}
	if dueEmby {
		r.log("info", "定时 Emby 观影同步触发", nil)
		r.runTask("emby")
	}
}
