[app]
title = Samir Pyth_DZ
package.name = samirpythdz
package.domain = org.samir
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf,xml
source.exclude_dirs = bin, .buildozer, venv, __pycache__, .git
source.exclude_patterns = *.db, startup_error.txt, *.pdf
version = 1.1.1

icon.filename = %(source.dir)s/icon.png
presplash.filename = %(source.dir)s/splash.png
presplash.color = #020B1E

# المتطلبات (p4a لا يثبّت الاعتماديات تلقائيًا، لذلك تُكتب كلها صراحةً)
# - sqlite3 : ضروري وإلا يفشل import sqlite3 على الهاتف
# - python-bidi==0.4.2 : النسخ الأحدث مكتوبة بـ Rust ولا تُبنى على Android
# - androidx.core تُزال من هنا (ليست recipe) وتبقى في gradle_dependencies
requirements = python3,hostpython3,kivy==2.3.0,kivymd==1.1.1,sqlite3,pillow,reportlab,cryptography,arabic-reshaper,python-bidi==0.4.2,pypdf

orientation = portrait
fullscreen = 0

android.api = 33
android.minapi = 24
android.ndk = 25b
android.ndk_api = 24
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True

android.permissions = INTERNET, READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE, READ_MEDIA_IMAGES

# FileProvider لمشاركة النسخ الاحتياطية
android.enable_androidx = True
android.gradle_dependencies = androidx.core:core:1.9.0
# ملاحظة: الـ <provider> يُضاف تلقائياً في build.yml (هذا المفتاح يقبل attributes فقط)
android.add_resources = ./xml/file_paths.xml:xml/file_paths.xml

android.allow_backup = True
android.logcat_filters = *:S python:D

# نسخة p4a مستقرة مع kivy 2.3.0 / Python 3.11 / NDK 25b
p4a.branch = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 1
