import type { HostAPI, HTTPClient, Files, CD2Client, Notification, NotificationResult, NotifyChannelInfo, CookieCloudClient, WatchInput, JSONValue, ListenerState, MessagingContext, HTTPRequest, PluginWebSocket, HTTPStream, TCPSocket, TCPServer, ResponseStreams } from './core-types.js'
export type Bytes = Uint8Array
export type BinaryInput = string|Uint8Array|ArrayBuffer
export type Output = 'hex'|'base64'|'base64url'|'utf8'|'bytes'
export interface HTMLSelection {
 readonly length:number;find(selector:string):HTMLSelection;filter(selector:string):HTMLSelection;not(selector:string):HTMLSelection;is(selector:string):boolean;
 eq(index:number):HTMLSelection;first():HTMLSelection;last():HTMLSelection;parent(selector?:string):HTMLSelection;closest(selector:string):HTMLSelection;children(selector?:string):HTMLSelection;
 next(selector?:string):HTMLSelection;prev(selector?:string):HTMLSelection;siblings():HTMLSelection;
 text():string;html():string;outerHTML():string;attr(name:string):string|null;attrs():Record<string,string>;url(attr?:string):string|null;hasClass(name:string):boolean;
 toArray():HTMLSelection[];map<T>(fn:(item:HTMLSelection,index:number)=>T):T[];each(fn:(item:HTMLSelection,index:number)=>void|false):HTMLSelection;
}
export interface XMLNode {name:string;attrs:Record<string,string>;text:string;children:XMLNode[]}
export interface AESOptions {mode?:'cbc'|'gcm'|'ctr'|'ecb';key:BinaryInput;iv?:BinaryInput;data:BinaryInput;aad?:BinaryInput;padding?:'pkcs7'|'none';output?:Output}
export interface RSAOptions {key:string;data:BinaryInput;padding?:'pkcs1'|'oaep'|'pss';hash?:string;signature?:BinaryInput;output?:Output}
export interface BackgroundContext extends MessagingContext {
 ws:{connect(options:string|(HTTPRequest&{protocols?:string[];max_message_bytes?:number})):Promise<PluginWebSocket>};
 /** Requires the network.tcp grant. */
 tcp:{connect(options:{host:string;port:number;tls?:boolean;server_name?:string;insecure?:boolean;timeout_seconds?:number}):Promise<TCPSocket>;listen(options:{port:number;host?:string}):Promise<TCPServer>};
 /** Only inside an HTTP handler. */
 response?:ResponseStreams;
 api:HostAPI;http:HTTPClient&{stream(options:HTTPRequest):Promise<HTTPStream>};files:Files;cd2:CD2Client;notify(options:Notification):Promise<NotificationResult>;cookiecloud:CookieCloudClient;
 notifications:{send(options:Notification):Promise<NotificationResult>;channels():Promise<NotifyChannelInfo[]>};
 storage:{get<T=JSONValue>(key:string):Promise<T|null>;set(key:string,value:JSONValue):Promise<number>;remove(key:string):Promise<void>};
 task:{id:string;checkpointValue:JSONValue;/** total/done/failed 为任务级计数：宿主任务队列显示“已处理 done/total”；只给计数时进度按 (done+failed)/total 计算，宿主文件移动的进度不再覆盖整体进度。 */update(value:{stage?:string;message?:string;progress?:number;total?:number;done?:number;failed?:number}):Promise<void>;log(message:string):Promise<void>;checkpoint(value:JSONValue):Promise<void>};
 watch:{add(value:WatchInput):Promise<void>;remove(id:string):Promise<void>};sleep(milliseconds:number):Promise<void>;
 settings:{get<T=Record<string,JSONValue>>():Promise<T>};
 plugin:{id:string;name:string;version:string;generation:string;revision:string;host_api:string};
 server:{list():Promise<ListenerState[]>;listen(options:{id:string;port:number;host?:string}):Promise<ListenerState>;close(id:string):Promise<void>;hookPath:string;publicHookPath?:string};
 codec:{utf8Encode(text:string):Bytes;utf8Decode(data:BinaryInput):string;encode(text:string,charset?:string):Bytes;decode(data:BinaryInput,charset?:string,options?:{fatal?:boolean}):string;
  base64Encode(data:BinaryInput,options?:{url?:boolean}):string;base64Decode(text:string):Bytes;hexEncode(data:BinaryInput):string;hexDecode(text:string):Bytes;concat(...parts:BinaryInput[]):Bytes};
 crypto:{randomUUID():string;randomBytes(size:number):Bytes;getRandomValues<T extends ArrayBufferView>(array:T):T;
  hash(algorithm:'md5'|'sha1'|'sha224'|'sha256'|'sha384'|'sha512',data:BinaryInput,output?:Output):string|Bytes;md5(data:BinaryInput,output?:Output):string;sha1(data:BinaryInput,output?:Output):string;sha256(data:BinaryInput,output?:Output):string;sha512(data:BinaryInput,output?:Output):string;
  hmac(algorithm:string,key:BinaryInput,data:BinaryInput,output?:Output):string|Bytes;aesEncrypt(options:AESOptions):string|Bytes;aesDecrypt(options:AESOptions):string|Bytes;
  rsaEncrypt(options:RSAOptions):string|Bytes;rsaDecrypt(options:RSAOptions):string|Bytes;rsaSign(options:RSAOptions):string|Bytes;rsaVerify(options:RSAOptions):boolean};
 html:{load(source:string,options?:{baseURL?:string}):HTMLSelection;select(source:string,selector:string,options?:{baseURL?:string}):{text:string;html:string;attrs:Record<string,string>}[]};
 xml:{parse(source:string):XMLNode};
}
export type RecoveryDecision = {action:'complete';result?:JSONValue}|{action:'resume'}|{action:'attention'}
