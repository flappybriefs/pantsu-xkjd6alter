--[[
librime-lua 样例
```
  engine:
    translators:
      - lua_translator@lua_function3
      - lua_translator@lua_function4
    filters:
      - lua_filter@lua_function1
      - lua_filter@lua_function2
```
其中各 `lua_function` 为在本文件所定义变量名。
--]]

--[[
本文件的后面是若干个例子，按照由简单到复杂的顺序示例了 librime-lua 的用法。
每个例子都被组织在 `lua` 目录下的单独文件中，打开对应文件可看到实现和注解。

各例可使用 `require` 引入。
```
  foo = require("bar")
```
可认为是载入 `lua/bar.lua` 中的例子，并起名为 `foo`。
配方文件中的引用方法为：`...@foo`。
--]]

date_time_translator = require("date_time")


-- single_char_filter: 候选项重排序，使单字优先
-- 详见 `lua/single_char.lua`
-- single_char_filter = require("single_char")


-- xkjd6_filter: 单字模式 & 630 即 ss 词组提示
--- 修改自 @懒散 TsFreddie https://github.com/TsFreddie/jdc_lambda/blob/master/rime/lua/xkjdc_sbb_hint.lua
-- 可由 schema 的 danzi_mode 与 wxw_hint 开关控制
-- 详见 `lua/xkjd6_filter.lua`
xkjd6_filter = require("xkjd6_filter")

-- 顶功处理器
topup_processor = require("for_topup")

-- 声笔笔简码提示 | 顶功提示 | 补全处理
hint_filter = require("for_hint")

-- number_translator: 将 `=` + 阿拉伯数字 翻译为大小写汉字
-- 详见 `lua/number.lua`
number_translator = require("xnumber")

-- 用 ' 作为次选键
smart_2 = require("smart_2")

-- easy_en_enhance_filter: 连续输入增强
-- 详见 `lua/easy_en.lua`
local easy_en = require("easy_en")
easy_en_enhance_filter = easy_en.enhance_filter


local english = require("english")()
english_processor = english.processor
english_segmentor = english.segmentor
english_translator = english.translator
english_filter = english.filter
english_filter0 = english.filter0



-- rime.lua

forfudan_freq_filter = require("forfudan_freq_filter")
forfudan_freq_first = forfudan_freq_filter.forfudan_freq_first
forfudan_freq_only = forfudan_freq_filter.forfudan_freq_only

--[[
librime-lua 样例
```
  engine:
    translators:
      - lua_translator@lua_function3
      - lua_translator@lua_function4
    filters:
      - lua_filter@lua_function1
      - lua_filter@lua_function2
```
其中各 `lua_function` 为在本文件所定义变量名。
--]]

--[[
本文件的后面是若干个例子，按照由简单到复杂的顺序示例了 librime-lua 的用法。
每个例子都被组织在 `lua` 目录下的单独文件中，打开对应文件可看到实现和注解。

各例可使用 `require` 引入。
```
  foo = require("bar")
```
可认为是载入 `lua/bar.lua` 中的例子，并起名为 `foo`。
配方文件中的引用方法为：`...@foo`。
--]]



-- single_char_filter: 候选项重排序，使单字优先
-- 详见 `lua/single_char.lua`
-- single_char_filter = require("single_char")


-- xmjd6_filter: 单字模式 & 630 即 ss 词组提示
--- 修改自 @懒散 TsFreddie https://github.com/TsFreddie/jdc_lambda/blob/master/rime/lua/xkjdc_sbb_hint.lua
-- 可由 schema 的 danzi_mode 与 wxw_hint 开关控制
-- 详见 `lua/xmjd6_filter.lua`
xmjd6_filter = require("xmjd6_filter")

-- 顶功处理器
xmjdtopup_processor = require("xmjdfor_topup")

-- 声笔笔简码提示 | 顶功提示 | 补全处理
xmjdhint_filter = require("xmjdfor_hint")

-- number_translator: 将 `=` + 阿拉伯数字 翻译为大小写汉字
-- 详见 `lua/number.lua`
xmjdnumber_translator = require("xmjdxnumber")

-- 用 ' 作为次选键
xmjdsmart_2 = require("xmjdsmart_2")

xmjdshuzi = require("xmjdshuzi")

xmjdjisuanqi = require("xmjdjisuanqi")

xmjdshijian = require("xmjdshijian")

xmjdxuanchongjsq = require("xmjdxuanchongjsq")


topup_processor = require("jd27_topup")  
date_translator = require("date")  


local smyh_core = require("smyh.core")

smyh_filter = smyh_core.filter
smyh_translator = smyh_core.translator


-- 星猫键道6
-- xmjd6_filter: 单字模式 & 630 即 ss 词组提示
--- 修改自 @懒散 TsFreddie https://github.com/TsFreddie/jdc_lambda/blob/master/rime/lua/xkjdc_sbb_hint.lua
-- 可由 schema 的 danzi_mode 与 wxw_hint 开关控制
-- 详见 `lua/xmjd6_filter.lua`
xmjd6_filter = require("xmjd6_filter")
-- 顶功处理器
xmjdtopup_processor = require("xmjdfor_topup")
-- 声笔笔简码提示 | 顶功提示 | 补全处理
xmjdhint_filter = require("xmjdfor_hint")
-- 用 ' 作为次选键
xmjdsmart_2 = require("xmjdsmart_2")
xmjdshuzi = require("xmjdshuzi")
xmjdjisuanqi = require("xmjdjisuanqi")
xmjdshijian = require("xmjdshijian")