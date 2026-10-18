# GitHub 发布准备

目标仓库：`https://github.com/Watendy66/Daily-News-Glimpse.git`

建议描述：

> A quiet Windows desktop news widget for AI, education and psychology, with Chinese briefs, source images and guided reading.

建议 Topics：`python`、`pyside6`、`windows`、`rss`、`desktop-widget`、`news-reader`、`education`。

## 本次源码包已做的准备

- 排除 `.venv`、数据库、日志、下载的新闻图片、密钥文件、构建目录和个人背景。
- 使用相对路径安装与构建，不包含本机账户名称或开发目录。
- 提供 README、第三方说明、离线测试、Windows CI 和手动 EXE 构建工作流。
- 运行依赖与构建依赖分开。
- 批处理统一使用英文指令与 Windows 换行，避免中文编码导致启动命令截断。

## 发布前仍需确认

- 源码许可证尚未指定；按发布意图选择并添加后，才能明确授予别人使用、修改和再分发的权限。
- 个人背景图默认不上传，字体文件不上传。
- 远程仓库已有文件时先合并，禁止强制推送覆盖历史。

## 推送方式

在此项目文件夹打开终端。如果已经关联远程仓库，只需完成提交并推送：

```powershell
git status
git add .
git commit -m "Prepare Daily News Glimpse desktop widget"
git push -u origin main
```

若远程有尚未合并的提交，先停止推送并检查差异。不要使用 `--force`。

没有命令行登录时，也可以在 VS Code 中打开本项目，用“源代码管理”登录 GitHub 后提交与同步。不要把访问令牌写入源码、README 或仓库远程地址。
