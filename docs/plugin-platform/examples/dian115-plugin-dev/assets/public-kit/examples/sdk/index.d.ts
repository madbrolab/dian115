import type { HostAPI, HTTPClient, Files, CD2Client, WatchInput, WatchRecord, Notification, NotificationResult, NotifyChannelInfo, CookieCloudClient, KVEntry, Run, OK, JSONValue, ListenerState, FileWriteResult } from './core-types.js'
export * from './core-types.js'
export type Request = (method:string,path:string,body?:unknown,source?:{plugin_id:string;generation?:string;revision?:string})=>Promise<unknown>
export interface PluginContext {
 id:string;api:HostAPI;
 storage:{get<T=JSONValue>(key:string):Promise<T|null>;set(key:string,value:JSONValue,expected_revision?:number):Promise<{revision:number}>;remove(key:string):Promise<OK>;list(limit?:number,offset?:number):Promise<KVEntry[]>};
 http:HTTPClient;files:Files&{start(options:{operation:'move'|'copy'|'remove'}&Record<string,JSONValue>):Promise<{task_id:string}>;downloadURL(path:string,options?:{inline?:boolean}):string;upload(path:string,file:Blob):Promise<FileWriteResult>};cd2:CD2Client;
 server:{list():Promise<ListenerState[]>;listen(options:{id:string;port:number;host?:string}):Promise<ListenerState>;close(id:string):Promise<OK>;hookURL(path?:string):string;publicHookURL(path?:string):string};
 settings:{get<T=Record<string,JSONValue>>():Promise<T>;set(value:Record<string,JSONValue>):Promise<{revision:number}>};
 events:{catalog():Promise<{type:string;group:string;name:string;description:string}[]>};
 watch:{list():Promise<WatchRecord[]>;add(options:WatchInput):Promise<OK>;remove(id:string):Promise<OK>};
 tasks:{run(job:string,business_key:string,input?:JSONValue):Promise<Run>;list(limit?:number,offset?:number):Promise<Run[]>;get(id:string):Promise<Run>;cancel(id:string):Promise<OK>;retry(id:string):Promise<Run>};
 notify(options:Notification):Promise<NotificationResult>;
 notifications:{send(options:Notification):Promise<NotificationResult>;channels():Promise<NotifyChannelInfo[]>};cookiecloud:CookieCloudClient;usage():Promise<Record<string,number>>;
 theme?:{readonly mode:'light'|'dark';subscribe(fn:(mode:'light'|'dark')=>void):()=>void};signal?:AbortSignal;
}
export function createPluginContext(id:string,request:Request,options?:{generation?:string;revision?:string;baseURL?:string}):PluginContext
