# 怎么把这个包编译出来并装到机器上

> ⚠️ **还没开始做的话，先看 [START-HERE.md](START-HERE.md)。** 那是唯一的主线清单（从建仓库到测出数据，10 步）。
> 本文是它的**细节补充**：构建原理、参数含义、失败排错。两份冲突时以 START-HERE 为准。

整条链路只用 GitHub 的免费 Linux 服务器编译，**你的 Windows 电脑不用装 Linux、不用装 NDK**。首次约 30–45 分钟（含下载 1.5 GB 的 NDK）。

> **本目录已经预初始化好了**：`.git` 已建、`main` 分支已建、文件已 `git add` 暂存，并且加了 `.gitattributes` 强制 LF 入库（`turnip_builder.sh` 在工作区是 CRLF，不改会让 Linux runner 报 `$'\r': command not found`）。你只需 commit + push。

---

## 第 1 步：建远程仓库并 push

1. 打开 https://github.com/new → Repository name 填 `turnip-duo-tz` → 选 **Public** → **不要**勾 README / .gitignore / license（勾了会让 push 冲突）→ Create repository。
2. 在本机终端（Git Bash / PowerShell 都行）逐行执行，把 `<你的用户名>` 和邮箱换成自己的：

```bash
cd "C:/Users/zhang/WorkBuddy/2026-11-23-06-46-20/turnip-duo-tz"
git config --local user.name  "<你的GitHub用户名>"
git config --local user.email "<你的GitHub邮箱>"
git commit -m "Turnip Duo TZ: Turnip-Z patches pinned, 4 A/B variants"
git remote add origin https://github.com/<你的用户名>/turnip-duo-tz.git
git push -u origin main
```

首次 push 会弹出浏览器让你登录 GitHub（本机已配 Git Credential Manager），授权一次即可。

### 备选：网页拖拽上传

不用命令行的话，可以 **Add file → Upload files**，把文件夹**里面的内容**（含 `.github/`）全拖进去。注意 `.github` 是隐藏目录，资源管理器要先开「查看 → 隐藏的项目」，**漏了它就没有 workflow**。

## 第 2 步：跑编译

1. 仓库页面 → **Actions** 标签。首次可能提示启用，点 **I understand my workflows, go ahead and enable them**。
2. 左侧选 **Build Turnip Duo TZ** → 右侧 **Run workflow**。
3. 参数保持默认即可：
   - `version` = `6.0`（只影响 zip 名和 meta.json）
   - `variants` = `tzqual tzfast tzsys tzccu2 tzvauzi`（要几个留几个；写 `all` 会连 `base` 一起编）
   - `mesa_ref` = `74920caaa0bed55313e7af00036c61515621913b`（v5.1 用的同一个提交，别动）
   - `cpu_flags` = `-march=armv8.2-a`（想对比就留空，会得到不优化 CPU 侧的版本）
4. 等绿勾。**先看这次运行的 Summary 页**：每个补丁应该是 `applied`，出现 `no-change` 说明锚点漂了、那个补丁等于没打（`34/35` 本来就会 no-change，我没放进去）。

## 第 3 步：下载产物

运行详情页底部 **Artifacts → turnip-duo-tz-6.0.zip**，解压后得到：

```
Turnip-Duo-TZ-v6.0.zip            # 基线（v5.1 补丁树，仅钉死默认值）
Turnip-Duo-TZ-v6.0-tzeden.zip     # Eden 主力（texfast + BGRA swap + LRZ，LOD +0.30，不锁 TU_DEBUG）
Turnip-Duo-TZ-v6.0-tzqual.zip     # 画质优先
Turnip-Duo-TZ-v6.0-tzfast.zip     # 帧数优先（LOD +0.45，强制 texfast）
Turnip-Duo-TZ-v6.0-tzsys.zip      # 强制 sysmem 兜底
Turnip-Duo-TZ-v6.0-tzccu2.zip     # CCU 2/32 对照
Turnip-Duo-TZ-v6.0-tzvauzi.zip    # 整套采用外部逆向的 A722 条目对照
```

