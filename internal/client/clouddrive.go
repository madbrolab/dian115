package client

import (
	"context"
	"fmt"
	"io"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/metadata"
	"google.golang.org/protobuf/types/known/emptypb"

	"strm-manager/internal/model"
	pb "strm-manager/internal/pb"
)

// CloudDriveClient CD2 gRPC客户端
type CloudDriveClient struct {
	host        string
	username    string
	password    string
	apiToken    string // 预先创建的 API 令牌
	conn        *grpc.ClientConn
	client      pb.CloudDriveFileSrvClient
	jwtToken    string
	tokenTime   time.Time
	useAPIToken bool // 是否使用 API Token 模式
	mu          sync.RWMutex
}

// NewCloudDriveClient 创建CD2客户端（使用用户名密码认证）
func NewCloudDriveClient(host, username, password string) *CloudDriveClient {
	host = normalizeHost(host)
	return &CloudDriveClient{
		host:        host,
		username:    username,
		password:    password,
		useAPIToken: false,
	}
}

// NewCloudDriveClientWithToken 创建CD2客户端（使用预先创建的 API Token）
func NewCloudDriveClientWithToken(host, apiToken string) *CloudDriveClient {
	host = normalizeHost(host)
	return &CloudDriveClient{
		host:        host,
		apiToken:    apiToken,
		useAPIToken: true,
	}
}

// normalizeHost 规范化主机地址
func normalizeHost(host string) string {
	// 确保host有正确格式
	if !strings.HasPrefix(host, "http://") && !strings.HasPrefix(host, "https://") {
		host = "http://" + host
	}
	// 移除http://前缀，gRPC只需要host:port
	host = strings.TrimPrefix(host, "http://")
	host = strings.TrimPrefix(host, "https://")
	return host
}

// Connect 建立gRPC连接
func (c *CloudDriveClient) Connect() error {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.conn != nil {
		return nil
	}

	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

	conn, err := grpc.DialContext(ctx, c.host,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithBlock())
	if err != nil {
		return fmt.Errorf("连接CD2失败: %v", err)
	}

	c.conn = conn
	c.client = pb.NewCloudDriveFileSrvClient(conn)
	return nil
}

// Close 关闭连接
func (c *CloudDriveClient) Close() error {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.conn != nil {
		err := c.conn.Close()
		c.conn = nil
		c.client = nil
		return err
	}
	return nil
}

// Authenticate 获取 JWT 令牌
func (c *CloudDriveClient) Authenticate(ctx context.Context) error {
	if err := c.Connect(); err != nil {
		return err
	}

	req := &pb.GetTokenRequest{
		UserName: c.username,
		Password: c.password,
	}

	resp, err := c.client.GetToken(ctx, req)
	if err != nil {
		return fmt.Errorf("认证失败: %v", err)
	}

	if !resp.Success {
		return fmt.Errorf("认证失败: %s", resp.ErrorMessage)
	}

	c.mu.Lock()
	c.jwtToken = resp.Token
	c.tokenTime = time.Now()
	c.mu.Unlock()

	return nil
}

