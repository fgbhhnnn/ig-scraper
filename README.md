# 社媒同行采集器（Instagram + Facebook + TikTok）

在 **Instagram / Facebook / TikTok** 上按**关键词 / 话题标签**搜索同行的**视频或帖子**，只保留**评论区里有人提问/询盘**的内容（评论只用来判断视频质量，每条视频最多看前 1~2 页评论，找到提问就停）。

双击 `Social-Scraper.exe`（v1.0 叫 IG-Scraper.exe） → 自动在浏览器打开本地网页 **http://127.0.0.1:8765**（固定端口，可收藏），不需要安装 Python。

> 全程只读：只发 GET 请求，不会点赞、关注、评论、私信。

## 使用步骤

1. **① Cookie**：Instagram 和 Facebook 分开填写、分开保存。粘贴后点「保存并校验」，显示登录用户 ID 即成功（IG 需含 sessionid，FB 需含 c_user、xs）。抓取中 Facebook 下发的新 Cookie 会自动保存。
2. **② AI 设置（可选）**：填 OpenAI 兼容接口的 Base 地址（如 `https://api.openai.com/v1`，或其它中转/国产模型的 `/v1` 地址）和 API Key → 「获取模型列表」→ 选模型 → 保存。也可手动输入模型名。
3. **③ 任务**：
   - 选择**平台**（Instagram / Facebook）和**内容类型**（视频 / 帖子 / 视频+帖子）
   - 填种子关键词、话题标签、评论区关键信息（如 价格 / MOQ / 怎么买）
   - 「✨ AI 裂变」：AI 扩展出更多搜索词、标签和多语言询盘短语（how much / precio / 多少钱 …），结果可直接编辑
   - 没配 AI 也能用：内置询盘规则（how much、price、moq、wholesale、catalog、whatsapp、where、ship … 以及带问号的评论）始终生效，并自动过滤推广/广告评论
   - 来源：关键词搜索（推荐）/ 话题标签 / 两者
   - 目标条数、翻页数、每条视频看几页评论、是否跳过本地已有、最少评论数/播放量、发布日期范围、文案必须包含/排除词
4. **④ 进度**：实时显示阶段、已匹配数、当前视频链接和日志，可随时「停止」。遇到 429 自动退避；遇到登录失效或安全验证(checkpoint)立即停止。
5. **⑤ 结果**：两个平台统一表格，可按平台、类型筛选；显示平台、类型、账号、链接、文案、播放、点赞、评论数、提问数、提问示例、发布日期、来源；可点表头排序、搜索、导出 CSV / Excel。

数据保存在 exe 同目录的 `igs_data/`：`config.json`（Cookie、AI Key，**不要发给别人**）和 `results.db`（SQLite，按「平台 + 内容 ID」去重；v1.0 的旧数据库首次启动时自动迁移，「跳过已有」跨任务生效）。用完点右上角「退出程序」关闭后台。

## 端口

- 固定使用 `8765`（页面右上角显示地址）。可在「AI 设置」页或 `igs_data/config.json` 的 `"port"` 修改，重启生效
- 再次双击 exe 时，如果程序已在运行，会直接打开已有页面，不会重复启动
- 如果端口被其他程序占用，会弹窗提示并退出（不会随机换端口），按提示关闭占用程序或修改端口即可

## 用 Cookie-Editor 获取 CK

1. Chrome / Edge 安装扩展 **Cookie-Editor**
2. 打开 https://www.instagram.com（或 https://www.facebook.com）并登录
3. 点扩展图标 → 右下 **Export** → **Export as JSON**（已复制到剪贴板）
4. 粘贴到软件 Cookie 页面对应平台的输入框

也可以 F12 → Network → 任意 instagram.com 请求 → 复制请求头里的 `cookie:` 整行。

建议用小号，节奏保持默认 1.5~3 秒/请求，单次任务不要太大。

## 从源码运行

```bash
pip install -r requirements.txt
python run.py          # 环境变量 IGS_PORT 临时覆盖端口, IGS_NO_BROWSER=1 不自动打开, IGS_DATA_DIR 指定数据目录
```

## 打包

```bash
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm ig-scraper.spec     # 输出 dist/Social-Scraper.exe（在 Windows 上打）
```

