# 从零开始：给 RP Duo 出驱动、装进 Eden、测出数据

这份清单是**唯一需要照着做的东西**。前面的 `FORK-HOWTO.md`（构建细节）、`TEST-PLAN.md`（测试表）、`EDEN-GUIDE.md`（原理与设置说明）都是参考，看不懂某一步时再去翻。

全程分 10 步，第 1–6 步大约 1 小时（其中 30–60 分钟是机器在云端编译，你不用管），第 7–8 步是你实际玩游戏的 40 分钟。

---

## v6.2：实测推翻了 v6.1 的方向，现在逐项对齐 v5.1

你在荒野之息上实测：**v6.1 的 `tzeden` 和 `tzfast` 都比 v5.1 慢**，而且 v5.1 本身也有锯齿（锯齿不用管，帧率优先）。这说明 v6.1「放开 GMEM」的方向错了，也说明 v6.0 的慢不只来自帧数，还有别的新增负重。逐项对照 v5.1 的补丁集后，找到了 v6.0/v6.1 共同引入、而 v5.1 没有的东西：

| # | v6.0/v6.1 新增 | 为什么可能是减速源 | v6.2 怎么处理 |
|---|---|---|---|
| 1 | 56 号把 `enable_tp_ubwc_flag_hint` 设成 `False` | 纹理处理器不吃 UBWC flag 提示 → 压缩纹理取数退化 → **带宽变大**。这台机器只有 ~17 GB/s，贴图密集的游戏最先爆 | 恢复上游默认（True），同时 `has_lpac` 也恢复 |
| 2 | 56 号把 `raw_magic_regs` 换成自造的 `a722_*`（v5.1 用 `a730_*`） | 这类寄存器写错不花屏，只表现为帧率差异 | 恢复 `a730_raw_magic_regs` |
| 3 | 33/37 号全局 BGRA 实色交换、31 号 LRZ rescue | v5.1 都没有；BGRA 会改动 shader 输出/写掩码/clear/blit 全部写路径 | `tz5` 不带；`tz5s` 带着做对照 |
| 4 | v6.1 放开 GMEM（autotune BANDWIDTH + 2/32/16） | 实测更慢 —— 1 MiB GMEM 装不下 1080p pass，多 bin 来回搬不划算 | 35b 号按 v5.1 的做法把 A722 钉回 sysmem；几何回设备真值 1/16/15 |

v6.2 出两个包：

- **`tz5`（主力）**：v5.1 等效 + texfast 省带宽档（`TU_Z_TEXMIP=1` + `TU_Z_LODBIAS=45`，你已确认不在乎锯齿）。预期帧率 ≥ v5.1。
- **`tz5s`（对照）**：与 tz5 唯一差别是保留 BGRA swap 和 LRZ rescue。tz5s 比 tz5 慢 → 这两项就是 v6.0 减速的来源；持平或更快 → 留着。

`tz5` 上还有一个运行时逃生开关 `TU_Z_FORCE_GMEM=1`：想在**不重编**的情况下走回 GMEM/autotune 路径对比，设它就行。

---

## v6.1 的结论（已被 v6.2 推翻，留作记录）

v6.0 的 `tzeden` 在塞尔达旷野之息上「帧数更低 + 边缘锯齿严重」。查完源码，两个症状的性质**不一样**，先说清楚：

### 锯齿：确认是 v6.0 引入的，已经修掉

32 号补丁除了加 LOD 偏置，还把 `miplinear` 设成 `false`（三线性 → 最近 mip）并把 `aniso` 归零。**v5.1 那条补丁只加 LOD 偏置，从不动这两项。** mip 之间直接跳变，远景草地/地面在运动时抖动发毛，观感就是"锯齿严重"——荒野之息满屏草地，最吃这个。

v6.1 把它拆成两个变量：`TU_Z_TEXMIP`（默认 0 = 不动）和 `TU_Z_LODBIAS`（默认 0 = 不加偏置）。默认状态下采样器与上游**逐 bit 相同**。

### 帧数：不是 v6.0 新引入的，是 v5.1 一直就有的设计，v6.1 换方向

v5.1 其实**也是强制 sysmem**的——`TU_Z_SYSMEM_ONLY` 默认 true（`use_sysmem_rendering()` 里直接 return true），外加 tu_autotune 的默认算法写成 `PREFER_SYSMEM`。v6.0 的 36 号只是把这个做法原封不动搬进了 autotune（`PREFER_SYSMEM` 在 `get_optimal_mode()` 里是 `early_return_mode` 提前返回，等于所有 render pass 一律走系统内存）。

问题在于：**这条路在带宽只有 ~17 GB/s 的 Duo 上方向是错的**。把整帧颜色/深度全压到 DDR，双屏 120Hz 还要再扣 1.58 GB/s，荒野之息这种高 overdraw 场景最吃亏。（TurnipZ 在 865 上走这条路能赢，是因为 865 的 GMEM 和带宽是另一个量级。）

