# 胖次键道维护说明

## 日常操作

- `8`：当前候选前移；同码候选内也可前移。
- `9`：当前候选后移；同码候选内也可后移。
- `0`：第一次标记删除，第二次确认删除。
- macOS：`Control+Z` 撤销，`Control+H` 查看最近操作。
- Windows/Linux：`Ctrl+Z` 撤销，`Ctrl+Shift+H` 查看最近操作。
- `Esc`：退出当前输入和连续调频。

成功调频后只刷新候选顺序，不显示常驻成功提示；删除确认、失败原因、
撤销结果和主动查看历史仍会显示。

这些快捷键只在 Rime 已有输入码或候选菜单时生效。空状态下不会拦截，
仍由当前应用处理。

鼠须管会在前端忽略带 Command 的普通按键，因此 `Command+Z` 无法交给
Rime Lua 处理。

调频结果写入 `pantsu_overrides.tsv`，基础词库不再被日常操作反复重写。
同码顺序保存在 `pantsu_candidate_order.tsv`。
自造词的最终编码和删除状态保存在 `pantsu_self_words.tsv`；如果部署覆盖了
`pantsu.user.dict.yaml`，下次加载胖次键道时会从该文件自动恢复。

## 自造词

- 空输入时按 `[`：按常规最短空码规则造词。
- 已有输入码时按 `[`：锁定当前输入码造词。
- 锁定码必须是所造词完整编码或飞键完整编码的前缀，否则显示可用全码。
- 锁定码已有词时，原词自动后移；新词原本在后续码时自动提前。
- 普通造词和锁定码造词都会生成星空键道 6 的飞键等价码，例如
  `q/f`、`j/w`、`x/m`。
- 调频前移后会显示再上一级编码及其当前占用词，方便判断是否继续前移。
- 两字词及四字以上词最短为四码，三字词最短为三码；调频和指定码
  自造词都不会进入单字码区。

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

覆盖记录和自造词状态按操作时间合并。无法自动解决的内容写入
`pantsu_sync_conflicts.tsv`，不会静默覆盖。