`tzvauzi` 与 `tzqual` **只差 A722 设备条目这一项**（CCU 数、tile 对齐、highest_bank_bit、魔数寄存器表），用来裁决「本仓库 56 号那套保守参数」和「Vauzi-17/710 那套声称实机验证过的参数」哪个更对。若它花屏或出横向条带，第一嫌疑是 `highest_bank_bit`（15 vs 16）与 `tile_align_h`。

把这些 zip 拷到 Duo 上（U 盘 / 局域网 / adb push 都行，**不要解压**，Eden 认的是 zip 本身）。

## 第 4 步：装进模拟器

Eden / Citron / Azahar / Cemu 各自独立管理驱动，要装哪个就进哪个：

1. 设置 → **GPU Driver Manager**（图形驱动管理器）→ **Install** → 选 zip。
2. 装完在列表里能看到 `Turnip Duo TZ` 字样，选中它即可。
3. 想换版本就在列表里切，想删就删——**不需要 root，不动系统驱动**，删掉自动回到高通原厂驱动。

> 建议先只装 `tzqual` 和 `tzfast` 两个，跑完记录数据再装另外两个，避免自己记混。

## 第 5 步：确认驱动真的加载了这套默认值

```bash
adb logcat -c
# 启动游戏跑一会儿
adb logcat | grep -i "default env"
```

应该看到（`tzfast` 为例）：

```
default env: TU_Z_TEXFAST=1
default env: TU_Z_LODBIAS=45
default env: TU_Z_BGRA_SWAP=1
default env: TU_Z_LRZ_RESCUE=1
```

日志在就说明构造器跑过了、默认值生效。看不到的话，说明包没被选中或者装进了另一个模拟器。

## 第 6 步：回退

驱动管理器里切回 `Turnip Duo v5.1` 或 `System driver` 即可，秒回。四个包互相切换也不会残留配置。

---

## 如果 CI 编译失败

- **`meson: command not found`** → 工作流里的 pip 安装那步没跑成，重新 Run 一次。
- **某个补丁 `does not apply`** → 说明 Mesa 提交和你改的 `mesa_ref` 对不上。把 `mesa_ref` 改回默认值再跑。
- **`ERROR FD722 block not found`** → `tzccu2` 变体专用报错，原因是 56 号补丁没先跑成。其他变体不受影响，可以先只编 `tzqual tzfast tzsys`。
- 想只验证补丁能不能打、不编译：在 Actions 里把 `variants` 设成一个不存在的名字会失败；正确做法是本地 Linux 上跑
  `BUILD_VERSION=test PATCH_ONLY=1 bash turnip_builder.sh`，克隆完 Mesa、打完补丁就停，不下载 NDK。

## 第 7 步：把什么发回给我

按这个顺序发，我才能判断是「补丁没生效」还是「生效了但没用」：

1. **Actions 运行 Summary 页的截图**（含 4 个 `<details>` 里的 `patches-tz*.txt`）——我要逐个确认是 `applied` 不是 `no-change`。
2. **`adb logcat | grep "default env"` 的输出**——确认默认值真的进了构造函数。
3. **按 `TEST-PLAN.md` 填好的那张表**（FPS + 三项主观分）。
4. **异常截图**：花屏、条带、色偏、UI 糊，静态场景拍一张就够。

---

## 自己的 Linux 机器/云主机上编译

```bash
sudo apt-get install -y build-essential flex bison glslang-tools ninja-build zip unzip pkg-config python3-pip
sudo pip3 install meson mako pyyaml
BUILD_VERSION=6.0 BUILD_VARIANTS="tzqual tzfast tzsys tzccu2" \
ANDROID_CPU_FLAGS="-march=armv8.2-a" bash ./turnip_builder.sh
# 产物在 out/*.zip
```
