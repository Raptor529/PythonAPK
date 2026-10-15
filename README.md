# 条码拍照 PDF 生成器（安卓应用）

一个小巧的安卓应用：**拍 3 张图（其中一张是条码图）→ 自动读取条码当作文档名 → 合并成一个 PDF → 存到你指定的位置。**

---

## 一、功能与需求对照

| 需求 | 实现情况 |
|------|---------|
| 拍三张图片 | 三个图片卡片，逐张准备，进度实时显示「已准备 2 / 3 张图片」 |
| 支持本地上传 | 每张图都能二选一：**「拍照」** 或 **「从相册选择」**，可混用、可单张重取 |
| 其中一张是条码图片 | 第 1 张默认提示「建议拍条码」，但**三张都会自动尝试识别**，任意一张有码都能认出来 |
| 提取条码作为文档名称 | 支持 EAN13 / CODE128 / CODE39 / UPC / QR 码等；识别出的内容自动填入「文档名称」，**可以手动改** |
| 三张图保存在同一个 PDF | 生成标准 PDF，一页一张图，顺序就是准备顺序 |
| 文档保存路径可自定义 | 预设 4 个常用目录 + **可直接输入任意完整路径**；安卓 11+ 还可一键申请「所有文件访问」权限 |
| 界面简洁、易懂 | 全中文，四屏流程：首页 → 准备图片 → 确认信息 → 生成结果，按钮大、层级少 |
| 不闪退 | 全链路异常兜底（见下文「稳定性设计」） |
| 运行在安卓系统上 | Android 7.0（API 24）及以上，arm64-v8a / armeabi-v7a 双架构 |

---

## 二、文件说明

| 文件 | 作用 |
|------|------|
| `main.py` | **应用主程序**（全部逻辑与界面都在这里，中文注释按 10 个分节组织） |
| `buildozer.spec` | 打包成安卓 APK 的配置文件 |
| `selftest.py` | 可选：在电脑上跑一遍全流程自检，确认代码正常 |
| `requirements-desktop.txt` | 可选：在电脑上运行界面所需依赖 |
| `.github/workflows/build.yml` | 可选：GitHub Actions 云端自动打包配置（见「三、4. 云端打包」） |

---

## 三、打包成 APK

> ⚠️ buildozer 只能在 **Linux / macOS / WSL2** 里运行，Windows 的 CMD 直接敲 `buildozer android debug` 会报 `Unknown command/target android`，这是官方限制。

### 1. 准备环境（以 Ubuntu 为例）

```bash
sudo apt update
sudo apt install -y git zip unzip openjdk-17-jdk python3-pip python3-venv \
    autoconf libtool pkg-config zlib1g-dev libncurses-dev cmake libffi-dev libssl-dev ccache

pip3 install --user buildozer cython
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### 2. 开始打包

把整个项目文件夹拷到 Linux 下（**建议放在 Linux 家目录，不要放在 `/mnt/c/` 里编译**），然后：

```bash
cd 项目目录
# 若还没有图标，先注释掉 buildozer.spec 里的 android.icon 一行
buildozer -v android debug
```

首次编译需要自动下载 Android SDK / NDK（约 1.5 GB），耗时 **20～40 分钟**；之后再编译只要 5～10 分钟。

编译成功后，APK 在 `bin/` 目录里，文件名类似 `barcodepdf-1.0.0-debug.apk`，拷到手机安装即可（需允许「安装未知来源应用」）。

### 3. 装到手机上

- 数据线连电脑：`adb install bin/barcodepdf-1.0.0-debug.apk`
- 或直接把 APK 传到手机，用文件管理器点击安装

### 4. 云端打包（自己电脑什么都不用装，推荐）

本项目已经内置了 GitHub Actions 工作流（文件在 `.github/workflows/build.yml`），
由 GitHub 的服务器替你编译，全程只需点几下鼠标：

1. 注册并登录 GitHub：<https://github.com>
2. 新建仓库：<https://github.com/new>，仓库名随意（如 `BarcodePDFApp`），
   公开或私有都可以，点「Create repository」。
3. 上传本项目**全部文件**，注意两点：
   - 上传前先在文件管理器里打开「显示隐藏的项目」（Windows：查看 → 勾选；
     macOS：`Cmd+Shift+.`），因为 `.github` 是隐藏文件夹，不打开会漏传，导致找不到工作流；
   - 若 `.github` 拖不进去，改用网页的 **Add file → Create new file**，
     文件名填 `.github/workflows/build.yml`（输入 `/` 会自动建目录），
     再把本地同名文件的内容复制粘贴进去保存。
4. 进仓库顶部 **Actions** 标签 → 左侧选 **Build Android APK** →
   右侧点 **Run workflow** → 绿色按钮确认。
5. 等 **10～20 分钟**，出现绿色 ✅ 后点进这次运行记录，页面底部
   **Artifacts** 区域下载 `BarcodePDFApp-apk`（是个 zip），解压出的 `.apk` 装到手机即可。

> 如果国内访问 GitHub 不稳定，可把仓库改放到 Gitee（<https://gitee.com>）并使用其「流水线」
> 功能，把 `.github/workflows/build.yml` 里的构建步骤搬到 Gitee 流水线配置中即可，原理完全一样。

---

## 四、不用安卓手机，先在电脑上看界面

```bash
# 1. 安装依赖
pip3 install -r requirements-desktop.txt

