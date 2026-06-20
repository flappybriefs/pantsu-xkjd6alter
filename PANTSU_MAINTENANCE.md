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

历史面板会列出最近 7 次可撤销操作；继续按 `1` 到 `7`，可撤销到对应
操作之前。撤销包含调频、删除和自造词。

撤销快照保存在 `build/pantsu_undo/`，由 Lua 自动创建并仅保留最近 7 步。
旧版根目录中的 `pantsu_undo_*.tsv` 会自动迁入。该目录属于设备本地临时
状态，不需要复制到手机或参与同步；部署后缺失时会在第一次加载或操作时
重新创建。仓的键盘运行环境若不能创建该目录，会自动改用内存回滚点：
删除、调频和自造词仍会写入根目录 TSV，只是本次键盘进程没有磁盘多步撤销。

调频结果写入 `pantsu_overrides.tsv`，基础词库不再被日常操作反复重写。
同码顺序保存在 `pantsu_candidate_order.tsv`。
自造词的最终编码和删除状态保存在 `pantsu_self_words.tsv`。该文件一旦
存在记录，便是自造词的权威来源；重新部署带回的旧 YAML 不会重新激活
已删除或已改码的词。即使部署后的编译词库暂时没有该词，动态候选也会
直接从 TSV 加载。

仓输入法的 `hamster.yaml` 已设置 `rime.overrideDictFiles: false`，部署前会
把键盘端的 `pantsu.user.dict.yaml`、自造词、调频和同码顺序状态回拷到
应用文件；`build/pantsu_undo/` 不会参与复制。
旧手机若曾在仓的设置界面开启“重新部署时覆盖词库文件”，需要手动关闭
一次；应用界面设置的优先级高于 YAML。

## 自造词

- 空输入时按 `[`：按常规最短空码规则造词。
- 已有输入码时按 `[`：锁定当前输入码造词。
- 每次造词先显示编码、被后移词和飞键数量；再次按空格才真正保存。
- 按 `]`：进入英文单词模式；Lua 不再截获该键。
- 锁定码必须是所造词完整编码或飞键完整编码的前缀，否则显示可用全码。
- 锁定码已有词时，原词自动后移；新词原本在后续码时自动提前。
- 普通造词和锁定码造词都会生成星空键道 6 的飞键等价码，例如
  `q/f`、`j/w`、`x/m`。
- 调频前移后会显示再上一级编码及其当前占用词，方便判断是否继续前移。
- 两字词及四字以上词最短为四码，三字词最短为三码；调频和指定码
  自造词都不会进入单字码区。
- 所有关键 TSV 和 YAML 写入后都会立即重新读取校验；手机端写入失败时
  会显示错误，不再把半写状态当作成功。
- 仓若不支持临时文件重命名，会自动改为直接写入并回读校验。当前运行版
  会在 `pantsu_overrides.tsv` 中保留 `runtime	2026-06-20.3` 标记。

## 维护工具

在 Rime 目录运行：

```bash
python3 tools/pantsu_maintenance.py health
python3 tools/pantsu_maintenance.py history -n 30
python3 tools/pantsu_maintenance.py performance -n 20
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

## 性能观测

自造词、前移、后移和删除会把各步骤耗时写入
`pantsu_performance.tsv`，最多保留最近 300 次操作。计时单位是
Lua CPU 毫秒，适合比较索引、TSV、YAML 和候选刷新哪个阶段较慢；
日志写入自身的耗时不计入总数。

`pantsu_performance.enabled` 默认内容为：

```text
enabled	1
limit	300
clock	lua_cpu_ms
```

将 `enabled` 改为 `0` 可停止记录。手机可直接在“键盘文件”中查看
`pantsu_performance.tsv`；电脑可使用 `performance` 命令汇总。

运行时会缓存必要文件检查和撤销目录位置；自造词修改用户词库后，仅重建
`pantsu.user.dict.yaml` 对应的索引段，不再重新扫描全部基础词库。