// Login 登录获取token (兼容旧接口)
func (c *CloudDriveClient) Login() error {
	// 如果使用 API Token 模式，直接返回成功
	if c.useAPIToken {
		return c.Connect()
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	return c.Authenticate(ctx)
}

// SetJwtToken 直接设置 JWT Token（用于使用预先创建的 API Token）
func (c *CloudDriveClient) SetJwtToken(token string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.jwtToken = token
	c.tokenTime = time.Now()
}

// SetAPIToken 设置 API Token 并切换到 Token 模式
func (c *CloudDriveClient) SetAPIToken(token string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.apiToken = token
	c.useAPIToken = true
}

// GetCurrentToken 获取当前使用的 Token
func (c *CloudDriveClient) GetCurrentToken() string {
	c.mu.RLock()
	defer c.mu.RUnlock()
	if c.useAPIToken {
		return c.apiToken
	}
	return c.jwtToken
}

// ensureToken 确保token有效
func (c *CloudDriveClient) ensureToken() error {
	// 如果使用 API Token 模式，只需确保连接
	if c.useAPIToken {
		return c.Connect()
	}

	c.mu.RLock()
	tokenValid := c.jwtToken != "" && time.Since(c.tokenTime) < 30*time.Minute
	c.mu.RUnlock()

	if tokenValid {
		return nil
	}

	return c.Login()
}

// createAuthorizedContext 创建带授权头的上下文
func (c *CloudDriveClient) createAuthorizedContext(ctx context.Context) context.Context {
	c.mu.RLock()
	var token string
	if c.useAPIToken {
		token = c.apiToken
	} else {
		token = c.jwtToken
	}
	c.mu.RUnlock()

	if token == "" {
		return ctx
	}

	md := metadata.Pairs("authorization", fmt.Sprintf("Bearer %s", token))
	return metadata.NewOutgoingContext(ctx, md)
}

// TestConnection 测试连接
func (c *CloudDriveClient) TestConnection() error {
	if c.useAPIToken {
		// 使用 API Token 模式时，尝试获取系统信息来测试连接
		if err := c.Connect(); err != nil {
			return err
		}
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		_, err := c.GetSystemInfo(ctx)
		return err
	}
	return c.Login()
}

// GetSystemInfo 获取系统信息(无需认证)
func (c *CloudDriveClient) GetSystemInfo(ctx context.Context) (*pb.CloudDriveSystemInfo, error) {
	if err := c.Connect(); err != nil {
		return nil, err
	}
	return c.client.GetSystemInfo(ctx, &emptypb.Empty{})
}

// GetSubFiles 列出目录中的文件
func (c *CloudDriveClient) GetSubFiles(ctx context.Context, path string, forceRefresh bool) ([]*pb.CloudDriveFile, error) {
	if err := c.ensureToken(); err != nil {
		return nil, err
	}

	req := &pb.ListSubFileRequest{
		Path:         path,
		ForceRefresh: forceRefresh,
	}

	authCtx := c.createAuthorizedContext(ctx)
	stream, err := c.client.GetSubFiles(authCtx, req)
	if err != nil {
		return nil, fmt.Errorf("获取子文件失败: %v", err)
	}

	var files []*pb.CloudDriveFile
	for {
		resp, err := stream.Recv()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, fmt.Errorf("接收流时出错: %v", err)
		}
		files = append(files, resp.SubFiles...)
	}

	return files, nil
}

// FindFileByPath 根据路径查找文件
func (c *CloudDriveClient) FindFileByPath(ctx context.Context, path string) (*pb.CloudDriveFile, error) {
	if err := c.ensureToken(); err != nil {
		return nil, err
	}

	// 分离父路径和文件名
	parentPath := "/"
	fileName := path
	if idx := strings.LastIndex(path, "/"); idx > 0 {
		parentPath = path[:idx]
		fileName = path[idx+1:]
	} else if idx == 0 {
		parentPath = "/"
		fileName = path[1:]
	}

	req := &pb.FindFileByPathRequest{
		ParentPath: parentPath,
		Path:       fileName,
	}

	authCtx := c.createAuthorizedContext(ctx)
	return c.client.FindFileByPath(authCtx, req)
}

// CreateFolder 创建新文件夹
func (c *CloudDriveClient) CreateFolder(ctx context.Context, parentPath, folderName string) (*pb.CreateFolderResult, error) {
	if err := c.ensureToken(); err != nil {
		return nil, err
	}

	req := &pb.CreateFolderRequest{
		ParentPath: parentPath,
		FolderName: folderName,
	}

	authCtx := c.createAuthorizedContext(ctx)
	return c.client.CreateFolder(authCtx, req)
}

// DeleteFile 删除文件或文件夹
func (c *CloudDriveClient) DeleteFile(ctx context.Context, filePath string) (*pb.FileOperationResult, error) {
	if err := c.ensureToken(); err != nil {
		return nil, err
	}

	req := &pb.FileRequest{
		Path: filePath,
	}

	authCtx := c.createAuthorizedContext(ctx)
	return c.client.DeleteFile(authCtx, req)
}

// DeleteFiles 批量删除文件
func (c *CloudDriveClient) DeleteFiles(ctx context.Context, filePaths []string) (*pb.FileOperationResult, error) {
	if err := c.ensureToken(); err != nil {
		return nil, err
	}

	req := &pb.MultiFileRequest{
		Path: filePaths,
	}

	authCtx := c.createAuthorizedContext(ctx)
	return c.client.DeleteFiles(authCtx, req)
}

// RenameFile 重命名文件
func (c *CloudDriveClient) RenameFile(ctx context.Context, filePath, newName string) (*pb.FileOperationResult, error) {
	if err := c.ensureToken(); err != nil {
		return nil, err
	}

	req := &pb.RenameFileRequest{
		TheFilePath: filePath,
		NewName:     newName,
	}

	authCtx := c.createAuthorizedContext(ctx)
	return c.client.RenameFile(authCtx, req)
}

