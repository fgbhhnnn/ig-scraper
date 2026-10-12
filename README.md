# IG 同行视频采集器

在 Instagram 上按**关键词 / 话题标签**搜索同行视频，只保留**评论区里有人提问/询盘**的视频（评论只用来判断视频质量，每条视频最多看前 1~2 页评论，找到提问就停）。

双击 `IG-Scraper.exe` → 自动在浏览器打开本地网页（`http://127.0.0.1:端口/`），不需要安装 Python。

> 全程只读：只发 GET 请求，不会点赞、关注、评论、私信。

## 使用步骤

1. **① Cookie**：粘贴 Cookie，点「保存并校验」，显示登录用户 ID 即成功。
2. **② AI 设置（可选）**：填 OpenAI 兼容接口的 Base 地址（如 `https://api.openai.com/v1`，或其它中转/国产模型的 `/v1` 地址）和 API Key → 「获取模型列表」→ 选模型 → 保存。也可手动输入模型名。
3. **③ 任务**：
   - 填种子关键词、话题标签、评论区关键信息（如 价格 / MOQ / 怎么买）
   - 「✨ AI 裂变」：AI 扩展出更多搜索词、标签和多语言询盘短语（how much / precio / 多少钱 …），结果可直接编辑
   - 没配 AI 也能用：内置询盘规则（how much、price、moq、wholesale、catalog、whatsapp、where、ship … 以及带问号的评论）始终生效，并自动过滤推广/广告评论
   - 来源：关键词搜索（推荐）/ 话题标签 / 两者
   - 目标条数、翻页数、每条视频看几页评论、是否跳过本地已有、最少评论数/播放量、发布日期范围、文案必须包含/排除词
4. **④ 进度**：实时显示阶段、已匹配数、当前视频链接和日志，可随时「停止」。遇到 429 自动退避；遇到登录失效或安全验证(checkpoint)立即停止。
5. **⑤ 结果**：表格显示账号、链接、文案、播放、点赞、评论数、提问数、提问示例、发布日期、来源；可点表头排序、搜索、导出 CSV / Excel。

数据保存在 exe 同目录的 `igs_data/`：`config.json`（Cookie、AI Key，**不要发给别人**）和 `results.db`（SQLite，按 shortcode 去重，「跳过已有」跨任务生效）。用完点右上角「退出程序」关闭后台。

## 用 Cookie-Editor 获取 CK

1. Chrome / Edge 安装扩展 **Cookie-Editor**
2. 打开 https://www.instagram.com 并登录
3. 点扩展图标 → 右下 **Export** → **Export as JSON**（已复制到剪贴板）
4. 粘贴到软件的 Cookie 页面

也可以 F12 → Network → 任意 instagram.com 请求 → 复制请求头里的 `cookie:` 整行。

建议用小号，节奏保持默认 1.5~3 秒/请求，单次任务不要太大。

## 从源码运行

```bash
pip install -r requirements.txt
python run.py          # 环境变量 IGS_PORT=8765 指定端口, IGS_NO_BROWSER=1 不自动打开, IGS_DATA_DIR 指定数据目录
```

## 打包

```bash
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm ig-scraper.spec     # 输出 dist/IG-Scraper.exe（在 Windows 上打）
```

GitHub Actions（`.github/workflows/build.yml`）会在 `windows-latest` 上自动打包：推送到 main 后在 Actions 页面下载 artifact；推送 `v*` 标签（如 `git tag v1.0.0 && git push --tags`）会自动发布 Release 并附上 exe。

## 限制

- 使用 Instagram 网页版内部接口，非官方 API，接口变动可能失效
- 「OEM」等词会被 Instagram 防假货提示拦截，搜不出视频；部分词只返回账号不返回视频
- 提问数为前 1~2 页评论里的数量，仅作相对参考
- 关键词匹配规则较宽松，带问号即算提问（可在任务页关闭）
