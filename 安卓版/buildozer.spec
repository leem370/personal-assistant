[app]

# (str) Title of your application, displayed in the app menu
title = 个人助理

# (str) Package name
package.name = personal_assistant

# (str) Package domain
package.domain = org.personal

# (str) Source code directory
source.dir = .

# (str) Source code excludes
source.exclude_exts = spec,pyc,md,env,txt,log

# (list) List of directory to exclude from source
source.exclude_dirs = __pycache__,data,.git,assets

# (list) Application version
version = 0.1.0

# (list) Application requirements
requirements = python3,kivy,kivymd,requests,pyyaml,schedule,plyer

# (str) Presplash of the application
#presplash.filename = %(source.dir)s/assets/presplash.png

# (str) Icon of the application
#icon.filename = %(source.dir)s/assets/icon.png

# (str) Supported orientation
orientation = portrait

# (bool) Indicate if the app should be fullscreen or not
fullscreen = 0

# (list) Permissions
android.permissions = VIBRATE,INTERNET,RECEIVE_BOOT_COMPLETED,WAKE_LOCK,PACKAGE_USAGE_STATS,FOREGROUND_SERVICE,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE

# (int) Target Android API
android.api = 31

# (int) Minimum Android API
android.minapi = 21

# (str) Android NDK version
android.ndk = 25b

# (str) Android SDK version
android.sdk = 31

# (bool) If True, copy all library files into the apk (like java/libs/*.jar)
android.copy_libs = 1

# (str) The Android arch to build for
android.archs = arm64-v8a, armeabi-v7a

# (bool) enables Android auto backup feature
android.allow_backup = True

[buildozer]

# (int) Log level (0 = error, 1 = warn, 2 = info, 3 = debug)
log_level = 2

# (int) Display warning
warn_on_root = 1