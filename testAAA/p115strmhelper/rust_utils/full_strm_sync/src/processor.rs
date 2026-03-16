use crate::types::*;
use aho_corasick::{AhoCorasick, AhoCorasickBuilder, BuildError};
use rayon::prelude::*;
use std::path::Path;

pub struct Processor {
    config: Config,
    strm_blacklist_automaton: AhoCorasick,
    mediainfo_whitelist_automaton: AhoCorasick,
    mediainfo_blacklist_automaton: AhoCorasick,
}

impl Processor {
    pub fn new(config: Config) -> Result<Self, BuildError> {
        let strm_blacklist_automaton = AhoCorasickBuilder::new()
            .ascii_case_insensitive(true)
            .build(&config.strm_generate_blacklist)?;

        let mediainfo_whitelist_automaton = AhoCorasickBuilder::new()
            .ascii_case_insensitive(true)
            .build(&config.mediainfo_download_whitelist)?;

        let mediainfo_blacklist_automaton = AhoCorasickBuilder::new()
            .ascii_case_insensitive(true)
            .build(&config.mediainfo_download_blacklist)?;

        Ok(Self {
            config,
            strm_blacklist_automaton,
            mediainfo_whitelist_automaton,
            mediainfo_blacklist_automaton,
        })
    }

    pub fn process_batch_rust(&self, batch: Vec<FileInput>) -> PackedResult {
        batch
            .par_iter()
            .map(|item| self.process_item(item))
            .fold(PackedResult::default, |mut acc, result| {
                acc.add(result);
                acc
            })
            .reduce(PackedResult::default, |mut final_acc, local_acc| {
                final_acc.merge(local_acc);
                final_acc
            })
    }

    pub fn process_item(&self, item: &FileInput) -> ProcessingResult {
        // 判断是否为非法路径
        if item.is_dir {
            return ProcessingResult::Skip(SkipInfo {
                path_in_pan: item.path.clone(),
                reason: format!("{} 路径为文件夹，跳过处理", item.path).into(),
            });
        }
        if !item.path.starts_with(&self.config.pan_media_dir) {
            return ProcessingResult::Skip(SkipInfo {
                path_in_pan: item.path.clone(),
                reason: format!("{} 路径在网盘媒体库目录外，跳过处理", item.path).into(),
            });
        }

        // 准备后续判断变量
        let file_path = Path::new(&item.name);
        let file_suffix_with_dot = file_path
            .extension()
            .and_then(|s| s.to_str())
            .map(|s| format!(".{}", s.to_lowercase()))
            .unwrap_or_default();

        // 判断是否为待整理目录下面的文件
        if self.config.pan_transfer_enabled
            && self
                .config
                .pan_transfer_paths
                .iter()
                .any(|p| !p.is_empty() && item.path.starts_with(p))
        {
            return ProcessingResult::Skip(SkipInfo {
                path_in_pan: item.path.clone(),
                reason: format!("{} 路径在待整理目录下，跳过处理", item.path).into(),
            });
        }

        // 处理媒体信息文件下载
        if self.config.auto_download_mediainfo
            && self
                .config
                .download_mediaext_set
                .contains(&file_suffix_with_dot)
        {
            // 判断是否在白名单内
            if !self.config.mediainfo_download_whitelist.is_empty()
                && self
                    .mediainfo_whitelist_automaton
                    .find(&item.name)
                    .is_none()
            {
                return ProcessingResult::Skip(SkipInfo {
                    path_in_pan: item.path.clone(),
                    reason: format!(
                        "{} 文件名未匹配到媒体信息文件白名单关键词，跳过处理",
                        item.name
                    )
                    .into(),
                });
            }
            // 判断是否在黑名单内
            if !self.config.mediainfo_download_blacklist.is_empty() {
                if let Some(found) = self.mediainfo_blacklist_automaton.find(&item.name) {
                    let keyword = &self.config.mediainfo_download_blacklist[found.pattern()];
                    return ProcessingResult::Skip(SkipInfo {
                        path_in_pan: item.path.clone(),
                        reason: format!(
                            "{} 匹配到媒体信息文件黑名单关键词: {}",
                            item.name, keyword
                        )
                        .into(),
                    });
                }
            }

            return match (&item.pickcode, &item.sha1) {
                (Some(pc), Some(sha)) => ProcessingResult::Download(DownloadInfo {
                    pickcode: pc.clone(),
                    sha1: sha.clone(),
                    path_in_pan: item.path.clone(),
                }),
                (None, _) => ProcessingResult::Fail(FailInfo {
                    path_in_pan: item.path.clone(),
                    reason: format!("{} 缺失 pick_code 数据", item.path).into(),
                }),
                (_, None) => ProcessingResult::Fail(FailInfo {
                    path_in_pan: item.path.clone(),
                    reason: format!("{} 缺失 sha1 数据", item.path).into(),
                }),
            };
        }

        // 匹配媒体后缀
        if !self.config.rmt_mediaext_set.contains(&file_suffix_with_dot) {
            return ProcessingResult::Skip(SkipInfo {
                path_in_pan: item.path.clone(),
                reason: format!(
                    "{} 未匹配到媒体文件后缀和媒体信息文件后缀，跳过处理",
                    item.path
                )
                .into(),
            });
        }

        // 匹配黑名单
        if !self.config.strm_generate_blacklist.is_empty() {
            if let Some(found) = self.strm_blacklist_automaton.find(&item.name) {
                let keyword = &self.config.strm_generate_blacklist[found.pattern()];
                return ProcessingResult::Skip(SkipInfo {
                    path_in_pan: item.path.clone(),
                    reason: format!("{} 匹配到 STRM 生成黑名单关键词: {}", item.name, keyword)
                        .into(),
                });
            }
        }

        // 匹配文件大小
        if let Some(size) = item.size {
            if self.config.full_sync_min_file_size > 0 && size < self.config.full_sync_min_file_size
            {
                return ProcessingResult::Skip(SkipInfo {
                    path_in_pan: item.path.clone(),
                    reason: format!("文件小于最低限度: {}", item.path).into(),
                });
            }
        }

        // pick_code 检查
        let Some(pc) = &item.pickcode else {
            return ProcessingResult::Fail(FailInfo {
                path_in_pan: item.path.clone(),
                reason: format!("{} 缺失 pick_code 值", item.path).into(),
            });
        };

        if pc.len() == 17 && pc.chars().all(char::is_alphanumeric) {
            ProcessingResult::Strm(StrmInfo {
                pickcode: pc.clone(),
                original_file_name: item.name.clone(),
                path_in_pan: item.path.clone(),
            })
        } else {
            ProcessingResult::Fail(FailInfo {
                path_in_pan: item.path.clone(),
                reason: format!("{} 错误的 pick_code 格式: {}", item.path, pc).into(),
            })
        }
    }
}
