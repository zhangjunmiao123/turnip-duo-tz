# 从零开始：给 RP Duo 出驱动、装进 Eden、测出数据

这份清单是**唯一需要照着做的东西**。前面的 `FORK-HOWTO.md`（构建细节）、`TEST-PLAN.md`（测试表）、`EDEN-GUIDE.md`（原理与设置说明）都是参考，看不懂某一步时再去翻。

全程分 10 步，第 1–6 步大约 1 小时（其中 30–60 分钟是机器在云端编译，你不用管），第 7–8 步是你实际玩游戏的 40 分钟。

---

## 第 0 步：先确认四件事（5 分钟）

| 检查项 | 怎么查 | 不满足怎么办 |
|---|---|---|
| 有 GitHub 账号 | 能登录 github.com | 注册一个，免费 |
| 本机有 git | 终端执行 `git --version` | 之前的会话已确认你有 git 2.55，应该有 |
| **Duo 上的 Eden 版本够新** | Eden → 设置 → 关于（或主页底部版本号） | 只要不是 2025 年的老版本就行。判断标准见第 8 步：设置里能不能找到 Turnip 环境变量入口 |
| 有一款想测的游戏 + 存档 | 建议先测 **Metroid Dread** 或 **Hades** | 因为社区已有这两款的公开数据（35–40fps），有对照才看得出我们的驱动是涨还是跌 |

**为什么强调 Eden 版本**：Eden 在 2026-01-09 合并了 PR #3205，才支持在图形设置里配 Turnip 环境变量。版本够新，你才能在第 8 步用 30 秒切一次显存模式；不够新，就只能用 `tzsys` 那个把 `sysmem` 写死的包，实验成本高很多。

---

## 第 1 步：把仓库推到 GitHub（10 分钟）

仓库已经在 `C:\Users\zhang\WorkBuddy\2026-11-23-06-46-20\turnip-duo-tz` **就地初始化并提交好了**：

- `main` 分支已建，114 个文件已提交（提交号 `c28b916`）
- 换行符已统一成 LF，`.gitattributes` 已加
- 作者信息已设为 `zhangjunmiao123 <zhangjunmiao123@users.noreply.github.com>`

**你不需要 `git init` / `git add` / `git commit`。** 只剩「建远程仓库 + push」两件事。

### 1.0 先解决 `git` 命令找不到（已替你修好一半）

WorkBuddy 自带了一个 PortableGit（2.55），但它原来不在系统 PATH 里，所以 PowerShell 报 `无法将"git"项识别为...`。已经把这个目录写进你的**用户 PATH**：

```
C:\Users\zhang\.workbuddy\binaries\PortableGit\versions\1.3.0\cmd
C:\Users\zhang\.workbuddy\binaries\PortableGit\versions\1.3.0\mingw64\bin
```

**但已经打开的 PowerShell 窗口不会自动生效。** 二选一：

- **办法 A（推荐）**：关掉当前 PowerShell，重新开一个，执行 `git --version`，应该显示 `git version 2.55.0.windows.3`。
- **办法 B（不想重开）**：在当前窗口先执行一次，本次会话就能用：
  ```powershell
  $env:Path += ";C:\Users\zhang\.workbuddy\binaries\PortableGit\versions\1.3.0\cmd;C:\Users\zhang\.workbuddy\binaries\PortableGit\versions\1.3.0\mingw64\bin"
  ```

> 如果 `git --version` 还是报错，就用完整路径直接调：
> `& "C:\Users\zhang\.workbuddy\binaries\PortableGit\versions\1.3.0\cmd\git.exe" --version`

### 1.1 先在网页上建空仓库

1. 打开 https://github.com/new
2. Repository name 填 `turnip-duo-tz`
3. 选 **Public**（Public 才免费使用 Actions；Private 也会消耗额度）
4. **下面三个勾一个都别打**（README / .gitignore / license 都不要，打了 push 会冲突）
5. 点 **Create repository**

### 1.2 在终端执行（只管 push）

```powershell
cd "C:\Users\zhang\WorkBuddy\2026-11-23-06-46-20\turnip-duo-tz"
git remote add origin https://github.com/zhangjunmiao123/turnip-duo-tz.git
git push -u origin main
```

