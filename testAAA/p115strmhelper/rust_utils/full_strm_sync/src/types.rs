use pyo3::prelude::*;
use serde::Deserialize;
use std::collections::HashSet;

#[derive(Deserialize, Debug, Clone)]
pub struct Config {
    pub pan_transfer_enabled: bool,
    pub pan_transfer_paths: Vec<String>,
    pub auto_download_mediainfo: bool,
    pub rmt_mediaext_set: HashSet<String>,
    pub download_mediaext_set: HashSet<String>,
    pub strm_generate_blacklist: Vec<String>,
    pub mediainfo_download_whitelist: Vec<String>,
    pub mediainfo_download_blacklist: Vec<String>,
    pub full_sync_min_file_size: u64,
    pub pan_media_dir: String,
}

#[derive(Clone, Debug, Deserialize)]
pub struct FileInput {
    pub name: String,
    pub path: String,
    pub is_dir: bool,
    pub size: Option<u64>,
    pub pickcode: Option<String>,
    pub sha1: Option<String>,
}

#[pyclass(get_all, frozen)]
#[derive(Clone, Debug)]
pub struct StrmInfo {
    pub pickcode: String,
    pub original_file_name: String,
    pub path_in_pan: String,
}

#[pyclass(get_all, frozen)]
#[derive(Clone, Debug)]
pub struct DownloadInfo {
    pub pickcode: String,
    pub sha1: String,
    pub path_in_pan: String,
}

#[pyclass(get_all, frozen)]
#[derive(Clone, Debug)]
pub struct SkipInfo {
    pub path_in_pan: String,
    pub reason: String,
}

#[pyclass(get_all, frozen)]
#[derive(Clone, Debug)]
pub struct FailInfo {
    pub path_in_pan: String,
    pub reason: String,
}

#[derive(Clone, Debug)]
pub enum ProcessingResult {
    Strm(StrmInfo),
    Download(DownloadInfo),
    Skip(SkipInfo),
    Fail(FailInfo),
}

#[pyclass(get_all)]
#[derive(Default)]
pub struct PackedResult {
    pub strm_results: Vec<StrmInfo>,
    pub download_results: Vec<DownloadInfo>,
    pub skip_results: Vec<SkipInfo>,
    pub fail_results: Vec<FailInfo>,
}

impl PackedResult {
    pub fn add(&mut self, result: ProcessingResult) {
        match result {
            ProcessingResult::Strm(info) => self.strm_results.push(info),
            ProcessingResult::Download(info) => self.download_results.push(info),
            ProcessingResult::Skip(info) => self.skip_results.push(info),
            ProcessingResult::Fail(info) => self.fail_results.push(info),
        }
    }
    pub fn merge(&mut self, other: Self) {
        self.strm_results.extend(other.strm_results);
        self.download_results.extend(other.download_results);
        self.skip_results.extend(other.skip_results);
        self.fail_results.extend(other.fail_results);
    }
}