GitHub Actions（`.github/workflows/build.yml`）会在 `windows-latest` 上自动打包：推送到 main 后在 Actions 页面下载 artifact；推送 `v*` 标签（如 `git tag v1.0.0 && git push --tags`）会自动发布 Release 并附上 Social-Scraper.exe。

## TikTok 说明

1. **Cookie**：必须包含 HttpOnly 的 `sessionid`，请用 Cookie-Editor 在 tiktok.com 导出 JSON（`document.cookie` 拿不到）
2. **msToken**：推荐填浏览器 F12 → Application → Session Storage → `msToken`；留空则用 Cookie 里的 msToken（会随响应自动更新）
3. **device_id**：F12 → Application → Local Storage → `__tea_cache_tokens_1988` 的 `web_id`（可直接粘贴整段 JSON，自动提取）。必须与导出 Cookie 的浏览器一致，否则容易触发风控
4. **User-Agent**：填导出 Cookie 那个浏览器的 UA（控制台 `navigator.userAgent`），留空用默认 Chrome UA
5. **签名模块**：TikTok 接口需要 X-Gnarly / X-Dynosaur 签名。算法来自 [cv-cat/TiktokApis](https://github.com/cv-cat/TiktokApis)（纯 Python 实现，感谢原作者）。该项目**没有声明开源许可证**，因此本仓库不包含它的代码；在 Cookie 页点击「下载签名模块」，软件会从 GitHub 下载其固定版本（commit `b3b2a44`）的 `signing/pure.py` 到 `igs_data/tiktok_sign/`，并校验 SHA-256。也可以手动选择本地文件。该文件只依赖 Python 标准库，在 exe 内运行，**不需要安装 Node 或 Python**
6. 请求使用 [curl_cffi](https://github.com/lexiforest/curl_cffi)（MIT）模拟 Chrome 的 TLS 指纹，普通 requests 会被返回空响应
7. 关键词搜索 `/api/search/general/full/`，只保留评论数 > 0 的视频；评论用 `/api/comment/list/` 游标翻页（20 条/页，「TikTok 评论最多翻页数」默认 2），找到提问就停止；作者本人评论不计入。话题标签按「#标签」搜索
8. 字段：账号、链接、文案、播放、点赞、评论数、分享、发布日期、来源
9. 节奏默认 1.5~3 秒；遇到 status_code 2484 等风控码会等待重试，连续失败则停止并给出中文提示；返回空响应通常表示 Cookie / device_id / msToken 不匹配

## Facebook 说明

- 视频：搜索 `/search/videos/?q=`；帖子：搜索 `/search/posts/?q=`（帖子页里也会混有视频，按附件类型区分）。话题标签按「#标签」作为关键词搜索
- 搜索翻页和评论用 Facebook 网页版 GraphQL（只读查询），doc_id 运行时从 JS 包里自动识别，识别不到时用内置默认值，并缓存到 config.json
- 评论：普通帖子先读帖子页里自带的前约 10 条，Reels 直接用评论查询；之后按「Facebook 评论最多翻页数」继续翻页（约 10 条/页，默认 2 页，最多 50 页），一旦找到提问就停止翻页。帖主本人的回复不计入
- 评论翻页需要的 Relay provider 变量会尝试从 JS 包中自动识别，识别不到用内置列表
- 播放量：搜索结果里没有。勾选「从帖子页读取播放量」后，普通视频帖能拿到播放量；Reels 页面不提供，显示为「-」
- 节奏默认与 Instagram 相同，1.5~3 秒/请求（设置里可调，最小 0.5 秒；v1.1.0 的 4~7 秒默认值会自动升级）；遇到 429 自动等待重试；只有 USER_ID=0 或出现登录表单时才判定为掉线并停止
- 建议用小号，每次任务目标 10~30 条

## 限制

- 使用 Instagram / Facebook 网页版内部接口，非官方 API，接口变动可能失效
- 「OEM」等词会被 Instagram 防假货提示拦截，搜不出视频；部分词只返回账号不返回视频
- 提问数为前 1~2 页评论里的数量，仅作相对参考
- 关键词匹配规则较宽松，带问号即算提问（可在任务页关闭）
- Instagram 搜索结果以 Reels 为主，图片/文字帖子较少，抓帖子建议搭配话题标签
- TikTok 依赖第三方签名算法，TikTok 更新 WebMssdk 后可能失效，需要等原项目更新后替换签名文件