**如果 `zhangjunmiao123` 不是你的 GitHub 用户名**，把第一条 `git remote add` 里的名字改掉；已经加错了就改：
```powershell
git remote set-url origin https://github.com/真正的用户名/turnip-duo-tz.git
```

首次 push 会弹出浏览器窗口让你登录 GitHub，授权一次就行（凭据管理器已配置 `credential.helper = manager`，以后不用再登）。

### 1.3 确认推上去了

刷新仓库页面，应该能看到 `EDEN-GUIDE.md`、`ANALYSIS.md`、`turnip_builder.sh`，以及**一个叫 `.github` 的文件夹**（GitHub 网页会显示它）。

看不到 `.github` 就说明 workflow 没上去，第 2 步会没有可点的按钮。

---

## 第 2 步：跑第一次构建（先只出 1 个包）

**这里有个关键建议：第一次只编 `tzeden` 一个变体。**

理由：4 个变体是**各自从干净源码树完整编译一遍**（构建脚本每个变体都 `git reset --hard` + `clean -fdx`），首次还要额外下载 1.5GB 的 NDK。4 个一起跑容易撞 120 分钟超时；先单个跑通链路，确认补丁、打包、产物都对，再批量。单个首次约 **30–40 分钟**。

### 2.1 启动

1. 仓库页 → **Actions** 标签
2. 首次会提示 `Workflows aren't being run on this repository` 之类，点 **I understand my workflows, go ahead and enable them**
3. 左侧列表里有 **5 个** workflow，**只点 `Build Turnip Duo TZ`**（其余四个是上游遗留的，见文末"先别碰的东西"）
4. 右侧点 **Run workflow**，按下表填：

| 参数 | 填什么 | 说明 |
|---|---|---|
| `version` | `6.0` | 只影响 zip 名，别填中文 |
| `variants` | **`tzeden`** | ← 第一次只填这一个 |
| `mesa_ref` | **保持默认不动** | `74920caa...913b`，动了补丁锚点可能全部失效 |
| `cpu_flags` | `-march=armv8.2-a` | 保持默认。这是唯一零画质风险的改动，别清空 |

5. 点绿色 **Run workflow**

### 2.2 等的时候看什么

点进正在跑的那次运行，展开 `Build` 步骤的日志。**正常**的日志会长这样：

```
==== Building v6.0-tzeden ====
[56-fd722-blob.py] applied ...
[57-fd722-duo.py] applied ...
```

如果看到 `Downloading android-ndk-r29` 卡很久，是正常现象（1.5GB）。

---

## 第 3 步：确认补丁真的打上了（不能跳过）

**绿色对勾不等于补丁生效。** 补丁找不到锚点时会打印 `no-change` 然后继续，照样出包——那就是一个和白装没区别的驱动。

在运行详情页往下拉，找到 **Summary**，展开 `<details>`，逐行看：

- ✅ 要的是：`applied`
- ❌ 有问题的是：`no-change`、`WARNING`、`skipped`

**把 Summary 这一块整段截图发我**。如果出现 `no-change`，说明该补丁等于没打，需要我改锚点重来——这个必须在装到机器上之前发现。

---

## 第 4 步：下载并解开（注意是两层压缩）

1. 运行详情页最下方 **Artifacts** → 点 `turnip-duo-tz-6.0` 下载
2. 下载到的是一个 zip，**先解压这一次**，里面是：

```
Turnip-Duo-TZ-v6.0-tzeden.zip     ← 这个才是驱动包
patches-tzeden.txt                ← 补丁日志（和 Summary 里一样）
build-info.env                    ← Mesa 提交号、版本
build-tz.log                      ← 完整编译日志
```

3. **`Turnip-Duo-TZ-v6.0-tzeden.zip` 不要再解压**。Eden 认的就是这个 zip 本身。

---

## 第 5 步：传到 Duo 并安装

传输用 U 盘、局域网、或 `adb push` 都行，把那个 zip 放到 Duo 的下载目录。

在 Duo 上：

1. 打开 **Eden**
2. **设置 → 图形（Graphics）→ GPU 驱动（GPU driver）**
3. 点 **安装（Install）**，文件选择器里选 `Turnip-Duo-TZ-v6.0-tzeden.zip`
4. 列表里应该出现一项 **`Turnip Duo TZ v6.0-tzeden`**
5. 选中它（选中即生效，会提示重启模拟器/游戏）

