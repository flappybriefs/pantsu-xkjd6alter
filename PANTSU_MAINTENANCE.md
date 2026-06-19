# 胖次键道维护说明

## 日常操作

- `8`：当前候选前移；同码候选内也可前移。
- `9`：当前候选后移；同码候选内也可后移。
- `0`：第一次标记删除，第二次确认删除。
- macOS：`Command+Z` 撤销，`Command+Shift+H` 查看最近操作。
- Windows/Linux：`Ctrl+Z` 撤销，`Ctrl+Shift+H` 查看最近操作。
- `Esc`：退出当前输入和连续调频。

成功调频后只刷新候选顺序，不显示常驻成功提示；删除确认、失败原因、
撤销结果和主动查看历史仍会显示。

这些快捷键只在 Rime 已有输入码或候选菜单时生效。空状态下不会拦截，
仍由当前应用处理。

调频结果写入 `pantsu_overrides.tsv`，基础词库不再被日常操作反复重写。
同码顺序保存在 `pantsu_candidate_order.tsv`。

## 维护工具

在 Rime 目录运行：

```bash
python3 tools/pantsu_maintenance.py health
python3 tools/pantsu_maintenance.py history -n 30
python3 tools/pantsu_maintenance.py backup
python3 tools/pantsu_maintenance.py restore 20260619-120000
```

定期将稳定覆盖合并回基础词库：

```bash
python3 tools/pantsu_maintenance.py apply-overrides
```

## 设备同步

在每台设备导出自己的状态：

```bash
python3 tools/pantsu_maintenance.py sync-export
```

同步目录传到其他设备后执行：

```bash
python3 tools/pantsu_maintenance.py sync-merge
```

覆盖记录按操作时间合并；自造词取并集。无法自动解决的内容写入
`pantsu_sync_conflicts.tsv`，不会静默覆盖。
