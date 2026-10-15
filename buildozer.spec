[app]
# ==============================================================================
#  条码拍照 PDF 生成器 —— Android 打包配置
#
#  说明：本文件是 buildozer 的配置文件。buildozer 是 python-for-android 的
#        命令行封装，用来把 Python/Kivy 程序编译成安卓 APK。
#
#  打包命令（需要在 Linux 或 WSL2 里执行，Windows 的 CMD 不能直接用）：
#        buildozer -v android debug
#  编译好的 APK 会出现在项目目录的 bin/ 子目录里。
# ==============================================================================

# ------------------------------ 应用基本信息 ----------------------------------
title = 条码PDF生成器
package.name = barcodepdf
package.domain = org.example

# ------------------------------ 源码设置 --------------------------------------
# source.dir = . 表示「当前目录就是源码目录」
source.dir = .
# 需要打包进 APK 的文件类型（otf/ttf/ttc 是字体，保证界面中文正常显示）
source.include_exts = py,png,jpg,jpeg,kv,atlas,json,otf,ttf,ttc
# 这些目录不用打包（编译产物、缓存等）
source.exclude_dirs = bin,.buildozer,__pycache__,build_tools

version = 1.0.0

# ------------------------------ Python 依赖 -----------------------------------
# 说明：
#   python3  —— 打包时会把 Python 解释器一起打进 APK
#   kivy     —— 界面框架
#   pillow   —— 图片处理 + 生成 PDF（必须）
#   pyzbar   —— 条码识别（python-for-android 官方自带这个配方）
#   cffi     —— pyzbar 的底层依赖，显式写上更稳
#
# 注意：不要在这里再写 libzbar —— pyzbar 的配方会自动把 libzbar 一起编译进来。
requirements = python3,kivy,pillow

# ------------------------------ 界面设置 --------------------------------------
orientation = portrait
fullscreen = 0
# 顶部状态栏以外的区域都留给应用

# ------------------------------ Android 版本 ----------------------------------
# api     = 编译时使用的 Android SDK 版本
# minapi  = 最低支持的安卓版本，24 对应 Android 7.0
android.api = 34
android.minapi = 24
android.ndk = 28c
android.ndk_api = 24
android.skip_update = False
android.accept_sdk_license = True
android.archs = arm64-v8a, armeabi-v7a
android.apptheme = @android:style/Theme.NoTitleBar.Fullscreen

# ------------------------------ 权限声明 --------------------------------------
# CAMERA                 —— 调用系统相机拍照
# READ/WRITE_EXTERNAL_STORAGE —— 在低版本安卓上读写公共存储
# READ_MEDIA_IMAGES      —— Android 13+ 读取相册图片
android.permissions = CAMERA, READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE, READ_MEDIA_IMAGES
android.features = android.hardware.camera

# ------------------------------ 外观 ------------------------------------------
android.presplash_color = #2688EB
# 如果你准备了应用图标，取消下面这行的注释并放好图片：
# android.icon = images/icon.png

# ------------------------------ 构建参数 --------------------------------------
p4a.branch = stable
p4a.bootstrap = sdl2
log_level = 2
warn_on_root = 1