# 2. 跑自检（会模拟完整流程：准备三张图 → 识别条码 → 生成 PDF）
python3 selftest.py

# 3. 直接运行应用（电脑上「拍照」会变成「选择本地图片」）
python3 main.py
```

---

## 五、代码结构（`main.py` 内的 10 个分节）

| 分节 | 内容 |
|------|------|
| 第 1 节 | 基础导入与全局常量 |
| 第 2 节 | 通用工具：文件名净化、图片方向校正、缩略图、弹窗 |
| 第 3 节 | **条码识别引擎**（pyzbar + 旋转/放大变体，提高识别率） |
| 第 4 节 | **PDF 生成引擎**（Pillow 多页 PDF） |
| 第 5 节 | 存储路径工具（自定义目录 + 逐级回退） |
| 第 6 节 | **平台桥接层**：`AndroidBridge`（相机 / 相册 / 权限）、`DesktopBridge`（电脑选图） |
| 第 7 节 | 界面定义（KV 语言，界面长什么样） |
| 第 8 节 | 界面逻辑类（四个页面 + 图片卡片） |
| 第 9 节 | 应用主类 |
| 第 10 节 | 程序入口 + 中文字体注册 |

---

## 六、稳定性设计（为什么不容易闪退）

1. **异常全兜底**：所有按钮回调、文件读写、识图、写 PDF 都包在异常捕获里，出错只弹提示，不崩。
2. **图片全部走缩略图**：4000×3000 的原图不会直接进显存，避免低端机内存溢出被杀。
3. **拍照保活**：实现了 `on_pause()` 返回 `True`。打开系统相机时应用会被切到后台，若不处理，系统会销毁应用，回来时拍好的图就没了。
4. **结果不覆盖**：同名文件自动变成 `名字(1).pdf`、`名字(2).pdf`，不会悄悄覆盖旧文档。
5. **保存多级回退**：用户指定目录 → 公共 Documents → 公共 Download → 应用私有目录，总有一个能写成功，并如实告诉用户最终存到哪了。
6. **识别失败可兜底**：认不出条码时不报错，引导用户手动填写文档名称，流程照样能走完。
7. **图片自动转正**：按 EXIF 方向校正，竖拍的照片不会在 PDF 里躺着。
8. **权限失败不致命**：缺相机 / 存储权限时功能受限但不崩溃，并会再次申请。

---

## 七、常见问题

**Q1：界面中文显示成方框？**
Kivy 默认字体不含汉字。程序会自动去找安卓系统自带的中文字体（`/system/fonts/NotoSansCJK-Regular.ttc` 等），绝大多数手机没问题。
若确实显示方框，把任意中文字体（如 `NotoSansSC-Regular.otf`）放进项目的 `fonts/` 目录再重新打包即可，文件名需与 `main.py` 里 `FONT_CANDIDATES` 列出的名字一致。

**Q2：条码怎么都识别不出来？**
- 让条码占画面大一些、对焦清楚、光线均匀；
- 一维条码尽量**横向**充满画面（程序也会自动尝试四个旋转方向）；
- 实在不行点预览页的「手动填写」，直接输入文档名称。

**Q3：保存到 `/storage/emulated/0/Documents` 失败？**
这是安卓 11 及以上对公共目录的写入限制，属于系统规则。两种解决办法：
1. 点预览页的「申请『所有文件访问』权限」按钮，按提示打开开关；
2. 或者不管它——程序会自动改存到可写的目录（公共下载 / 应用私有目录），并在结果页显示真实路径。

**Q4：为什么拍照时不用缩略图？**
系统相机默认只回传几百像素的缩略图，那种清晰度认不出条码。所以程序是通过 MediaStore 给相机指定了一个高清输出位置，拿到的是原图。

**Q5：编译报找不到 `libtinfo` / `cython` 之类？**
```bash
sudo apt install libtinfo5   # Ubuntu 22.04 以前
pip3 install --user cython
```

---

## 八、技术要点备注

- **相机取图方案**：不用 FileProvider（python-for-android 的 Manifest 模板里没有 provider 声明，自己加容易出错），而是先通过 `MediaStore` 插入一条图片记录拿到 `content://` 地址，再让相机写入。这个做法不需要改 Manifest，各版本安卓兼容性最好。
- **相册取图方案**：`ACTION_GET_CONTENT` + 三级路径解析（查 `_data` → `FileUtils.copy` → 解码重存），保证拿到可读的本地文件。
- **条码识别库**：`pyzbar`，其配方已自动依赖 `libzbar`，所以 `buildozer.spec` 的 `requirements` 里**不要**再单独写 `libzbar`。
