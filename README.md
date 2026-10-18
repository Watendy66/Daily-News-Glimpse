# 拾光简报 · Daily Glimpse

一个安静放在 Windows 桌面上的中文新闻按钮，每天精选 AI、教育与心理资讯，让阅读从“看到了什么”继续走向“该怎样理解”。

仓库：<https://github.com/Watendy66/Daily-News-Glimpse>

## 能做什么

- 点击“今日新闻”桌面按钮展开，再次点击收起；按钮可拖动。
- 每日精选 5 条，默认目标为 **AI 2 条、教育 2 条、心理 1 条**。某类不足时仅从其余关注主题补足；首次联网仍不足 5 条时显示提示。
- 仅选近 7 天内容，保留真实发布时间；心理科研进展并非每天发布。
- 标题、摘要显示简体中文，保留 AI、BBC 等必要英文。
- 新闻缩略图、来源配图、原文入口，以及事实摘要、影响路径、思考问题和后续观察点。
- 背景透明度单独调节，文字保持清晰；窗口可拖动、缩放，外观设置自动保存。
- 程序运行时每天北京时间 **08:00** 更新，收起后仍运行。右键按钮可刷新或退出，展开时可按 **F5** 刷新。
- 本地缓存和相似报道追踪，不需要 API 密钥。

## 快速运行

支持 Windows 11；当前使用 Python **3.12** 验证，安装脚本接受 Python 3.11 / 3.12。

```powershell
git clone https://github.com/Watendy66/Daily-News-Glimpse.git
cd Daily-News-Glimpse
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

然后双击 `run.bat`。启动后先显示桌面按钮，点击展开新闻。启动脚本可能短暂显示命令窗口。

如果使用 Conda，先激活一个 Python 3.11 / 3.12 环境，再运行安装脚本。也可以指定已有解释器，脚本会在项目内创建独立 `.venv`：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -Python "D:\YourConda\python.exe"
```

无需修改系统环境变量，也不会向 Conda 的原环境安装项目依赖。`install.bat` 是安装脚本的双击入口。

## 背景和字体

仓库默认使用内置暖色底色。要使用自己的背景，把有权使用的图片保存为 `assets/background.jpg`，重启即可。图片按比例显示，窗口缩放时不拉伸。

背景图属于本地个性化资源，默认被 Git 忽略。仓库不包含原开发者的个人背景图片、字体文件或新闻图片缓存。

字体优先使用已安装的**华文中宋 / STZhongsong**，缺少时回退到微软雅黑；英文由系统字体补齐。

## 来源与配置

默认配置位于 `sources.json`，包含 IT之家、科学网、教育部、中科院心理所、Solidot 和 BBC 中文等来源。程序仅筛选 AI、教育、心理主题，关键词分类可能误判，具体信息以原文为准。

首次运行会复制配置到 `%LOCALAPPDATA%\DailyFocus\sources.json`，以后读取用户目录中的配置。修改该文件后手动刷新即可。项目沿用 `DailyFocus` 数据目录，以兼容早期版本。

报道配图优先从来源的 RSS、文章元数据或正文取得。图片不可用时显示明确标注的**主题示意图**，不把无关照片当作现场图。新闻与图片的权利属于各自发布方，项目不提供转载授权。

## 分析是什么

详情中的分析是依据标题、摘要和主题组织的**本地阅读框架**，不是在线模型逐条生成的深度分析，也没有完成全文和多方核实。心理研究的提示用于阅读证据，不用于个人诊断或治疗建议。

程序不会读取 ChatGPT 定时任务。自动更新需要程序保持运行、电脑已开机并可联网；休眠恢复后会检查更新时间。

## 本地数据

数据保存在 `%LOCALAPPDATA%\DailyFocus`：

| 文件或目录 | 用途 |
| --- | --- |
| `daily_focus.sqlite3` | 新闻与每日选择缓存 |
| `sources.json` | 用户订阅配置 |
| `appearance.json` | 按钮位置、窗口尺寸、透明度 |
| `images/` | 新闻配图缓存 |
| `daily_focus.log` / `startup_error.log` | 运行日志 / 启动错误 |

程序会连接配置的新闻站点和图片服务器，不上传本地数据库；网站会像普通访问一样接收到网络请求。日志和本地数据不应提交到仓库。

## 构建 Windows EXE

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_exe.ps1
```

输出为 `dist\DailyGlimpse\DailyGlimpse.exe`。分发时应复制整个 `dist\DailyGlimpse` 目录，不能只复制单个 EXE。本仓库仅交付构建流程；是否已有可下载二进制文件，以仓库实际发布记录为准。

也可以在 GitHub 的 **Actions → Build Windows app → Run workflow** 手动构建，完成后下载 `DailyGlimpse-windows` 构建产物。

## 测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

测试不抓取实时新闻，覆盖主题筛选、图片地址处理、缓存读写、阅读页去重、缩放和桌面按钮交互。联网来源可能改版或暂时不可用，离线测试不保证所有外部站点持续可达。

## 项目文件

```text
app.py               桌面按钮、窗口、订阅读取与缓存
topics.py            三类新闻筛选和配额
news_media.py        来源图片解析与缓存
news_views.py        图文阅读和响应式排版
reading_guide.py     简体转换和阅读框架
sources.json         默认订阅配置
tests/               离线回归测试
docs/                发布准备与素材说明
```

## 许可状态

源码许可证尚未指定，公开仓库并不自动授予再分发或修改许可。发布者可在确认后添加适当许可证。第三方库、新闻、图片和字体分别遵循其各自条款，见 [第三方说明](docs/THIRD_PARTY.md)。