v6.1 的做法不是"回退"，而是**第一次真正把 GMEM 路径打开**：

1. 36 号停用 → 显存模式交回上游 `BANDWIDTH`（逐 render pass 按估算带宽选 GMEM / sysmem）；
2. 但 1/16/15 的几何只在强制 sysmem 下验证过，autotune 一走 GMEM 就会 `UBWC corruption (purple/black lines) and a GPU hang`（57 号注释原文）。所以 57 号改成 **2/32/16** —— 这是 MrPurple666 的 T30 在 **A722 实机 + 自动调优开启**下验证过的组合（T30 的 meta.json 明写 `uses tu_autotune GMEM/sysmem selection`）；
3. 17 号脚本原来在 `BUILD_VARIANT` 不认识时会**静默回退成 `p2`**，于是每个变体都被无提示地关掉 KGSL governor、强制 turbo，还顺手把 autotune 带宽乘数 11→10（那一改把 EMA 变成了累加，GMEM 永远显得更贵）。v6.1 起只有显式请求 `p/p1/p2` 才生效，governor 单独做成运行时变量 `TU_KGSL_GOVERNOR_OFF`（默认 1 = v5.1 行为）。

> 如果 2/32/16 在你的机器上出紫黑横条（说明这套几何不成立），**先别改补丁**：在 Eden 环境变量里加 `TU_DEBUG=sysmem` 就能绕开 GMEM，继续用这个包，然后把现象告诉我。
>
> 另外，**如果第 7 步把分辨率设成了 0.75x，那也是锯齿的第二个来源**。荒野之息手持原生 720p，降到 540p 再拉到 1080p，几何边缘必然更糟。v6.1 的基线一律用 **1x**。

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

**这里有个关键建议：第一次只编 `tz5` 一个变体。**

理由：4 个变体是**各自从干净源码树完整编译一遍**（构建脚本每个变体都 `git reset --hard` + `clean -fdx`），首次还要额外下载 1.5GB 的 NDK。4 个一起跑容易撞 120 分钟超时；先单个跑通链路，确认补丁、打包、产物都对，再批量。单个首次约 **30–40 分钟**。

### 2.1 启动

1. 仓库页 → **Actions** 标签
2. 首次会提示 `Workflows aren't being run on this repository` 之类，点 **I understand my workflows, go ahead and enable them**
3. 左侧列表里有 **5 个** workflow，**只点 `Build Turnip Duo TZ`**（其余四个是上游遗留的，见文末"先别碰的东西"）
4. 右侧点 **Run workflow**，按下表填：

| 参数 | 填什么 | 说明 |
|---|---|---|
| `version` | `6.2` | 只影响 zip 名，别填中文 |
| `variants` | **`tz5`** | ← 第一次只填这一个 |
| `mesa_ref` | **保持默认不动** | `74920caa...913b`，动了补丁锚点可能全部失效 |
| `cpu_flags` | `-march=armv8.2-a` | 保持默认。这是唯一零画质风险的改动，别清空 |

5. 点绿色 **Run workflow**

### 2.2 等的时候看什么

点进正在跑的那次运行，展开 `Build` 步骤的日志。**正常**的日志会长这样：