**不需要 root，不动系统驱动。** 想回退就在同一个界面切回"系统驱动"，或删掉这一项。

---

## 第 6 步：确认驱动真的被加载了（3 种方式，至少验一种）

### 方式 A：看 Eden 里的驱动名（最快）

设置 → 图形 → GPU 驱动，当前选中的那一项应该显示 `Turnip Duo TZ v6.0-tzeden`。这是"选中了"，但不代表"加载成功"。

### 方式 B：看 logcat（最可靠）

在电脑上（需要 adb，Android platform-tools）：

```bash
adb logcat -c
# 然后在 Duo 上启动 Eden 并进入游戏，跑 1-2 分钟
adb logcat | grep -iE "default env|Adreno \(TM\) 722"
```

三种结果的含义：

| 看到什么 | 说明 |
|---|---|
| `default env: TU_Z_TEXFAST=1` 之类 | ✅ 我们的驱动被加载了，内置默认值生效 |
| 只有 `Adreno (TM) 722`，没有 `default env` | ❌ 加载的是系统驱动或别的构建，检查第 5 步是不是装到了别的模拟器 |
| 什么都没有 | 可能是 adb 没连上，先 `adb devices` 确认 |

### 方式 C：画面判断（不推荐单独用）

如果进游戏后出现**整屏红蓝互换**，说明 `TU_Z_BGRA_SWAP` 这条在你机器上不成立——这反而是"驱动确实加载了"的证据。处理：在 Eden 的 Turnip 环境变量里设 `TU_Z_BGRA_SWAP=0`，不用重装。

---

## 第 7 步：把 Eden 设置一次性定死（之后不再动）

**这一步比换驱动更容易影响结果**，而且必须先做——否则后面测驱动时变量全是混的。

按顺序改，改完**不要再动**：

| 顺序 | 设置项 | 改成 | 为什么 |
|---|---|---|---|
| 1 | 图形 → **分辨率（Resolution）** | **0.75x** | 这台机器内存带宽只有约 17 GB/s（LPDDR4X），填充率是最贵的开销。5.5 寸屏上 0.75x 几乎看不出 |
| 2 | 图形 → **各向异性过滤（Anisotropic Filtering）** | **关闭** | Eden 默认本来就关，确认一下别被打开 |
| 3 | 图形 → **ASTC 解码（ASTC Decoding）** | **GPU** | Switch 贴图以 ASTC 为主，Adreno 原生支持 |
| 4 | 图形 → **异步着色器 / 管线缓存** | **开启** | ⚠️ **换驱动后必须清一次管线缓存重建**，否则第一次进游戏长时间卡顿会被误判成"驱动慢" |
| 5 | 系统 → **显示刷新率** | **60Hz** | 120Hz 下 40fps 的游戏帧节奏反而更不均 |
| 6 | 玩的时候把**下屏关掉**（或让 Eden 独占前台） | — | 两块 120Hz 屏持续扫描输出 ≈ 1.58 GB/s，占 17 GB/s 的 9%。关下屏+降 60Hz 能省掉七成左右 |
| 7 | 系统 → **强制最大频率 / 性能模式** | 开启 | 有风扇能扛，但留意温度 |

**改完先玩 5 分钟确认稳定**，再进入第 8 步。

---

## 第 8 步：三档显存模式实验（核心，30 分钟）

这是现在信息量最大的一组实验，因为社区口径**互相矛盾**：Vauzi-17（710/720/722 驱动的作者）推荐 `sysmem` 作默认，而 MrPurple 在 Eden 的 PR 里说 A710/720 必须 `gmem` 才正常。A722 没人公开测过。

### 8.1 找到 Turnip 环境变量入口

Eden → 设置 → 图形 → GPU 驱动 附近，通常在选中自定义驱动后出现"驱动设置 / 配置 / Driver settings"。里面可以填 `NAME=VALUE`。

**如果找不到这个入口**（版本太老），跳过 8.2，直接用 `tzsys` 包代替——那个包把 `TU_DEBUG=sysmem` 写死在驱动里了。

### 8.2 只改一个值，跑三轮

