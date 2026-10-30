export type JSONValue = null | boolean | number | string | JSONValue[] | { [key:string]:JSONValue }
export type OK = {ok:true}
export type Headers = Record<string,string[]>
import type { TypedHostAPI } from './host-api.js'
export type * from './host-api.js'
/** ctx.api with request/response types inferred from documented host routes. */
export type HostAPI = TypedHostAPI
export interface Cookie { name:string;value:string;domain:string;path:string;host_only:boolean;secure:boolean;http_only:boolean;same_site?:'lax'|'strict'|'none'|'';expires_at?:number }
export interface MultipartFile {field:string;filename?:string;content_type?:string;path?:string;base64?:string;text?:string}
export interface HTTPRequest {url:string;method?:string;headers?:Headers|Record<string,string>;body?:string;body_base64?:string|Uint8Array;body_file?:string;form?:Record<string,JSONValue>;json?:JSONValue;multipart?:{fields?:Record<string,JSONValue>;files?:MultipartFile[]};
 response_type?:'text'|'base64'|'json';charset?:string;save_to?:string;follow_redirects?:boolean;max_redirects?:number;session?:string;timeout_seconds?:number;max_bytes?:number;cache_seconds?:number;proxy?:string}
export interface HTTPResult {status:number;url:string;headers:Headers;body:string;cached:boolean;body_base64?:string;data?:JSONValue;path?:string;size?:number;sha256?:string}
export interface RenderRequest {endpoint:string;url:string;session?:string;wait_seconds?:number;timeout_seconds?:number}
export interface RenderResult {url:string;html:string;user_agent:string;http_status_verified:boolean}
export interface HTTPClient {request(options:HTTPRequest):Promise<HTTPResult>;cookies(options:{url:string;session?:string;cookie?:string}):Promise<Cookie[]>;importCookies(options:{cookies:Cookie[];session?:string;replace?:boolean}):Promise<OK>;render(options:RenderRequest):Promise<RenderResult>}
export interface FileInfo {name:string;path:string;is_dir:boolean;size:number;modified:string;backend:'plugin'|'local'|'cd2'}
export type FileEncoding = 'utf8'|'base64'
export interface FileWriteResult {size:number;sha256:string;path?:string}
/** Relative = plugin-owned data/files; absolute Linux path or "cd2:/drive/dir" = host path (never readable). */
export type FilePath = string
export interface FileTransfer {path?:FilePath;paths?:FilePath[];destination?:FilePath;destination_dir?:FilePath;overwrite?:boolean;progress?:boolean}
export interface TransferResult {backend:'system'|'cd2'|'plugin';items?:{source:string;path:string;size:number}[];result?:JSONValue}
export interface FileProgress {operation:string;backend:string;current?:string;items_done:number;items_total:number;bytes_done:number;bytes_total:number;message?:string}
export interface Files {
 /** Plugin-owned only; at most 16 MiB per read. */
 call(options:{operation:'read';path:string;encoding?:FileEncoding;offset?:number;length?:number}):Promise<string>;
 /** Plugin-owned only. */
 call(options:{operation:'write'|'append';path:string;content:string;encoding?:FileEncoding}):Promise<FileWriteResult>;
 call(options:{operation:'list';path:FilePath}):Promise<FileInfo[]>;
 call(options:{operation:'walk';path:FilePath;pattern?:string;limit?:number}):Promise<FileInfo[]>;
 call(options:{operation:'stat';path:FilePath}):Promise<FileInfo>;
 call(options:{operation:'exists';path:FilePath}):Promise<boolean>;
 call(options:{operation:'hash';path:FilePath;algorithm?:'sha256'}):Promise<string>;
 call(options:{operation:'mkdir';path:FilePath}):Promise<{path:string}|null>;
 /** Remove one empty directory only; CD2 is unsupported. Never recursive. */
 call(options:{operation:'rmdir';path:FilePath}):Promise<null>;
 /** Local host paths only, no overwrite; hardlink requires the same filesystem. */
 call(options:{operation:'hardlink'|'symlink';path:FilePath;destination:FilePath;overwrite?:false}):Promise<{path:string;operation:string}>;
 call(options:{operation:'rename';path:FilePath;name:string}):Promise<{path:string}|null>;
 call(options:{operation:'remove';path?:FilePath;paths?:FilePath[];progress?:boolean}):Promise<JSONValue>;
 call(options:FileTransfer&{operation:'move'|'copy'}):Promise<TransferResult>;
}
export interface CD2File extends FileInfo {id:string;path:string}
export interface CD2Result {success:boolean;error_message:string;paths:string[]|null}
export interface CD2Outcome {path:string;file:CD2File|null;retryable:boolean;error:string}
export interface CD2Operations {
 list:{input:{path:string;force_refresh?:boolean};output:CD2File[]};
 stat:{input:{path:string};output:CD2File|null};
 mkdir:{input:{parent:string;name:string};output:{file:CD2File|null;result:CD2Result|null}};
 rename:{input:{path:string;name:string};output:CD2Outcome[]};
 move:{input:{path:string;destination:string};output:CD2Outcome[]};
 copy:{input:{path:string;destination:string};output:CD2Result|null};
 remove:{input:{path:string};output:CD2Result|null};
 search:{input:{path:string;query:string;fuzzy?:boolean};output:CD2File[]};
}
export interface CD2Client {call<M extends keyof CD2Operations>(method:M,options:CD2Operations[M]['input']):Promise<CD2Operations[M]['output']>}
export interface WatchInput {id:string;kind:'local'|'cd2';path:string;job:string;interval_seconds?:number;realtime?:boolean;debounce_ms?:number;patterns?:string[];recursive?:boolean}
export interface WatchChange {path:string;kind:'created'|'changed'|'removed'}
export interface WatchInputEvent {watch:string;changes:WatchChange[]}
export interface HostEvent {id:string;type:string;title?:string;content?:string;data?:Record<string,JSONValue>;at:string}
export interface ListenerState {id:string;port:number;host?:string;source:'manifest'|'runtime';running:boolean;address?:string;error?:string}
export interface HTTPHandlerRequest {method:string;path:string;url:string;query:Record<string,string|string[]>;headers:Headers;remote_addr:string;host:string;source:string;body?:string;body_base64:string;json?:JSONValue}
export type HTTPHandlerResponse = string|null|{status?:number;headers?:Record<string,string|string[]>;body?:string;body_base64?:string;json?:JSONValue;file?:string}
export interface WatchRecord extends WatchInput {sequence:number;snapshot?:Record<string,string>;pending_snapshot?:Record<string,string>;initialized:boolean;pending?:JSONValue;error?:string}
export type NotifyChannelKey = 'telegram'|'wecom'
/** text = the user's plugin notification template; markdown/html = sent as authored with a host source line. */
export type NotificationFormat = 'text'|'markdown'|'html'
export interface NotificationChannelContent {title?:string;body?:string;format?:NotificationFormat;image_url?:string}
export interface Notification {
 title:string;body:string;level?:'info'|'success'|'warning'|'error';format?:NotificationFormat;
 /** Limit delivery; omitted/'all' = every channel the user allows for plugin notifications. */
 channels?:(NotifyChannelKey|'all')[];
 overrides?:Partial<Record<NotifyChannelKey,NotificationChannelContent>>;
 silent?:boolean;job_ref?:string;dedupe_key?:string;image_url?:string;buttons?:{text:string;url?:string;callback_data?:string}[][]
}
export interface NotificationDelivery {channel:NotifyChannelKey;status:'sent'|'skipped'|'failed';reason?:'not_configured'|'disabled'|'quiet_hours';error?:string;format?:NotificationFormat;preserved?:string[];dropped?:string[]}
export interface NotificationResult {event:string;accepted:boolean;deduplicated?:boolean;suppressed?:boolean;suppression_reason?:string;channels?:{channel:string;preserved?:string[];dropped?:string[]}[];deliveries?:NotificationDelivery[]}
export interface NotifyChannelInfo {channel:NotifyChannelKey;name:string;configured:boolean;enabled:boolean;quiet_now:boolean;deliverable:boolean;formats:NotificationFormat[];capabilities:string[];max_body_runes:number;notes?:string}
export interface CookieCloudSnapshot {revision:string;domains:{domain:string;cookie_count:number}[];cookies:Cookie[]}
export interface CookieCloudClient {
 (operation:'read',options:{domains?:string[]}):Promise<CookieCloudSnapshot>;
 (operation:'write',options:{domains:string[];cookies:Cookie[];revision:string}):Promise<{revision:string}>;
}
export interface KVEntry {key:string;revision:number;encrypted_bytes:number}
export interface Run {id:string;job_id:string;business_key:string;revision:string;status:'queued'|'running'|'failed'|'succeeded'|'cancelled'|'attention_required';attempted:boolean;stage:string;progress:number;message:string;total?:number;done?:number;failed?:number;input?:JSONValue;result?:JSONValue;checkpoint?:JSONValue;error?:string;logs?:string[];created_at:string;updated_at:string}
export interface APIError extends Error {status:number;method:string;path:string;data:unknown}