```
==== Building v6.2-tz5 ====
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

1. 运行详情页最下方 **Artifacts** → 点 `turnip-duo-tz-6.1` 下载
2. 下载到的是一个 zip，**先解压这一次**，里面是：

```
Turnip-Duo-TZ-v6.2-tz5.zip     ← 这个才是驱动包
patches-tz5.txt                ← 补丁日志（和 Summary 里一样）
build-info.env                    ← Mesa 提交号、版本
build-tz.log                      ← 完整编译日志
```

3. **`Turnip-Duo-TZ-v6.2-tz5.zip` 不要再解压**。Eden 认的就是这个 zip 本身。

---

## 第 5 步：传到 Duo 并安装

传输用 U 盘、局域网、或 `adb push` 都行，把那个 zip 放到 Duo 的下载目录。

在 Duo 上：

1. 打开 **Eden**
2. **设置 → 图形（Graphics）→ GPU 驱动（GPU driver）**
3. 点 **安装（Install）**，文件选择器里选 `Turnip-Duo-TZ-v6.2-tz5.zip`
4. 列表里应该出现一项 **`Turnip Duo TZ v6.2-tz5`**
5. 选中它（选中即生效，会提示重启模拟器/游戏）

**不需要 root，不动系统驱动。** 想回退就在同一个界面切回"系统驱动"，或删掉这一项。

---

## 第 6 步：确认驱动真的被加载了（3 种方式，至少验一种）

### 方式 A：看 Eden 里的驱动名（最快）

设置 → 图形 → GPU 驱动，当前选中的那一项应该显示 `Turnip Duo TZ v6.2-tz5`。这是"选中了"，但不代表"加载成功"。

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
| `default env: TU_Z_TEXFAST=1`、`default env: TU_AUTOTUNE_ALGO=bandwidth` 之类 | ✅ 我们的驱动被加载了，内置默认值生效 |
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
| 1 | 图形 → **分辨率（Resolution）** | **1x**（基线必须 1x） | 荒野之息手持模式原生就是 720p，再降 0.75x 等于 540p 拉伸到 1080p，几何边缘会明显更糟。先把 1x 当基线，测完驱动再考虑降分辨率换帧数 |
| 2 | 图形 → **各向异性过滤（Anisotropic Filtering）** | **关闭** | Eden 默认本来就关，确认一下别被打开 |
| 3 | 图形 → **ASTC 解码（ASTC Decoding）** | **GPU** | Switch 贴图以 ASTC 为主，Adreno 原生支持 |
| 4 | 图形 → **异步着色器 / 管线缓存** | **开启** | ⚠️ **换驱动后必须清一次管线缓存重建**，否则第一次进游戏长时间卡顿会被误判成"驱动慢" |
| 5 | 系统 → **显示刷新率** | **60Hz** | 120Hz 下 40fps 的游戏帧节奏反而更不均 |
| 6 | 玩的时候把**下屏关掉**（或让 Eden 独占前台） | — | 两块 120Hz 屏持续扫描输出 ≈ 1.58 GB/s，占 17 GB/s 的 9%。关下屏+降 60Hz 能省掉七成左右 |
| 7 | 系统 → **强制最大频率 / 性能模式** | 开启 | 有风扇能扛，但留意温度 |

**改完先玩 5 分钟确认稳定**，再进入第 8 步。

---

## 第 8 步：显存模式实验（核心，30 分钟）

这是现在信息量最大的一组实验，但**有一条硬约束，先看这一条**：

> ⚠️ **v6.2 起 `tz5` 默认就是强制 sysmem**（v5.1 的行为，35b 号补丁按 chip_id 钉死），所以不需要也不建议手动设 `TU_DEBUG=gmem` 或 `TU_DEBUG=sysmem`——前者会把所有 pass 无条件塞进 1 MiB GMEM，后者是重复操作。想临时走回 GMEM/autotune 路径对比，设 `TU_Z_FORCE_GMEM=1`。

社区口径本身也**互相矛盾**：Vauzi-17（710/720/722 驱动的作者）推荐 `sysmem` 作默认，而 MrPurple 在 Eden 的 PR 里说 A710/720 必须 `gmem` 才正常。两者对应的却不是同一套几何参数——这大概就是矛盾的原因。A722 没人公开测过。

### 8.1 找到 Turnip 环境变量入口

Eden → 设置 → 图形 → GPU 驱动 附近，通常在选中自定义驱动后出现"驱动设置 / 配置 / Driver settings"。里面可以填 `NAME=VALUE`。

**如果找不到这个入口**（版本太老），跳过 8.2，直接用 `tzsys` 包代替——那个包把 `TU_DEBUG=sysmem` 写死在驱动里了。

### 8.2 在 `tz5` 上跑四档（不重编，30 秒一档）

v6.2 的 `tz5` 默认就是强制 sysmem（v5.1 行为），所以变量只用来**对照**：

| 轮次 | Eden 驱动设置里写 | 含义 |
|---|---|---|
| **基线** | 什么都不加 | 强制 sysmem（= v5.1）+ texfast 省带宽 |
| B | `TU_Z_LODBIAS=20` | 把 LOD 偏置收小（远景更清楚，带宽略多） |
| C | `TU_Z_FORCE_GMEM=1` | 运行时走回 GMEM/autotune 路径 —— 用来验证"GMEM 更慢"这个结论 |
| D | `TU_Z_TEXMIP=0` `TU_Z_LODBIAS=0` | 关掉 texfast = 纯 v5.1 等效，量出 texfast 到底赚了多少 |

判读：**基线 ≥ v5.1 → 成功**；C 慢于基线 → GMEM 结论成立，这条变量以后不用再设；D 明显慢于基线 → texfast 在起作用。

**画质不用看了**：你已确认锯齿不重要。如果远景糊得影响玩，降 `TU_Z_LODBIAS` 就行，不用换包。

### 8.2b tz5 vs tz5s：一次构建两个包的对照

先测 `tz5`，记下基线帧率；再装 `tz5s`，同样设置再测一次。两个包只有 BGRA swap + LRZ rescue 的差别：

- `tz5s` 更慢 → 这两项就是 v6.0/v6.1 减速的来源之一，以后的主线包永远不带；
- 持平或更快 → 可以把 `tz5s` 当日常包（它顺便解决了某些游戏的红蓝互换问题）。

### 8.3 万一 `tz5` 还是比 v5.1 慢

那就说明 v6.2 还没对齐完 v5.1，嫌疑收窄到 base 里 v5.1 也有的少数补丁。按这个顺序用**运行时变量**排除，不用重编：

1. `TU_KGSL_GOVERNOR_OFF=0` —— 排除 governor 强制的因素；
2. `TU_Z_TEXFAST=0` —— 排除 texfast；
3. 还慢 → 把现象和帧数告诉我，我再往下查（剩下的差异在 15/16/01/25/30 这几个 v5.1 就有的补丁里，需要逐个做开关）。

### 8.4 每轮怎么测

同一款游戏、同一个存档点、同一条路线，**先跑 3 分钟让机身热稳定**（有风扇也要等），然后固定跑 2 分钟，记：

| 轮次 | 平均 fps | 1% low | 画面有没有异常 | 机身烫不烫 |
|---|---|---|---|---|
| 基线：系统驱动 | | | | |
| A：不设 TU_DEBUG | | | | |
| C：`sysmem` | | | | |

- 想看帧数用 Eden 自带的 FPS 显示（设置 → 界面 → 显示性能统计），或系统自带的游戏助手浮层。
- **1% low 比平均 fps 更重要**——平均 40 但 1% low 22 的手感，比平均 36 但 1% low 32 差得多。

---

## 第 9 步：其它包，看情况再编

**先别急着编。** 等 8.2/8.2b 出结论再说：

- `tz5` ≥ v5.1 且 `tz5s` 与它持平 → 主线就定 `tz5`（或 `tz5s`，看哪个顺手），结束。
- 想要更极致的画质对照再跑一次 workflow，`variants` 填 `tzqual tzvauzi tzsys`：
  - `tzqual` = v6.2 base + 关 texfast 的画质对照包
  - `tzvauzi` = 外部逆向的完整 A722 寄存器表（走 GMEM 的几何 2/32/16，配合 `TU_Z_FORCE_GMEM=1` 才有意义）
  - `tzsys` = sysmem 兜底版

编完后的产物名：`Turnip-Duo-TZ-v6.2-tzqual.zip` 等，装法同第 5 步，但**一次只装一个、测完删掉再装下一个**，否则你分不清是哪个在起作用。

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
| workflow 跑了 120 分钟超时 | 4 个变体一次编 + 首次下 NDK | `variants` 只填 `tz5` 重跑，NDK 有缓存会快很多 |
| `Downloading NDK` 失败/超时 | 网络抖动 | 直接重跑，缓存会续上 |
| Summary 里 `no-change` | 补丁锚点对不上上游源码 | 把截图发我，我改锚点 |
| 装完进游戏黑屏 | 该变体参数不适合 | Eden 里切回系统驱动，报告是哪个包 |
| 整屏红蓝互换 | `TU_Z_BGRA_SWAP` 不成立 | Eden 环境变量设 `TU_Z_BGRA_SWAP=0` |
| 固定周期横向条带 | `tile_align_h` / `highest_bank_bit` 配错（GMEM 几何不成立） | Eden 环境变量加 `TU_DEBUG=sysmem` 先恢复；再告诉我，我改回 1/16/15 重编 |
| 第一次进游戏卡很久 | 管线缓存要重建 | 正常，第二次进就快；别误判成驱动慢 |
| **帧数比 v6.0 高但比系统驱动低** | 荒野之息本身在 Eden 上就是 CPU + 带宽双瓶颈 | 先看第 8 步的显存模式三档，再考虑降分辨率；别指望驱动把 720p 的 Switch 游戏拉到 60fps |
| **画面还是"锯齿严重"** | 先确认分辨率是 1x；再确认没开 `TU_Z_TEXMIP=1` | 两个都排除了，那就是 720p 拉 1080p 的固有结果，只能靠 Eden 提高分辨率（吃性能）换画质 |

---

## 先别碰的东西

- **Actions 里另外 4 个 workflow**：`Build Turnip (Adreno 722)`、`Turnip Duo v7.0`、`Turnip Duo v3.1`、`Turnip A722 bisect builds`。它们都是上游遗留、手动触发，其中 `Build Turnip (Adreno 722)` 引用的两个 stable 补丁文件在本仓库已移到 `legacy-patches/`，跑了会直接报错。你只需要 `Build Turnip Duo TZ`。
- **别同时装多个驱动包**，Eden 只用一个，装了也分不清。
- **别在测驱动的同时改分辨率**——第 7 步定死它就是为了这个。
- **先只跑 `tz5`**，把基线立起来；`tzvauzi` 是寄存器表的对照包，等基线稳了再碰。
