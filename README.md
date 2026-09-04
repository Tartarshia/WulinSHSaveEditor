# 大侠立志传：本地存档修改器

用于 Steam 版《大侠立志传：碧血丹心》（AppID 1948980）的离线 Windows 存档修改器。

功能包括：

- 背包道具按名称或 ID 搜索、按 ID 排序、按游戏物品类别筛选；修改数量或添加道具。
- 从游戏自带数据表显示物品与角色中文名称。
- 查看出战、已入队未出战、曾入队已离队角色，并修改基础属性。
- 每次写入前完整备份存档槽；AES/GZip 编码后的内容会先回读验证，再原子替换原文件。

本工具不修改剧情、任务、入队状态或 Steam 成就。

## 使用

1. 完全退出游戏。
2. 运行 `启动大侠立志传存档修改器.cmd`，或从 Releases 下载 `WulinSHSaveEditor.exe`。
3. 工具会自动寻找 Steam 安装目录和存档目录；若找不到，点击界面顶部的“选择游戏目录”或“选择存档目录”。游戏目录应直接包含 `Wulin.exe`，存档根目录应直接包含 `Save0`、`QuickSave0` 等文件夹。
4. 读取存档、修改内容并保存。备份位于存档根目录的 `_EditorBackups`。
5. 启动游戏验证。若 Steam Cloud 出现冲突，请确认选择刚修改的本地版本。

选择过的目录只保存在本机 `%APPDATA%\WulinSHSaveEditor\config.json`，不会上传、不会写入本项目，也不会随发布包分发。

## 从源码运行或构建

需要 Python 3.11+：

```powershell
python -m pip install -r requirements.txt
python app.py
python test_public.py
```

构建单文件 Windows 程序：

```powershell
.\build.ps1
```

构建产物为 `dist\WulinSHSaveEditor.exe`。

## 免责声明

请自行保留额外备份。游戏更新可能改变存档结构；修改存档的风险由使用者自行承担。