// MoveFile 移动文件
func (c *CloudDriveClient) MoveFile(ctx context.Context, filePaths []string, destPath string) (*pb.FileOperationResult, error) {
	if err := c.ensureToken(); err != nil {
		return nil, err
	}

	req := &pb.MoveFileRequest{
		TheFilePaths: filePaths,
		DestPath:     destPath,
	}

	authCtx := c.createAuthorizedContext(ctx)
	return c.client.MoveFile(authCtx, req)
}

// CopyFile 复制文件
func (c *CloudDriveClient) CopyFile(ctx context.Context, filePaths []string, destPath string) (*pb.FileOperationResult, error) {
	if err := c.ensureToken(); err != nil {
		return nil, err
	}

	req := &pb.CopyFileRequest{
		TheFilePaths: filePaths,
		DestPath:     destPath,
	}

	authCtx := c.createAuthorizedContext(ctx)
	return c.client.CopyFile(authCtx, req)
}

// GetSearchResults 搜索文件
func (c *CloudDriveClient) GetSearchResults(ctx context.Context, path, searchFor string, fuzzyMatch bool) ([]*pb.CloudDriveFile, error) {
	if err := c.ensureToken(); err != nil {
		return nil, err
	}

	req := &pb.SearchRequest{
		Path:         path,
		SearchFor:    searchFor,
		ForceRefresh: false,
		FuzzyMatch:   fuzzyMatch,
	}

	authCtx := c.createAuthorizedContext(ctx)
	stream, err := c.client.GetSearchResults(authCtx, req)
	if err != nil {
		return nil, fmt.Errorf("搜索文件失败: %v", err)
	}

	var files []*pb.CloudDriveFile
	for {
		resp, err := stream.Recv()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, fmt.Errorf("接收流时出错: %v", err)
		}
		files = append(files, resp.SubFiles...)
	}

	return files, nil
}

// GetSpaceInfo 获取空间信息
func (c *CloudDriveClient) GetSpaceInfo(ctx context.Context, path string) (*pb.SpaceInfo, error) {
	if err := c.ensureToken(); err != nil {
		return nil, err
	}

	req := &pb.FileRequest{
		Path: path,
	}

	authCtx := c.createAuthorizedContext(ctx)
	return c.client.GetSpaceInfo(authCtx, req)
}

// GetFileDetailProperties 获取文件详细属性
func (c *CloudDriveClient) GetFileDetailProperties(ctx context.Context, path string) (*pb.FileDetailProperties, error) {
	if err := c.ensureToken(); err != nil {
		return nil, err
	}

	req := &pb.FileRequest{
		Path: path,
	}

	authCtx := c.createAuthorizedContext(ctx)
	return c.client.GetFileDetailProperties(authCtx, req)
}

// GetDownloadUrlPath 获取下载URL路径
func (c *CloudDriveClient) GetDownloadUrlPath(ctx context.Context, path string, preview bool, getDirectUrl bool) (*pb.DownloadUrlPathInfo, error) {
	if err := c.ensureToken(); err != nil {
		return nil, err
	}

	req := &pb.GetDownloadUrlPathRequest{
		Path:         path,
		Preview:      preview,
		GetDirectUrl: getDirectUrl,
	}

	authCtx := c.createAuthorizedContext(ctx)
	return c.client.GetDownloadUrlPath(authCtx, req)
}

// GetAllCloudApis 获取所有云盘API
func (c *CloudDriveClient) GetAllCloudApis(ctx context.Context) (*pb.CloudAPIList, error) {
	if err := c.ensureToken(); err != nil {
		return nil, err
	}

	authCtx := c.createAuthorizedContext(ctx)
	return c.client.GetAllCloudApis(authCtx, &emptypb.Empty{})
}

// GetMountPoints 获取所有挂载点
func (c *CloudDriveClient) GetMountPoints(ctx context.Context) (*pb.GetMountPointsResult, error) {
	if err := c.ensureToken(); err != nil {
		return nil, err
	}

	authCtx := c.createAuthorizedContext(ctx)
	return c.client.GetMountPoints(authCtx, &emptypb.Empty{})
}

