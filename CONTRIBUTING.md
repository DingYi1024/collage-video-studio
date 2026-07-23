# 贡献与维护

## 修改原则

- 保持 `project.json`、`state.json`、JSONL manifest 和后端实现之间的边界。
- 新增服务商时优先增加独立适配器，不把服务商字段写进故事或渲染层。
- 不修改用户原始图片和视频。
- 付费请求必须可恢复，并在提交结果不确定时停止自动重试。
- 不在仓库中加入 API 密钥、真实客户素材或生成结果。

## 开发流程

1. 从 `main` 创建短期分支。
2. 修改代码和对应文档。
3. 在 `CHANGELOG.md` 的 `Unreleased` 中记录用户可见变化。
4. 运行：

   ```bash
   python scripts/selftest.py
   python scripts/package_skill.py --output dist/collage-video-studio.skill --force
   ```

5. 提交只包含本次工作范围的文件。
6. 通过 Pull Request 合并，避免直接在 `main` 上进行大改。

## 后端改动

变更生产后端时至少验证：

- 六种 job kind 都有明确路由；
- 本地文件句柄正确关闭；
- 已有 prediction ID 会恢复轮询；
- 输出不存在时不会静默重新付费；
- 异常文本和日志中不含凭据；
- 下载结果非空并通过媒体探测；
- 适配器契约测试仍然通过。

## 发布

1. 将 `Unreleased` 内容移动到新版本标题。
2. 更新 `VERSION`。
3. 合并到 `main`。
4. 创建并推送与版本一致的 Tag，例如 `v1.1.0`。
5. GitHub Actions 自测通过后自动创建 Release，并附上 `.skill`。
