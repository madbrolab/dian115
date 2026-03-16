# 构建阶段
FROM golang:1.24-alpine AS builder

# 安装构建依赖
RUN apk add --no-cache gcc musl-dev sqlite-dev

WORKDIR /app

# 复制go mod文件
COPY go.mod go.sum* ./

# 复制源代码（需要先复制以便go mod tidy能分析依赖）
COPY cmd/ ./cmd/
COPY internal/ ./internal/
COPY static/ ./static/

# 下载依赖并生成go.sum
RUN go mod tidy && go mod download

# 构建
RUN CGO_ENABLED=1 GOOS=linux go build -a -ldflags '-linkmode external -extldflags "-static"' -o strm-manager ./cmd/main.go

# 运行阶段
FROM alpine:3.19

# 安装运行时依赖
RUN apk add --no-cache ca-certificates tzdata

# 设置时区
ENV TZ=Asia/Shanghai

WORKDIR /app

# 从构建阶段复制二进制文件
COPY --from=builder /app/strm-manager /app/strm-manager

# 复制前端文件
COPY --from=builder /app/static /app/static

# 创建数据目录
RUN mkdir -p /app/config /app/data

# 暴露端口
EXPOSE 8095 8098

# 数据卷
VOLUME ["/app/config", "/app/data", "/data/strm"]

# 启动命令
ENTRYPOINT ["/app/strm-manager"]
CMD ["-db", "/config/dian115.db"]