// PushMessage 订阅推送消息流
func (c *CloudDriveClient) PushMessage(ctx context.Context) (pb.CloudDriveFileSrv_PushMessageClient, error) {
	if err := c.ensureToken(); err != nil {
		return nil, err
	}

	authCtx := c.createAuthorizedContext(ctx)
	return c.client.PushMessage(authCtx, &emptypb.Empty{})
}

// GetRuntimeInfo 获取运行时信息
func (c *CloudDriveClient) GetRuntimeInfo(ctx context.Context) (*pb.RuntimeInfo, error) {
	if err := c.ensureToken(); err != nil {
		return nil, err
	}

	authCtx := c.createAuthorizedContext(ctx)
	return c.client.GetRuntimeInfo(authCtx, &emptypb.Empty{})
}

// GetRunningInfo 获取运行状态信息
func (c *CloudDriveClient) GetRunningInfo(ctx context.Context) (*pb.RunInfo, error) {
	if err := c.ensureToken(); err != nil {
		return nil, err
	}

	authCtx := c.createAuthorizedContext(ctx)
	return c.client.GetRunningInfo(authCtx, &emptypb.Empty{})
}

// ForceExpireDirCache 强制刷新目录缓存
func (c *CloudDriveClient) ForceExpireDirCache(ctx context.Context, path string) error {
	if err := c.ensureToken(); err != nil {
		return err
	}

	req := &pb.FileRequest{
		Path: path,
	}

	authCtx := c.createAuthorizedContext(ctx)
	_, err := c.client.ForceExpireDirCache(authCtx, req)
	return err
}

// GetMetaData 获取文件元数据
func (c *CloudDriveClient) GetMetaData(ctx context.Context, path string) (*pb.FileMetaData, error) {
	if err := c.ensureToken(); err != nil {
		return nil, err
	}

	req := &pb.FileRequest{
		Path: path,
	}

	authCtx := c.createAuthorizedContext(ctx)
	return c.client.GetMetaData(authCtx, req)
}

// AddOfflineFiles 添加离线下载任务
func (c *CloudDriveClient) AddOfflineFiles(ctx context.Context, urls, toFolder string) (*pb.FileOperationResult, error) {
	if err := c.ensureToken(); err != nil {
		return nil, err
	}

	req := &pb.AddOfflineFileRequest{
		Urls:     urls,
		ToFolder: toFolder,
	}

	authCtx := c.createAuthorizedContext(ctx)
	return c.client.AddOfflineFiles(authCtx, req)
}

// ListOfflineFilesByPath 列出离线下载文件
func (c *CloudDriveClient) ListOfflineFilesByPath(ctx context.Context, path string) (*pb.OfflineFileListResult, error) {
	if err := c.ensureToken(); err != nil {
		return nil, err
	}

	req := &pb.FileRequest{
		Path: path,
	}

	authCtx := c.createAuthorizedContext(ctx)
	return c.client.ListOfflineFilesByPath(authCtx, req)
}

// GetCloudMemberships 获取云盘会员信息
func (c *CloudDriveClient) GetCloudMemberships(ctx context.Context, path string) (*pb.CloudMemberships, error) {
	if err := c.ensureToken(); err != nil {
		return nil, err
	}

	req := &pb.FileRequest{
		Path: path,
	}

	authCtx := c.createAuthorizedContext(ctx)
	return c.client.GetCloudMemberships(authCtx, req)
}

// ============ 兼容旧接口的方法 ============

// ListFiles 列出目录下的文件 (兼容旧接口)
func (c *CloudDriveClient) ListFiles(path string) ([]*model.FileInfo, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	files, err := c.GetSubFiles(ctx, path, false)
	if err != nil {
		return nil, err
	}

	var result []*model.FileInfo
	for _, f := range files {
		result = append(result, &model.FileInfo{
			Path:     f.FullPathName,
			Name:     f.Name,
			Size:     f.Size,
			IsDir:    f.IsDirectory,
			PickCode: f.Id,
		})
	}

	return result, nil
}

// GetFileInfo 获取文件信息 (兼容旧接口)
func (c *CloudDriveClient) GetFileInfo(path string) (*model.FileInfo, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	file, err := c.FindFileByPath(ctx, path)
	if err != nil {
		return nil, err
	}

	return &model.FileInfo{
		Path:     file.FullPathName,
		Name:     file.Name,
		Size:     file.Size,
		IsDir:    file.IsDirectory,
		PickCode: file.Id,
	}, nil
}

