# 视觉素材来源

品牌标记来自 DIAN115 官方 WIKI，按项目要求沿用。页面布局、CSS 图形、SVG 图标及动画为本页面独立编写。

电影海报于 2026-10-08 从 TMDB 图片 CDN 获取，用于表现私人影音收藏。海报署名与权利归相应电影发行方；页面没有使用产品截图。

| 本地文件 | 电影 | 原始图像地址 |
| --- | --- | --- |
| `interstellar.jpg` | 星际穿越 | https://image.tmdb.org/t/p/w500/gEU2QniE6E77NI6lCU6MxlNBvIx.jpg |
| `dune.jpg` | 沙丘 2 | https://image.tmdb.org/t/p/w500/1pdfLvkbY9ohJlCjQH2CZjjYVvJ.jpg |
| `blade-runner.jpg` | 银翼杀手 2049 | https://image.tmdb.org/t/p/w500/gajva2L0rPYkEWjzgFlBXCAVBE5.jpg |
| `arrival.jpg` | 降临 | https://image.tmdb.org/t/p/w500/x2FJsf1ElAgr63Y3PNPtJrcmpoe.jpg |
| `inception.jpg` | 盗梦空间 | https://image.tmdb.org/t/p/w500/oYuLEt3zVCKq57qu2F8dT7NIa6f.jpg |
| `soul.jpg` | 心灵奇旅 | https://image.tmdb.org/t/p/w500/hm58Jw4Lw8OIeECIq5qyPYhAeRJ.jpg |

可在 `index.html` 与 `app.js` 更换海报，在 `cinema.js` 更换对应影片名称、年份、类别和光影色。


## 2026-10-21 新版 RAVE 演示素材

RAVE 界面基于 [StreamVibe · Praha / Produce UI](https://www.figma.com/community/file/1294589591426976269)，按 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) 修改适配。修改包括中文本地化、媒体库与个人空间接入、内容类型扩展、主题及响应式布局适配。完整说明保存在 [RAVE-CREDITS.md](demo/static/RAVE-CREDITS.md) 与演示站素材说明中。

`demo/static/demo-catalog/` 保存真实歌手和演职人员头像、专辑封面、频道标志、漫画卷封、经典书籍封面及少量影视横图。完整出处、作者与许可见该目录的 [CREDITS.md](demo/static/demo-catalog/CREDITS.md)、`sources.json`、`attributions.json` 与 `backdrop-sources.json`。图片按展示尺寸下载，本地托管，保留署名来源。

专辑与歌曲资料取自 Apple iTunes Lookup API，原始资料和公开试听地址保存在 `music-metadata.json`。Demo 不包含完整歌曲、影视正片、漫画正文或有声书朗读；观看进度、评分、收藏和直播排期为演示状态。

## 2026-11-04 封面与背景预告片

`assets/current/` 新增 28 张影视封面、两张剧集横图与两个本地背景视频。作品资料来自 TMDB；作品页、图片原地址及校验摘要见 [sources.json](assets/current/sources.json)。图片和影视内容的权利归原权利人，TMDB 不代表对本站的认可。

背景片段保留原生 1920×1080，截取 36 秒并移除音轨，没有移除或重绘视频原有标识。

- 《龙之家族》：[TMDB 条目](https://www.themoviedb.org/tv/94997-house-of-the-dragon/videos)，[HBO Max 官方预告片](https://www.youtube.com/watch?v=DotnJ7tTA34)，片段从第 32 秒开始。
- 《绝命毒师》：[TMDB 条目](https://www.themoviedb.org/tv/1396-breaking-bad/videos)，[节目官方频道预告片](https://www.youtube.com/watch?v=VaOt6tXyf2Y)，片段从第 12 秒开始。
