# xkjd6-alter（星空键道6•改）

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