// GetPickCode 获取文件的pickcode (兼容旧接口)
func (c *CloudDriveClient) GetPickCode(path string) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	file, err := c.FindFileByPath(ctx, path)
	if err != nil {
		return "", err
	}

	if file.Id != "" {
		return file.Id, nil
	}

	return "", fmt.Errorf("未找到pickcode")
}

// WalkDir 递归遍历目录（串行版本，保留兼容性）
func (c *CloudDriveClient) WalkDir(path string, fn func(*model.CD2FileInfo) error) error {
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()

	files, err := c.GetSubFiles(ctx, path, false)
	if err != nil {
		return err
	}

	for _, f := range files {
		info := &model.CD2FileInfo{
			Name:     f.Name,
			Path:     f.FullPathName,
			Size:     f.Size,
			IsDir:    f.IsDirectory,
			PickCode: f.Id,
		}

		if err := fn(info); err != nil {
			return err
		}

		// 递归处理子目录
		if f.IsDirectory {
			if err := c.WalkDir(f.FullPathName, fn); err != nil {
				return err
			}
		}
	}

	return nil
}

// WalkDirConcurrent 并发遍历目录（高性能版本）
func (c *CloudDriveClient) WalkDirConcurrent(rootPath string, workerCount int, fn func(*model.CD2FileInfo) error) error {
	if workerCount <= 0 {
		workerCount = 10 // 默认10个并发
	}

	// 创建目录队列和文件通道
	dirQueue := make(chan string, 10000)
	fileChan := make(chan *model.CD2FileInfo, 1000)
	errChan := make(chan error, 1)

	var wg sync.WaitGroup
	var activeWorkers int32
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// 启动目录扫描工作线程
	for i := 0; i < workerCount; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for {
				select {
				case <-ctx.Done():
					return
				case dirPath, ok := <-dirQueue:
					if !ok {
						return
					}
					atomic.AddInt32(&activeWorkers, 1)
					c.scanDirForWalk(ctx, dirPath, dirQueue, fileChan)
					atomic.AddInt32(&activeWorkers, -1)
				}
			}
		}()
	}

	// 启动文件处理goroutine
	var processErr error
	var processErrMu sync.Mutex
	go func() {
		for file := range fileChan {
			if err := fn(file); err != nil {
				processErrMu.Lock()
				if processErr == nil {
					processErr = err
					cancel() // 取消所有工作
				}
				processErrMu.Unlock()
				return
			}
		}
	}()

	// 将根目录放入队列
	dirQueue <- rootPath

	// 等待扫描完成
	go func() {
		time.Sleep(200 * time.Millisecond)
		for {
			select {
			case <-ctx.Done():
				close(dirQueue)
				return
			default:
				if len(dirQueue) == 0 && atomic.LoadInt32(&activeWorkers) == 0 {
					time.Sleep(500 * time.Millisecond)
					if len(dirQueue) == 0 && atomic.LoadInt32(&activeWorkers) == 0 {
						close(dirQueue)
						return
					}
				}
				time.Sleep(100 * time.Millisecond)
			}
		}
	}()

	wg.Wait()
	close(fileChan)

	// 检查是否有错误
	select {
	case err := <-errChan:
		return err
	default:
	}

	processErrMu.Lock()
	defer processErrMu.Unlock()
	return processErr
}

// scanDirForWalk 扫描单个目录用于WalkDirConcurrent
func (c *CloudDriveClient) scanDirForWalk(ctx context.Context, path string, dirQueue chan string, fileChan chan *model.CD2FileInfo) {
	select {
	case <-ctx.Done():
		return
	default:
	}

	reqCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()

	files, err := c.GetSubFiles(reqCtx, path, false)
	if err != nil {
		return
	}

	for _, f := range files {
		select {
		case <-ctx.Done():
			return
		default:
		}

		info := &model.CD2FileInfo{
			Name:     f.Name,
			Path:     f.FullPathName,
			Size:     f.Size,
			IsDir:    f.IsDirectory,
			PickCode: f.Id,
		}

		if f.IsDirectory {
			// 将子目录加入队列
			select {
			case dirQueue <- f.FullPathName:
			case <-ctx.Done():
				return
			default:
				// 队列满了，直接递归
				c.scanDirForWalk(ctx, f.FullPathName, dirQueue, fileChan)
			}
		} else {
			// 发送文件到处理通道
			select {
			case fileChan <- info:
			case <-ctx.Done():
				return
			}
		}
	}
}