| 轮次 | 设什么 | 怎么设 |
|---|---|---|
| A | **留空**（不设 `TU_DEBUG`） | 删掉这一行，或清空 |
| B | `TU_DEBUG=gmem` | 强制片上 GMEM 渲染，省带宽 |
| C | `TU_DEBUG=sysmem` | 强制系统内存渲染，兼容性最好 |

每轮之间：**退出游戏 → 改设置 → 重进游戏**（改完必须重启游戏进程才生效）。

### 8.3 每轮怎么测

同一款游戏、同一个存档点、同一条路线，**先跑 3 分钟让机身热稳定**（有风扇也要等），然后固定跑 2 分钟，记：

| 轮次 | 平均 fps | 1% low | 画面有没有异常 | 机身烫不烫 |
|---|---|---|---|---|
| 基线：系统驱动 | | | | |
| A：不设 TU_DEBUG | | | | |
| B：`gmem` | | | | |
| C：`sysmem` | | | | |

- 想看帧数用 Eden 自带的 FPS 显示（设置 → 界面 → 显示性能统计），或系统自带的游戏助手浮层。
- **1% low 比平均 fps 更重要**——平均 40 但 1% low 22 的手感，比平均 36 但 1% low 32 差得多。

---

## 第 9 步：剩下三个包，看情况再编

**先别急着编。** 等第 8 步出结论再说：

- 如果 A/B/C 里某一档明显赢，**先只玩这一档**，够用了。
- 如果三档都差不多、你想知道 texfast（我们的驱动相对原版到底改了多少），再跑一次 workflow，`variants` 填 `tzqual tzvauzi tzsys`。
  - `tzqual` = 关掉 texfast，量"纹理提速"的代价
  - `tzvauzi` = 换一套外部逆向的 A722 几何参数，**有花屏风险，最后一个测**
  - `tzsys` = 把 sysmem 写死的兜底版

编完后的产物名：`Turnip-Duo-TZ-v6.0-tzqual.zip` 等，装法同第 5 步，但**一次只装一个、测完删掉再装下一个**，否则你分不清是哪个在起作用。

---

## 第 10 步：回传这四样（我据此定位瓶颈）

1. **第 3 步的 Summary 截图**（补丁是 applied 还是 no-change）
2. **第 6 步 logcat 的输出**（有没有 `default env`）
3. **第 8 步那张表**（基线 + A/B/C 的 fps 和 1% low）
4. **异常截图**（花屏、横向条带、红蓝反、UI 糊）

有这四样，我能判断瓶颈在带宽、填充率还是驱动路径，而不是靠猜。

---

## 常见失败与处理

| 现象 | 原因 | 处理 |
|---|---|---|
| workflow 跑了 120 分钟超时 | 4 个变体一次编 + 首次下 NDK | `variants` 只填 `tzeden` 重跑，NDK 有缓存会快很多 |
| `Downloading NDK` 失败/超时 | 网络抖动 | 直接重跑，缓存会续上 |
| Summary 里 `no-change` | 补丁锚点对不上上游源码 | 把截图发我，我改锚点 |
| 装完进游戏黑屏 | 该变体参数不适合 | Eden 里切回系统驱动，报告是哪个包 |
| 整屏红蓝互换 | `TU_Z_BGRA_SWAP` 不成立 | Eden 环境变量设 `TU_Z_BGRA_SWAP=0` |
| 固定周期横向条带 | `tile_align_h` / `highest_bank_bit` 配错 | 只会在 `tzvauzi` 上出现，换回 `tzeden` |
| 第一次进游戏卡很久 | 管线缓存要重建 | 正常，第二次进就快；别误判成驱动慢 |

---

## 先别碰的东西

- **Actions 里另外 4 个 workflow**：`Build Turnip (Adreno 722)`、`Turnip Duo v7.0`、`Turnip Duo v3.1`、`Turnip A722 bisect builds`。它们都是上游遗留、手动触发，其中 `Build Turnip (Adreno 722)` 引用的两个 stable 补丁文件在本仓库已移到 `legacy-patches/`，跑了会直接报错。你只需要 `Build Turnip Duo TZ`。
- **别同时装多个驱动包**，Eden 只用一个，装了也分不清。
- **别在测驱动的同时改分辨率**——第 7 步定死它就是为了这个。
- **别把 `tzvauzi` 当第一个包测**，它有花屏风险，先建立基线。
