# Security

## 凭据

生产适配器只从环境变量读取凭据。不要将真实密钥写入：

- `backend.json`
- `project.json`
- `state.json`
- JSONL manifest
- Provider 日志
- Issue、Pull Request 或 Actions 日志

如果密钥被提交：

1. 立即在服务商控制台撤销密钥。
2. 创建新密钥。
3. 清理 Git 历史前先评估已有 Fork、缓存和发布包。
4. 不要仅通过一次普通提交删除文件后继续使用旧密钥。

## 付费任务

适配器保存内容寻址的本地执行记录。如果请求可能已到达服务端但预测 ID 未能保存，会
进入 `submission_uncertain`，并停止自动重试。

只有在服务商控制台确认后，才可以显式释放保护：

```bash
python scripts/replicate_backend.py release <project-dir> "<job-id>" --yes
```

## 私密素材

处理肖像、客户视频、内部产品或未发布素材前，检查：

- 服务商和具体模型的数据保留政策；
- 素材是否允许上传到第三方；
- 输出是否可以用于预期的商业场景；
- 本地项目包是否包含不应共享的媒体。

## 报告问题

不要在公开 Issue 中附带密钥、私密素材、完整请求头或可访问的临时媒体 URL。通过仓库
维护者指定的私密渠道提供最小复现信息。
