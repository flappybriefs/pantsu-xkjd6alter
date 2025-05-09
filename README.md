# pantsu-xkjd6alter（胖次键道-星空键道6•改），又名磨道，折磨版键道

## 简单的介绍

GitHub仓库链接：https://github.com/flappybriefs/pantsu-xkjd6alter

胖次版键道，修改了大量的词序，修改了大量的630词汇，并加以扩充，将次选的一简二简单字加了无理码，增加了很多词组二简和声声笔，后移了一部分单字，所以使用习惯和键道官方版以及一些别的衍生版差别很大，故又名折磨版键道，既磨道，为了极致的码长和顶功的快感而魔改。

一些小功能：
- 打字时使用单引号'开关emoji；
- 按v开启临时英语；
- /开头是诗词和东方project相关词汇，可以在pantsu.user.dict里面找到并修改/删除；
- 单引号'开头开启二分，使用键道的双拼打二分对生僻字进行查找，反查的基本上所有的常用字和多数生僻字都有拼音标注在后面;
- `开启反查，与官方版一致，也带有拼音的标注在后面;
- [和]可以用作以词定字，[选择第一个，]选择最后一个，使用-=换页；
- 移植了一部分小鹤的符号，;f开启；
- 该方案无次选按钮，如果想开的话需要自己设置一下，不能用;’/作为次选或三选，其余皆可。

如果用的是iOS，可以用我制作的仓输入法皮肤，即hamster.yaml，里面有两种适用于胖次键道的布局，也可用在吉旦饼方案中。

友链：[天行键](https://github.com/wzxmer/rime-txjx)，[星猫键道](https://github.com/hugh7007/xmjd6-rere)

如果想改词序的话可以直接提issue，我会更新得很勤快。

---

## 一些大的更改

2023-12-21 更改了pantsu.user.dict，将所有符号都改成了;开头，而东方和诗词词汇用/开头，这样就不会影响到i和o上面的字的顶功了，并更新了一下最新的beta测试版的仓的布局文件，逗号和句号下划是以词定字的选第一个和选最后一个。

---

2023.12.16 增加了键道码表版的二分，打生僻字更简单了，使用’开启，二分的键道版码表由[星猫键道](https://github.com/hugh7007/xmjd6-rere)提供，二分方案和码表名称目前前缀为pantsuef

---

2023.11.19 在浮生大佬的帮助下将我的文件进行了大量删减并带上了前缀，并且不再需要rime.lua，这样就非常好整理了

---

2023.11.17正式更名为胖次键道，不跟官方版的冲突

---

做了个iOS的仓输入法的皮肤，需要的话自取，自带横屏模式

---

2023.11.2 终于还是受不了过于抽象的外挂词库2了，于是将其删去了，重制了一版外挂码表，目前看来还算不错。

---

2023.10.22稍微精简了一下文件，将外挂词库里面的网络词库更新到了2023.10.20版，并修改扩大了临时英文的词库。增加了我自己做的仓输入法的皮肤。

---

2023.6.29加了一个乐子外挂waigua2，百万级别的词库，有很多废词，可选择关闭或者删除

---

2023.6.24精简掉了词库，只保留altercizu和waigua

---

2023.6.3更新了两版的词库，xkjd6.altercizu1和xkjd6.waigua1、xkjd6.altercizu2和xkjd6.waigua2，其中altercizu可以替换官方词库，altercizu2更大一些，废词也更多一些，但用起来空码的情况少很多，根据需要选取1或者2，外挂词库跟着数字选取，在extended.dict里面开关。

---

2023.5.31更新了一个我重新制作的词库xkjd6.altercizu，里面包含官方词库，以后就默认启用和修改这个了，有空了我会基于这个新词库重新制作一下外挂词库

---

星空键道6的胖次个人魔改版，仅修改了普通版本，并击和单字版并未魔改，并且在官方版的基础上添加了反查的拼音（如下所示），并添加了对于emoji的支持。

<img width="691" alt="CleanShot 2023-04-27 at 01 17 53@2x" src="https://user-images.githubusercontent.com/35480800/234622465-a25039ea-ef57-4c60-85d9-2d54ec208f0b.png">

增/删/改了很多原版词库里面的词以及词序，并且仍在进行中。单字的二简二三选全部改成了无理码，不必使用数字选重，无理码规则参照了西风瘦码，;表示左右结构，/为非左右结构。目前正在陆续增加单字的无理码以尽量降低单字的码长，增强输入体验。

本人是在Mac的鼠须管和iOS端的iRime使用，目前没有问题。

其中[xkdj6.waigua.dict.yaml](https://github.com/flappybriefs/xkjd6-alter/blob/main/xkjd6.waigua.dict.yaml)是我自己整合的多个词库做出的超大词库，可以在[xkjd6.extended.dict.yaml](https://github.com/flappybriefs/xkjd6-alter/blob/main/xkjd6.extended.dict.yaml)里面注释一下关掉/删除。

emoji来自于：[rime-opencc_emoji_symbols](https://github.com/rtransformation/rime-opencc_emoji_symbols)，为了防止emoji影响单字上屏，默认是关闭的，可使用单引号'开关emoji。

添加了[星猫键道](https://github.com/wzxmer/xkjd6-rime/tree/main) 的英文输入（v开启）和GKB单字码表（o开启），但考虑到反查寻找可能有点难受，所以未加入到反查里面。
