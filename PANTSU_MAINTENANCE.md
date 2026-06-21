# 胖次键道维护说明

## 日常操作

- `8`：当前候选前移；同码候选内也可前移。
- `9`：当前候选后移；同码候选内也可后移。
- `0`：第一次标记删除，第二次确认删除。
- macOS：`Control+Z` 撤销，`Control+H` 查看最近操作。
- Windows/Linux/仓输入法：`Ctrl+Z` 撤销，`Ctrl+H` 查看最近操作；
  桌面端原有的 `Ctrl+Shift+H` 也继续兼容。
- `Esc`：退出当前输入和连续调频。

成功调频后只刷新候选顺序，不显示常驻成功提示；删除确认、失败原因、
撤销结果和主动查看历史仍会显示。

词条改码后，旧码继续组句时会把旧词前缀替换为该码当前首选；沿新码
继续输入时保留原词，避免前移、后移或删除后仍出现旧顺序句子。

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
把键盘端的 `pantsu.user.dict.yaml`、`pantsu.zzc.dict.yaml`、自造词、
调频和同码顺序状态回拷到
应用文件；`build/pantsu_undo/` 不会参与复制。
旧手机若曾在仓的设置界面开启“重新部署时覆盖词库文件”，需要手动关闭
一次；应用界面设置的优先级高于 YAML。

## 自造词

- 空输入时按 `[`：按常规最短空码规则造词。
- 已有输入码时按 `[`：锁定当前输入码造词。
- 选入字词后立即显示最终编码、被后移词和飞键数量；按一次空格直接保存。
- 按 `]`：进入英文单词模式；Lua 不再截获该键。
- 锁定码必须是所造词完整编码或飞键完整编码的前缀，否则显示可用全码。
- 锁定码已有词时，原词自动后移；新词原本在后续码时自动提前。
- 普通造词和锁定码造词只生成星空键道 6 的合法飞键等价码：声母首位`q/f`、`w/j`，以及 `uang` 韵母第二位 `x/m`。飞键必须保持其余码位完全相同；同一汉字的其他多音字编码不会再作为飞键生成。
- 调频前移后会显示再上一级编码及其当前占用词，方便判断是否继续前移。
- 两字词及四字以上词最短为四码，三字词最短为三码；调频和指定码自造词都不会进入单字码区。
- 所有关键 TSV 和 YAML 写入后都会立即重新读取校验；手机端写入失败时会显示错误，不再把半写状态当作成功。
- 仓若不支持临时文件重命名，会自动改为直接写入并回读校验。当前运行版会在 `pantsu_overrides.tsv` 中保留 `runtime	2026-06-20.3` 标记。

## 维护工具

在 Rime 目录运行：

```bash
python3 tools/pantsu_maintenance.py health
python3 tools/pantsu_maintenance.py repair-overrides
python3 tools/pantsu_maintenance.py migrate-orders
python3 tools/pantsu_maintenance.py history -n 30
python3 tools/pantsu_maintenance.py performance -n 20
python3 tools/pantsu_maintenance.py backup
python3 tools/pantsu_maintenance.py restore 20260619-120000
```

定期将稳定覆盖合并回基础词库：

```bash
python3 tools/pantsu_maintenance.py apply-overrides
```

当前只有一个胖次键道方案。有效中文词库为 `pantsu.core`、`pantsu.danzi`、
`pantsu.cizu`、`pantsu.temp`、`pantsu.user` 和 `pantsu.zzc`。
原 `pantsu.waigua` 已合并进 `pantsu.cizu`，不再单独加载。

## 设备同步

平时只需双击 `胖次键道维护.command`，直接按回车。

电脑会自动完成以下操作：

1. 从仓输入法的 iCloud 目录读取手机状态；
2. 按每条记录的更新时间合并电脑与手机内容；
3. 先自动备份，再把合并结果写回电脑；
4. 同一份结果写回手机的 iCloud 目录；
5. 重新加载鼠须管。

完成后只需在仓输入法中再执行一次“同步/重新部署”，手机就会读取结果。
第一次使用时，如果提示手机尚无状态，先在仓输入法中执行一次
“同步/重新部署”，回到电脑再次按回车即可。通常不需要手工导出、选择文件
或分别执行多条命令。

覆盖、自造词、候选顺序和词频均按记录更新时间合并；无法自动解决的竞争
写入 `pantsu_sync_conflicts.tsv`，不会静默覆盖。

## 性能观测

电脑上可运行完整性能与极端压力测试：

```bash
PYTHONPATH=/tmp/audit-rime-jiandao-deps \
python3 tools/pantsu_performance.py
```

默认执行 20 万次查询，并用中文直接说明“逐次扫文件、首次建立索引、日常
缓存查询、编码占用判断”各自花费多少时间。手机数字使用桌面实测的 8 倍作
保守估计，便于阅读，不代表手机上的精确计时。

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

运行时会缓存必要文件检查和撤销目录位置。自造词单独保存在很小的
`pantsu.zzc.dict.yaml`；首次升级会从 `pantsu.user.dict.yaml` 的旧自造词区
自动迁移，之后只重建 `pantsu.zzc.dict.yaml` 对应的索引段，不再重新扫描
或重写完整用户词库。

动态候选刷新会把主码、飞键码和被挤动词条合并为一个批次，所有受影响
编码根重建完成后只写入一次缓存。自造词保存后，内存词库索引仅替换
`pantsu.zzc.dict.yaml` 对应的小段；磁盘索引保留脏标记，下次启动时再校验。
性能日志会分别记录词条查询、快照构建、缓存写入和校验耗时。

寻找最短空码时使用专用占码查询，不再为每个飞键构造完整候选词条。占码
扫描从当前词长允许的最短编码开始，不再读取宽泛的前两码分支；指定码造词
也只加载目标码及其后续顺延分支。

词典范围索引会按前两码直接定位磁盘区间。解析后的有效候选再按最长四码
分片缓存在内存中，造词、调频、删除和占码判断共用；状态变化时只失效受
影响的编码分片。缓存采用最近使用的 32 个分片上限，避免手机长期运行时
内存持续增长。

造词与候选编辑共用 `lua/pantsu_chain.lua` 中的候选链模型、索引、移动原语
和递归生命周期。造词的同词排除与失败回退、候选编辑的多路径歧义与强制
后移仍作为两种明确策略保留。修改候选链后可运行：

```bash
PYTHONPATH=/tmp/audit-rime-jiandao-deps \
python3 tools/test_pantsu_chain.py
```
